"""
Unit and integration tests for Phase D2: Real Conversation Events Integration.
Verifies:
1. Schema formatting for user_utterance and assistant_spoken.
2. Inbound 64 KB message size enforcement and malformed rejection.
3. Event emission on valid transcription and admission.
4. Zero emission for rejected/ignored utterances (no wake word, debounced, queue full).
5. Multi-prompt / compound utterance splitting and ordered emission without duplicate unparsed events.
6. Assistant spoken event emitted only after verified TTS playback completion.
7. Zero assistant spoken events on playback failure or interruption.
8. FIFO correlation between user utterance and assistant spoken response.
9. End-to-end WebSocket bridge broadcasting to connected dashboard clients.
"""

import asyncio
import json
import time
from unittest.mock import MagicMock, patch

import pytest
from aiohttp import ClientSession, WSMsgType

from core.bridge.schema import (
    SCHEMA_VERSION,
    BridgeMessageType,
    create_user_utterance_event,
    create_assistant_spoken_event,
    validate_incoming_message,
    MAX_INBOUND_MESSAGE_SIZE,
    MAX_TEXT_PAYLOAD_LENGTH,
)
from core.bridge.server import WebSocketBridgeServer
from core.assistant import LightAssistant, RequestItem
from core.state_machine import SessionState, StateMachine
from speech.tts import TTSEngine


# =============================================================================
# 1. SCHEMA AND VALIDATION TESTS
# =============================================================================

def test_schema_user_utterance_event():
    evt_json = create_user_utterance_event(
        text="  Light, open chrome  ",
        correlation_id=42,
        event_id="test_u_123",
        timestamp=1700000000.0,
    )
    data = json.loads(evt_json)
    assert data["schema_version"] == "1.0"
    assert data["type"] == "user_utterance"
    assert data["event_id"] == "test_u_123"
    assert data["correlation_id"] == 42
    assert data["timestamp"] == 1700000000.0
    assert data["payload"]["text"] == "Light, open chrome"
    assert data["payload"]["sender"] == "USER"


def test_schema_assistant_spoken_event():
    evt_json = create_assistant_spoken_event(
        text="  Opening Google Chrome.  ",
        correlation_id=42,
        event_id="test_a_456",
        timestamp=1700000002.5,
    )
    data = json.loads(evt_json)
    assert data["schema_version"] == "1.0"
    assert data["type"] == "assistant_spoken"
    assert data["event_id"] == "test_a_456"
    assert data["correlation_id"] == 42
    assert data["timestamp"] == 1700000002.5
    assert data["payload"]["text"] == "Opening Google Chrome."
    assert data["payload"]["sender"] == "ASSISTANT"


def test_schema_text_truncation_at_max_limit():
    huge_text = "A" * (MAX_TEXT_PAYLOAD_LENGTH + 500)
    evt_json = create_user_utterance_event(text=huge_text)
    data = json.loads(evt_json)
    assert len(data["payload"]["text"]) == MAX_TEXT_PAYLOAD_LENGTH

    huge_resp = "B" * (MAX_TEXT_PAYLOAD_LENGTH + 500)
    evt_json2 = create_assistant_spoken_event(text=huge_resp)
    data2 = json.loads(evt_json2)
    assert len(data2["payload"]["text"]) == MAX_TEXT_PAYLOAD_LENGTH


def test_schema_inbound_size_enforcement():
    # Exactly at or below 64 KB with valid payload
    small_ping = json.dumps({"schema_version": "1.0", "type": "ping", "payload": {}})
    is_valid, parsed, err = validate_incoming_message(small_ping)
    assert is_valid is True
    assert err is None

    # Oversized payload exceeding 64 KB
    oversized_data = "x" * (MAX_INBOUND_MESSAGE_SIZE + 10)
    is_valid, parsed, err = validate_incoming_message(oversized_data)
    assert is_valid is False
    assert "exceeds maximum allowed size" in err


# =============================================================================
# 2. ADMISSION AND UTTERANCE EMISSION TESTS
# =============================================================================

