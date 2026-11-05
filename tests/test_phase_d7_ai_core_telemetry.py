"""
Comprehensive unit and integration tests for LIGHT AI V1.0 AI Core Runtime Telemetry (Phase B).
Verifies:
- Monotonic latency tracking on GatewayResponse and CoeGatewayClient
- Separate last-request and cumulative session token usage (prompt, completion, total)
- Bounded latency history (maxlen=20) and average latency calculation strictly from successful calls
- Preservation of configured_model vs resolved_model
- Request lifecycle transitions (PROCESSING, IDLE, ERROR) and in-flight request tracking
- Safe context capacity handling (Unknown/None when unverified)
- SessionMemory telemetry integration
- Thread safety and concurrency protection
- Sanitization (zero API keys, prompts, or secrets in telemetry snapshots)
- Bridge schema and telemetry snapshot conformance
"""

import collections
import concurrent.futures
from dataclasses import dataclass
import json
import time
from unittest.mock import MagicMock, patch
import pytest

from core.coe_gateway import CoeGatewayClient, GatewayStatus, GatewayResponse
from core.bridge.schema import (
    BridgeMessageType,
    create_ai_core_state_event,
    create_telemetry_message,
    validate_incoming_message,
)
from core.bridge.telemetry import TelemetryCollector
from memory.session_memory import SessionMemory


class DummyUsage:
    def __init__(self, prompt=100, completion=50, total=150):
        self.prompt_tokens = prompt
        self.completion_tokens = completion
        self.total_tokens = total


class DummyChoice:
    def __init__(self, content='{"intent": "CONVERSATION", "voice_response": "Ji sir"}'):
        self.message = MagicMock(content=content)


class DummyCompletionResponse:
    def __init__(self, content='{"intent": "CONVERSATION", "voice_response": "Ji sir"}', model="vllm-qwen-resolved", usage=None):
        self.choices = [DummyChoice(content)]
        self.model = model
        self.usage = usage or DummyUsage()


def test_gateway_response_contains_latency():
    """Verify GatewayResponse holds latency_ms and serializes it in to_dict()."""
    resp = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content="test",
        latency_ms=142,
    )
    assert resp.latency_ms == 142
    d = resp.to_dict()
    assert d["latency_ms"] == 142
    assert d["status"] == "SUCCESS"


def test_monotonic_latency_and_successful_average():
    """Verify monotonic latency measurement and that only successful requests enter recent_latencies."""
    mock_openai = MagicMock()
    
    # Simulate first request: takes 50ms, succeeds
    def mock_create_1(*args, **kwargs):
        time.sleep(0.05)
        return DummyCompletionResponse(usage=DummyUsage(100, 50, 150))

    mock_openai.chat.completions.create.side_effect = mock_create_1
    client = CoeGatewayClient(api_key="sk-test", base_url="https://test.ai/v1", model="qwen-base", client=mock_openai)

    resp1 = client.chat([{"role": "user", "content": "hi"}])
    assert resp1.status == GatewayStatus.SUCCESS
    assert resp1.latency_ms is not None
    assert resp1.latency_ms >= 40  # ~50ms

    snap1 = client.get_telemetry_snapshot()
    assert snap1["success_count"] == 1
    assert snap1["failure_count"] == 0
    assert snap1["last_request_latency_ms"] == resp1.latency_ms
    assert snap1["last_successful_latency_ms"] == resp1.latency_ms
    assert len(snap1["recent_latencies_ms"]) == 1
    assert snap1["avg_latency_ms"] == float(resp1.latency_ms)

    # Simulate second request: raises timeout (failure)
    import openai
    mock_openai.chat.completions.create.side_effect = openai.APITimeoutError("Request timed out")
    resp2 = client.chat([{"role": "user", "content": "hi"}])
    assert resp2.status == GatewayStatus.TIMEOUT
    assert resp2.latency_ms is not None

    snap2 = client.get_telemetry_snapshot()
    assert snap2["success_count"] == 1
    assert snap2["failure_count"] == 1
    # Bounded latency list must NOT include the failed request!
    assert len(snap2["recent_latencies_ms"]) == 1
    assert snap2["last_successful_latency_ms"] == resp1.latency_ms
    assert snap2["avg_latency_ms"] == float(resp1.latency_ms)
    assert snap2["last_error_category"] == "TIMEOUT"


