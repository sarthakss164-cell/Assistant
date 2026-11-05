"""
Unit and integration tests for LIGHT AI local WebSocket bridge and telemetry collector.
Verifies schema enforcement, security restrictions, non-blocking telemetry collection,
battery fallback handling, and graceful server lifecycle.
"""

import asyncio
import json
import os
import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from aiohttp import ClientSession, WSMsgType

from core.bridge.schema import (
    SCHEMA_VERSION,
    ALLOWED_INBOUND_TYPES,
    BridgeMessageType,
    create_error_message,
    create_message,
    create_status_message,
    create_telemetry_message,
    validate_incoming_message,
)
from core.bridge.telemetry import TelemetryCollector
from core.bridge.server import WebSocketBridgeServer


# =============================================================================
# 1. SCHEMA AND VALIDATION TESTS
# =============================================================================

def test_schema_version_and_allowed_types():
    assert SCHEMA_VERSION == "1.0"
    assert "ping" in ALLOWED_INBOUND_TYPES
    assert "status" in ALLOWED_INBOUND_TYPES
    assert "execute" not in ALLOWED_INBOUND_TYPES
    assert "shell" not in ALLOWED_INBOUND_TYPES


def test_create_messages():
    # Telemetry
    raw_telemetry = create_telemetry_message({"test_key": 42})
    data = json.loads(raw_telemetry)
    assert data["schema_version"] == "1.0"
    assert data["type"] == "telemetry"
    assert data["payload"]["test_key"] == 42
    assert "timestamp" in data

    # Error
    raw_error = create_error_message("TEST_ERR", "Something broke")
    err_data = json.loads(raw_error)
    assert err_data["type"] == "error"
    assert err_data["payload"]["code"] == "TEST_ERR"

    # Status
    raw_status = create_status_message("ONLINE", {"detail": "ok"})
    st_data = json.loads(raw_status)
    assert st_data["type"] == "status"
    assert st_data["payload"]["status"] == "ONLINE"


def test_validate_incoming_message_valid():
    valid_ping = json.dumps({
        "schema_version": "1.0",
        "type": "ping",
        "payload": {},
    })
    is_valid, parsed, err = validate_incoming_message(valid_ping)
    assert is_valid is True
    assert parsed["type"] == "ping"
    assert err is None


def test_validate_incoming_message_prohibited_and_malformed():
    # Empty
    is_valid, _, err = validate_incoming_message("")
    assert is_valid is False
    assert "Empty" in err

    # Malformed JSON
    is_valid, _, err = validate_incoming_message("{not_json")
    assert is_valid is False
    assert "Invalid JSON" in err

    # Prohibited command execution attempt
    prohibited = json.dumps({
        "schema_version": "1.0",
        "type": "run_command",
        "payload": {"cmd": "calc.exe"},
    })
    is_valid, _, err = validate_incoming_message(prohibited)
    assert is_valid is False
    assert "Unsupported or prohibited" in err

    # Wrong version
    wrong_version = json.dumps({
        "schema_version": "9.9",
        "type": "ping",
        "payload": {},
    })
    is_valid, _, err = validate_incoming_message(wrong_version)
    assert is_valid is False
    assert "Unsupported schema_version" in err


# =============================================================================
# 2. TELEMETRY COLLECTOR TESTS
# =============================================================================

def test_telemetry_collector_metrics():
    collector = TelemetryCollector(history_length=20)
    metrics = collector.get_system_metrics()

    required_keys = [
        "ram_used_gb", "ram_total_gb", "ram_percent",
        "cpu_percent", "cpu_history",
        "storage_used_gb", "storage_total_gb", "storage_percent", "storage_drive",
        "battery_percent", "battery_charging", "has_battery",
    ]
    for key in required_keys:
        assert key in metrics, f"Missing required telemetry key: {key}"

    assert isinstance(metrics["cpu_history"], list)
    assert len(metrics["cpu_history"]) == 20
    assert metrics["ram_total_gb"] > 0
    assert metrics["storage_total_gb"] > 0