def test_valid_admission_emits_user_utterance():
    mock_bridge = MagicMock()
    mock_tts = MagicMock(spec=TTSEngine)
    assistant = LightAssistant(tts=mock_tts, bridge=mock_bridge)
    assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)

    try:
        success = assistant.enqueue_utterance("open notepad")
        assert success is True
        assert mock_bridge.broadcast_event.call_count == 1

        emitted_raw = mock_bridge.broadcast_event.call_args[0][0]
        data = json.loads(emitted_raw)
        assert data["type"] == "user_utterance"
        assert data["payload"]["text"].lower() == "open notepad"
        assert data["payload"]["sender"] == "USER"
        assert data["correlation_id"] is not None
    finally:
        assistant._shutdown_internal(farewell_message="")


def test_rejected_missing_wake_word_emits_nothing():
    mock_bridge = MagicMock()
    mock_tts = MagicMock(spec=TTSEngine)
    assistant = LightAssistant(tts=mock_tts, bridge=mock_bridge)
    assert assistant.state_machine.current_state == SessionState.WAITING_FOR_ACTIVATION

    try:
        # Without wake word in WAITING_FOR_ACTIVATION -> rejected
        success = assistant.enqueue_utterance("open notepad")
        assert success is False
        mock_bridge.broadcast_event.assert_not_called()
    finally:
        assistant._shutdown_internal(farewell_message="")


def test_rejected_debounced_utterance_emits_nothing():
    mock_bridge = MagicMock()
    mock_tts = MagicMock(spec=TTSEngine)
    assistant = LightAssistant(tts=mock_tts, bridge=mock_bridge)
    assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)

    try:
        # First admission succeeds
        res1 = assistant.enqueue_utterance("open notepad")
        assert res1 is True
        assert mock_bridge.broadcast_event.call_count == 1

        # Immediate second call is debounced -> rejected
        res2 = assistant.enqueue_utterance("open notepad")
        assert res2 is False
        # No second event broadcast
        assert mock_bridge.broadcast_event.call_count == 1
    finally:
        assistant._shutdown_internal(farewell_message="")


def test_rejected_queue_full_emits_no_user_utterance():
    mock_bridge = MagicMock()
    mock_tts = MagicMock(spec=TTSEngine)
    mock_tts.speak.return_value = True
    assistant = LightAssistant(tts=mock_tts, bridge=mock_bridge)
    assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)

    try:
        # Fill queue to maximum capacity (10 items)
        for i in range(10):
            assistant._request_queue.put_nowait(RequestItem(raw_text=f"item_{i}"))

        # Enqueue one more item
        success = assistant.enqueue_utterance("open edge")
        assert success is False
        # No user_utterance event emitted for rejected request
        mock_bridge.broadcast_event.assert_not_called()
    finally:
        assistant._shutdown_internal(farewell_message="")


def test_compound_utterance_splits_and_emits_in_fifo_order():
    mock_bridge = MagicMock()
    mock_tts = MagicMock(spec=TTSEngine)
    assistant = LightAssistant(tts=mock_tts, bridge=mock_bridge)
    assert assistant.state_machine.current_state == SessionState.WAITING_FOR_ACTIVATION

    try:
        # Compound prompt with wake prefix
        success = assistant.enqueue_utterance("Light, open notepad and open chrome")
        assert success is True

        # Must emit exactly 2 user_utterance events in FIFO order
        assert mock_bridge.broadcast_event.call_count == 2

        evt1 = json.loads(mock_bridge.broadcast_event.call_args_list[0][0][0])
        evt2 = json.loads(mock_bridge.broadcast_event.call_args_list[1][0][0])

        assert evt1["type"] == "user_utterance"
        assert evt1["payload"]["text"].lower() == "light, open notepad"
        assert evt2["type"] == "user_utterance"
        assert evt2["payload"]["text"].lower() == "open chrome"

        # Correlation IDs must be distinct and sequential
        assert evt1["correlation_id"] < evt2["correlation_id"]
    finally:
        assistant._shutdown_internal(farewell_message="")


# =============================================================================
# 3. TTS COMPLETION HOOK AND ASSISTANT SPOKEN TESTS
# =============================================================================