def test_last_and_cumulative_session_token_tracking():
    """Verify last-request and cumulative session tokens are tracked separately and distinguish prompt/completion/total."""
    mock_openai = MagicMock()
    client = CoeGatewayClient(api_key="sk-test", base_url="https://test.ai/v1", model="qwen-base", client=mock_openai)

    # Call 1: 100 prompt, 40 completion -> 140 total
    mock_openai.chat.completions.create.return_value = DummyCompletionResponse(usage=DummyUsage(100, 40, 140))
    client.chat([{"role": "user", "content": "one"}])

    snap1 = client.get_telemetry_snapshot()
    assert snap1["last_tokens"] == {"prompt_tokens": 100, "completion_tokens": 40, "total_tokens": 140}
    assert snap1["session_tokens"] == {"prompt_tokens": 100, "completion_tokens": 40, "total_tokens": 140}

    # Call 2: 200 prompt, 80 completion -> 280 total
    mock_openai.chat.completions.create.return_value = DummyCompletionResponse(usage=DummyUsage(200, 80, 280))
    client.chat([{"role": "user", "content": "two"}])

    snap2 = client.get_telemetry_snapshot()
    assert snap2["last_tokens"] == {"prompt_tokens": 200, "completion_tokens": 80, "total_tokens": 280}
    assert snap2["session_tokens"] == {"prompt_tokens": 300, "completion_tokens": 120, "total_tokens": 420}

    # Call 3: Missing usage object (None)
    mock_openai.chat.completions.create.return_value = DummyCompletionResponse(usage=None)
    mock_openai.chat.completions.create.return_value.usage = None
    client.chat([{"role": "user", "content": "three"}])

    snap3 = client.get_telemetry_snapshot()
    assert snap3["last_tokens"] is None
    # Session tokens must remain preserved, not reset or zeroed out
    assert snap3["session_tokens"] == {"prompt_tokens": 300, "completion_tokens": 120, "total_tokens": 420}


def test_configured_vs_resolved_model_preservation():
    """Verify configured model name and server-resolved model are tracked distinctly."""
    mock_openai = MagicMock()
    mock_openai.chat.completions.create.return_value = DummyCompletionResponse(
        model="/home/user1/models/Qwen3.6-35B-A3B-NVFP4-Fast"
    )
    client = CoeGatewayClient(api_key="sk-test", base_url="https://test.ai/v1", model="qwen3.6", client=mock_openai)

    # Prior to request: resolved_model is None
    assert client.configured_model == "qwen3.6"
    assert client.resolved_model is None
    assert client.get_telemetry_snapshot()["resolved_model"] is None

    # After request: resolved_model is captured from response
    client.chat([{"role": "user", "content": "ping"}])
    assert client.configured_model == "qwen3.6"
    assert client.resolved_model == "/home/user1/models/Qwen3.6-35B-A3B-NVFP4-Fast"
    snap = client.get_telemetry_snapshot()
    assert snap["configured_model"] == "qwen3.6"
    assert snap["resolved_model"] == "/home/user1/models/Qwen3.6-35B-A3B-NVFP4-Fast"


def test_request_lifecycle_and_in_flight_tracking():
    """Verify in-flight counter and state transitions (PROCESSING -> IDLE/ERROR)."""
    mock_openai = MagicMock()
    recorded_states = []

    def state_callback(snapshot):
        recorded_states.append((snapshot["runtime_state"], snapshot["in_flight_requests"]))

    client = CoeGatewayClient(api_key="sk-test", base_url="https://test.ai/v1", model="qwen3.6", client=mock_openai)
    client.on_state_change = state_callback

    def slow_create(*args, **kwargs):
        # Inspect client state during call
        snap = client.get_telemetry_snapshot()
        assert snap["runtime_state"] == "PROCESSING"
        assert snap["in_flight_requests"] == 1
        return DummyCompletionResponse()

    mock_openai.chat.completions.create.side_effect = slow_create

    resp = client.chat([{"role": "user", "content": "hi"}])
    assert resp.status == GatewayStatus.SUCCESS

    # After completion: state is IDLE, in-flight is 0
    final_snap = client.get_telemetry_snapshot()
    assert final_snap["runtime_state"] == "IDLE"
    assert final_snap["in_flight_requests"] == 0

    # Ensure callback observed PROCESSING and IDLE
    states = [s[0] for s in recorded_states]
    assert "PROCESSING" in states
    assert "IDLE" in states


def test_concurrent_requests_thread_safety():
    """Verify that multiple concurrent gateway requests safely manage in-flight counts and metrics under load."""
    mock_openai = MagicMock()
    
    def delayed_create(*args, **kwargs):
        time.sleep(0.02)
        return DummyCompletionResponse(usage=DummyUsage(10, 5, 15))

    mock_openai.chat.completions.create.side_effect = delayed_create
    client = CoeGatewayClient(api_key="sk-test", base_url="https://test.ai/v1", model="qwen3.6", client=mock_openai)

    # Launch 6 concurrent requests
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(client.chat, [{"role": "user", "content": f"msg_{i}"}]) for i in range(6)]
        results = [f.result() for f in futures]

    assert len(results) == 6
    for r in results:
        assert r.status == GatewayStatus.SUCCESS

    snap = client.get_telemetry_snapshot()
    assert snap["in_flight_requests"] == 0
    assert snap["success_count"] == 6
    assert snap["failure_count"] == 0
    assert snap["session_tokens"]["total_tokens"] == 15 * 6
    assert len(snap["recent_latencies_ms"]) == 6