def test_telemetry_collector_missing_battery():
    collector = TelemetryCollector()
    with patch("psutil.sensors_battery", return_value=None):
        metrics = collector.get_system_metrics()
        assert metrics["has_battery"] is False
        assert metrics["battery_percent"] is None
        assert metrics["battery_charging"] is True  # AC power


def test_telemetry_collector_with_battery():
    collector = TelemetryCollector()
    mock_batt = MagicMock()
    mock_batt.percent = 84.5
    mock_batt.power_plugged = False

    with patch("psutil.sensors_battery", return_value=mock_batt):
        metrics = collector.get_system_metrics()
        assert metrics["has_battery"] is True
        assert metrics["battery_percent"] == 84.5
        assert metrics["battery_charging"] is False


def test_process_watcher_data():
    collector = TelemetryCollector()
    proc_data = collector.get_process_watcher_data()

    assert "foreground_app" in proc_data
    assert "active_process" in proc_data
    assert "tool_latency_ms" in proc_data
    assert isinstance(proc_data["tool_latency_ms"], int)
    assert proc_data["tool_latency_ms"] >= 0


def test_collect_snapshot():
    collector = TelemetryCollector()
    snapshot = collector.collect_snapshot()
    assert "system_metrics" in snapshot
    assert "process_watcher" in snapshot


# =============================================================================
# 3. BRIDGE SERVER LIFECYCLE AND SECURITY TESTS
# =============================================================================

def test_assistant_bridge_shutdown():
    """
    Verifies that LightAssistant._shutdown_internal cleanly calls bridge.stop().
    """
    from core.assistant import LightAssistant

    mock_bridge = MagicMock()
    assistant = LightAssistant(bridge=mock_bridge)
    assert assistant.bridge is mock_bridge

    assistant._shutdown_internal(farewell_message="")
    mock_bridge.stop.assert_called_once()


def test_bridge_server_async_client_flow():
    """
    Spins up bridge on test port (8766), connects client, verifies snapshot,
    ping/pong, and clean shutdown.
    """
    async def _run_test():
        test_port = 8766
        server = WebSocketBridgeServer(host="127.0.0.1", port=test_port, telemetry_interval=0.2)
        started = server.start()
        assert started is True
        assert server.is_running is True

        try:
            async with ClientSession() as session:
                async with session.ws_connect(f"http://127.0.0.1:{test_port}/ws") as ws:
                    # Give server thread a few milliseconds to record connection in self._clients
                    for _ in range(50):
                        if server.client_count > 0:
                            break
                        await asyncio.sleep(0.02)
                    assert server.client_count == 1

                    # 1. Verify immediate initial telemetry snapshot
                    msg = await ws.receive(timeout=3.0)
                    assert msg.type == WSMsgType.TEXT
                    data = json.loads(msg.data)
                    assert data["type"] == "telemetry"
                    assert "system_metrics" in data["payload"]
                    assert "process_watcher" in data["payload"]

                    # 2. Send ping, verify pong
                    ping_msg = json.dumps({
                        "schema_version": "1.0",
                        "type": "ping",
                        "payload": {},
                    })
                    await ws.send_str(ping_msg)
                    resp = await ws.receive(timeout=3.0)
                    assert resp.type == WSMsgType.TEXT
                    pong_data = json.loads(resp.data)
                    assert pong_data["type"] == "pong"

                    # 3. Send prohibited type, verify error
                    bad_msg = json.dumps({
                        "schema_version": "1.0",
                        "type": "malicious_command",
                        "payload": {},
                    })
                    await ws.send_str(bad_msg)
                    err_resp = await ws.receive(timeout=3.0)
                    assert err_resp.type == WSMsgType.TEXT
                    err_data = json.loads(err_resp.data)
                    assert err_data["type"] == "error"
                    assert err_data["payload"]["code"] == "INVALID_MESSAGE"

        finally:
            server.stop()
            assert server.is_running is False
            assert server.client_count == 0

    asyncio.run(_run_test())