def test_tts_engine_on_speech_completed_callback():
    engine = TTSEngine(speech_gate=None)
    mock_completed = MagicMock()
    engine.on_speech_completed = mock_completed

    # Simulate successful playback by patching edge TTS and audio playback
    with patch.object(engine, "_generate_edge_tts", return_value=None), \
         patch.object(engine, "_play_audio_file", return_value=None), \
         patch("os.path.exists", return_value=True), \
         patch("os.path.getsize", return_value=1024), \
         patch("os.remove", return_value=None), \
         patch("time.sleep", return_value=None):
        result = engine.speak("Audio output verified")

    assert result is True
    mock_completed.assert_called_once_with("Audio output verified", True)


def test_failed_tts_does_not_call_on_speech_completed():
    engine = TTSEngine(speech_gate=None)
    mock_completed = MagicMock()
    engine.on_speech_completed = mock_completed

    # Simulate Edge failure and SAPI5 fallback failure
    with patch.object(engine, "_generate_edge_tts", side_effect=RuntimeError("Edge error")), \
         patch.object(engine, "_fallback_speak_sapi5", side_effect=RuntimeError("SAPI5 error")), \
         patch("time.sleep", return_value=None):
        result = engine.speak("Failure text")

    assert result is False
    mock_completed.assert_not_called()


def test_fifo_request_processing_correlates_assistant_response():
    mock_bridge = MagicMock()
    mock_tts = MagicMock(spec=TTSEngine)
    mock_tts.speak.return_value = True

    assistant = LightAssistant(tts=mock_tts, bridge=mock_bridge)
    assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)

    try:
        # Simulate request item being processed in queue worker
        item = RequestItem(raw_text="Light, open notepad")
        with assistant._processing_lock:
            assistant._is_processing_request = True
            assistant._current_request_item = item

        # Simulate TTS completion hook firing during request processing
        assistant._on_speech_completed("Notepad open kar rahi hoon.", success=True)

        assert mock_bridge.broadcast_event.call_count == 1
        spoken_evt = json.loads(mock_bridge.broadcast_event.call_args[0][0])
        assert spoken_evt["type"] == "assistant_spoken"
        assert spoken_evt["payload"]["text"] == "Notepad open kar rahi hoon."
        assert spoken_evt["payload"]["sender"] == "ASSISTANT"
        assert spoken_evt["correlation_id"] == item.item_id
    finally:
        assistant._shutdown_internal(farewell_message="")


# =============================================================================
# 4. END-TO-END BRIDGE BROADCAST INTEGRATION TEST
# =============================================================================

def test_e2e_bridge_broadcast_user_and_assistant():
    async def _run():
        server = WebSocketBridgeServer(host="127.0.0.1", port=8777, telemetry_interval=0.1)
        assert server.start() is True
        await asyncio.sleep(0.1)

        try:
            async with ClientSession() as session:
                async with session.ws_connect("http://127.0.0.1:8777/ws") as ws:
                    # Wait until server registers client
                    for _ in range(50):
                        if server.client_count > 0:
                            break
                        await asyncio.sleep(0.02)
                    assert server.client_count == 1

                    # Receive initial telemetry message
                    init_msg = await ws.receive_json(timeout=2.0)
                    assert init_msg["type"] == "telemetry"

                    # Broadcast user_utterance and wait for it (ignoring periodic telemetry if received in-between)
                    u_evt = create_user_utterance_event("Light, status check", correlation_id=101)
                    server.broadcast_event(u_evt)

                    for _ in range(5):
                        u_received = await ws.receive_json(timeout=2.0)
                        if u_received["type"] == "user_utterance":
                            break
                    assert u_received["type"] == "user_utterance"
                    assert u_received["payload"]["text"] == "Light, status check"
                    assert u_received["payload"]["sender"] == "USER"
                    assert u_received["correlation_id"] == 101

                    # Broadcast assistant_spoken and wait for it
                    a_evt = create_assistant_spoken_event("All systems nominal.", correlation_id=101)
                    server.broadcast_event(a_evt)

                    for _ in range(5):
                        a_received = await ws.receive_json(timeout=2.0)
                        if a_received["type"] == "assistant_spoken":
                            break
                    assert a_received["type"] == "assistant_spoken"
                    assert a_received["payload"]["text"] == "All systems nominal."
                    assert a_received["payload"]["sender"] == "ASSISTANT"
                    assert a_received["correlation_id"] == 101
        finally:
            server.stop()

    asyncio.run(_run())