def test_context_capacity_and_utilization_handling():
    """Verify context capacity is None (Unknown) by default, and calculated when verified."""
    mock_openai = MagicMock()
    mock_openai.chat.completions.create.return_value = DummyCompletionResponse(usage=DummyUsage(500, 100, 600))
    client = CoeGatewayClient(api_key="sk-test", base_url="https://test.ai/v1", model="qwen3.6", client=mock_openai)

    # Default: COE_AI_CONTEXT_CAPACITY is None
    client.chat([{"role": "user", "content": "hi"}])
    snap1 = client.get_telemetry_snapshot()
    assert snap1["context_capacity"] is None
    assert snap1["remaining_tokens"] is None
    assert snap1["utilization_percentage"] is None

    # When context capacity is configured:
    with patch("core.coe_gateway.COE_AI_CONTEXT_CAPACITY", 32768):
        snap2 = client.get_telemetry_snapshot()
        assert snap2["context_capacity"] == 32768
        assert snap2["remaining_tokens"] == 32768 - 600
        assert snap2["utilization_percentage"] == round((600 / 32768) * 100, 2)


def test_telemetry_collector_ai_core_snapshot_integration():
    """Verify TelemetryCollector bundles ai_core payload with SessionMemory and Gateway data."""
    collector = TelemetryCollector()

    # Create mock gateway client and session memory
    mock_gw = MagicMock()
    mock_gw.get_telemetry_snapshot.return_value = {
        "provider": "CoE AI Gateway",
        "configured_model": "qwen3.6",
        "resolved_model": "Qwen-35B",
        "gateway_status": "ONLINE",
        "runtime_state": "IDLE",
        "in_flight_requests": 0,
        "last_request_status": "SUCCESS",
        "last_error_category": None,
        "last_request_latency_ms": 320,
        "last_successful_latency_ms": 320,
        "avg_latency_ms": 320.0,
        "recent_latencies_ms": [320],
        "success_count": 5,
        "failure_count": 0,
        "last_success_timestamp": 123456789.0,
        "last_tokens": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        "session_tokens": {"prompt_tokens": 500, "completion_tokens": 250, "total_tokens": 750},
        "context_capacity": None,
        "remaining_tokens": None,
        "utilization_percentage": None,
        "history_included": True,
    }

    session_mem = SessionMemory(max_turns=10)
    session_mem.add_turn("User 1", "AI 1")
    session_mem.add_turn("User 2", "AI 2")

    collector.set_gateway_client(mock_gw)
    collector.set_session_memory(session_mem)

    snap = collector.collect_snapshot()
    assert "ai_core" in snap
    ai_core = snap["ai_core"]

    assert ai_core["provider"] == "CoE AI Gateway"
    assert ai_core["configured_model"] == "qwen3.6"
    assert ai_core["resolved_model"] == "Qwen-35B"
    assert ai_core["session_memory_turns"] == 2
    assert ai_core["session_memory_max_turns"] == 10
    assert ai_core["session_memory_available"] is True
    assert ai_core["session_memory_status"] == "ACTIVE"
    assert ai_core["history_included"] is True
    assert ai_core["session_tokens"]["total_tokens"] == 750


def test_bridge_ai_core_state_message_serialization():
    """Verify create_ai_core_state_event produces conforming bridge JSON schema."""
    payload = {
        "runtime_state": "PROCESSING",
        "in_flight_requests": 1,
        "gateway_status": "PROCESSING",
    }
    raw_json = create_ai_core_state_event(payload, correlation_id="req_99")
    data = json.loads(raw_json)

    assert data["schema_version"] == "1.0"
    assert data["type"] == BridgeMessageType.AI_CORE_STATE.value
    assert data["correlation_id"] == "req_99"
    assert data["payload"]["runtime_state"] == "PROCESSING"
    assert data["payload"]["in_flight_requests"] == 1


def test_sanitization_no_secrets_or_prompts_in_telemetry():
    """Verify telemetry snapshots never include api_key, raw messages, or user prompts."""
    mock_openai = MagicMock()
    mock_openai.chat.completions.create.return_value = DummyCompletionResponse()
    client = CoeGatewayClient(api_key="sk-SUPER-SECRET-KEY-12345", base_url="https://test.ai/v1", model="qwen3.6", client=mock_openai)

    client.complete("Secret confidential user utterance", system_prompt="Secret system prompt")
    snap = client.get_telemetry_snapshot()
    serialized = json.dumps(snap)

    assert "SUPER-SECRET-KEY" not in serialized
    assert "confidential user utterance" not in serialized
    assert "Secret system prompt" not in serialized
    assert "sk-" not in serialized

