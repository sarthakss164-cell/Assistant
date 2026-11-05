"""
Phase D4.3 Comprehensive Test Suite — LIGHT AI Text Command Console
LIGHT AI V1.0
"""

import json
import time
import threading
from typing import Optional, Dict, Any
from unittest.mock import MagicMock, patch
import pytest

from core.assistant import LightAssistant, RequestItem
from core.state_machine import SessionState, StateMachine
from core.router import CommandRouter, IntentType, CommandIntent
from core.bridge.schema import (
    validate_incoming_message,
    create_text_command_ack_event,
    ALLOWED_INBOUND_TYPES,
    BridgeMessageType,
)
from core.bridge.server import WebSocketBridgeServer
from speech.tts import TTSEngine
from speech.listener import SpeechListener


# ==============================================================================
# Helpers and Fixtures
# ==============================================================================

def make_test_assistant(start_worker: bool = True) -> LightAssistant:
    """Creates an isolated LightAssistant with mocked hardware and audio subsystems."""
    assistant = LightAssistant.__new__(LightAssistant)
    assistant.state_machine = StateMachine()

    # Mock SpeechGate
    assistant.speech_gate = MagicMock()
    assistant.speech_gate.playback_context.return_value.__enter__ = MagicMock()
    assistant.speech_gate.playback_context.return_value.__exit__ = MagicMock()

    # Mock TTS
    assistant.tts = MagicMock(spec=TTSEngine)
    assistant.tts.speak.side_effect = lambda text: assistant._on_speech_completed(text, success=True) or True

    # Mock Listener
    assistant.listener = SpeechListener()
    assistant.listener.set_mic_active(True)

    # Mock Router
    assistant.router = CommandRouter()

    # Mock App Launcher & Music Player
    assistant.app_launcher = MagicMock()
    assistant.music_player = MagicMock()
    assistant.music_player.has_active_playlist = False
    assistant.music_player.is_playing = False

    # Mock Bridge
    assistant.bridge = MagicMock()

    # FIFO Queue & Worker Setup
    assistant._queue_capacity = 10
    import queue
    import collections
    import concurrent.futures
    assistant._request_queue = queue.Queue(maxsize=10)
    assistant._queue_shutdown_event = threading.Event()
    assistant._current_request_futures = []
    assistant._current_request_lock = threading.Lock()
    assistant._is_processing_request = False
    assistant._current_request_item = None
    assistant._processing_lock = threading.Lock()
    assistant._task_history = collections.deque(maxlen=100)
    assistant._history_lock = threading.Lock()
    assistant._has_pending_activation = False
    assistant._admission_lock = threading.Lock()
    assistant._active_utterance_staged_whatsapp = None
    assistant._shutdown_completed = False
    assistant._shutdown_finished_event = threading.Event()
    assistant._futures_lock = threading.Lock()
    assistant._active_futures = []
    assistant._queue_worker_thread = None
    assistant._last_command_text = ""
    assistant._last_command_time = 0.0

    assistant._action_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
    assistant._speech_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    if start_worker:
        assistant.start_queue_worker()
    return assistant


# ==============================================================================
# 1. Bridge Schema & Validation Tests
# ==============================================================================

def test_bridge_schema_text_command_allowed():
    """Verify text_command is registered in ALLOWED_INBOUND_TYPES and BridgeMessageType."""
    assert "text_command" in ALLOWED_INBOUND_TYPES
    assert BridgeMessageType.TEXT_COMMAND == "text_command"
    assert BridgeMessageType.TEXT_COMMAND_ACK == "text_command_ack"


def test_bridge_schema_text_command_validation_success():
    """Verify valid text_command payload passes schema validation."""
    valid_payload = {
        "schema_version": "1.0",
        "type": "text_command",
        "timestamp": 1234567.89,
        "payload": {
            "text": "play Hindi playlist",
            "request_id": "txt_101",
        },
    }
    is_valid, data, err = validate_incoming_message(json.dumps(valid_payload))
    assert is_valid is True
    assert err is None
    assert data["payload"]["text"] == "play Hindi playlist"
    assert data["payload"]["request_id"] == "txt_101"


def test_bridge_schema_text_command_validation_failures():
    """Verify validation rejects missing text, empty text, and text > 500 characters."""
    # Missing text field
    msg_missing = {
        "schema_version": "1.0",
        "type": "text_command",
        "timestamp": 1234567.89,
        "payload": {},
    }
    is_valid, _, err = validate_incoming_message(json.dumps(msg_missing))
    assert is_valid is False
    assert "Missing or empty 'text'" in err

    # Whitespace-only text
    msg_empty = {
        "schema_version": "1.0",
        "type": "text_command",
        "timestamp": 1234567.89,
        "payload": {"text": "   "},
    }
    is_valid, _, err = validate_incoming_message(json.dumps(msg_empty))
    assert is_valid is False
    assert "Missing or empty 'text'" in err

    # Text exceeding 500 characters
    msg_oversized = {
        "schema_version": "1.0",
        "type": "text_command",
        "timestamp": 1234567.89,
        "payload": {"text": "A" * 501},
    }
    is_valid, _, err = validate_incoming_message(json.dumps(msg_oversized))
    assert is_valid is False
    assert "exceeds maximum length" in err


def test_create_text_command_ack_event():
    """Verify create_text_command_ack_event formats valid serialized JSON."""
    raw_json = create_text_command_ack_event(
        request_id="req_999",
        success=True,
        status="ACCEPTED",
        message="Command queued successfully.",
    )
    parsed = json.loads(raw_json)
    assert parsed["schema_version"] == "1.0"
    assert parsed["type"] == "text_command_ack"
    assert parsed["payload"]["request_id"] == "req_999"
    assert parsed["payload"]["success"] is True
    assert parsed["payload"]["status"] == "ACCEPTED"
    assert parsed["payload"]["message"] == "Command queued successfully."


# ==============================================================================
# 2. Text Command Admission & FIFO Queue Lifecycle
# ==============================================================================

def test_text_command_admission_success():
    """Verify admit_text_command enqueues valid text and emits user utterance event."""
    with RequestItem._counter_lock:
        RequestItem._counter = 0
    assistant = make_test_assistant(start_worker=False)
    try:
        success, status, msg = assistant.admit_text_command("who are you", request_id="txt_001")
        assert success is True
        assert status == "ACCEPTED"
        assert assistant.queue_depth == 1

        # Check emitted user utterance event on bridge
        assistant.bridge.broadcast_event.assert_called()
        calls = [c[0][0] for c in assistant.bridge.broadcast_event.call_args_list]
        utt_events = [json.loads(c) for c in calls if '"user_utterance"' in str(c)]
        assert len(utt_events) >= 1
        assert utt_events[-1]["payload"]["text"] == "who are you"
        assert utt_events[-1]["correlation_id"] == 1  # item_id
    finally:
        assistant._queue_shutdown_event.set()
        assistant._action_executor.shutdown(wait=False)
        assistant._speech_executor.shutdown(wait=False)


def test_text_command_validation_rejections():
    """Verify admit_text_command rejects empty text and oversized text without enqueuing."""
    assistant = make_test_assistant()
    try:
        # Empty text
        ok1, st1, _ = assistant.admit_text_command("")
        assert ok1 is False
        assert st1 == "INVALID_INPUT"

        # Whitespace-only
        ok2, st2, _ = assistant.admit_text_command("   \t\n ")
        assert ok2 is False
        assert st2 == "INVALID_INPUT"

        # Oversized
        ok3, st3, _ = assistant.admit_text_command("X" * 501)
        assert ok3 is False
        assert st3 == "TEXT_TOO_LONG"

        assert assistant.queue_depth == 0
    finally:
        assistant._queue_shutdown_event.set()
        assistant._action_executor.shutdown(wait=False)
        assistant._speech_executor.shutdown(wait=False)


def test_text_command_queue_capacity_limit():
    """Verify queue accepts up to 10 commands and rejects the 11th with QUEUE_FULL."""
    assistant = make_test_assistant(start_worker=False)
    try:
        # Enqueue 10 commands
        for i in range(10):
            ok, st, _ = assistant.admit_text_command(f"command number {i + 1}")
            assert ok is True
            assert st == "ACCEPTED"

        assert assistant.queue_depth == 10

        # 11th command must be rejected
        ok_extra, st_extra, msg_extra = assistant.admit_text_command("one command too many")
        assert ok_extra is False
        assert st_extra == "QUEUE_FULL"
        assert "Queue is full" in msg_extra
        # TTS spoken warning triggered
        assistant.tts.speak.assert_called_with("Queue full hai, kripya thodi der baad submit karein.")
    finally:
        assistant._action_executor.shutdown(wait=False)
        assistant._speech_executor.shutdown(wait=False)


def test_text_command_shutdown_rejection():
    """Verify text commands are rejected when assistant is shutting down."""
    assistant = make_test_assistant()
    assistant._shutdown_completed = True
    try:
        ok, st, _ = assistant.admit_text_command("hello there")
        assert ok is False
        assert st == "ASSISTANT_SHUTDOWN"
    finally:
        assistant._action_executor.shutdown(wait=False)
        assistant._speech_executor.shutdown(wait=False)


# ==============================================================================
# 3. Wake-Word Isolation & Microphone State Independence
# ==============================================================================

def test_text_command_bypasses_wake_word_and_preserves_mic_isolation():
    """
    Verify Option A: Direct text commands DO NOT require 'Light' wake word,
    and DO NOT alter SessionState.WAITING_FOR_ACTIVATION, so voice input
    continues strictly requiring wake word.
    """
    assistant = make_test_assistant()
    try:
        assert assistant.state_machine.current_state == SessionState.WAITING_FOR_ACTIVATION

        # Direct text command WITHOUT wake word
        ok, st, _ = assistant.admit_text_command("who are you", wait_for_completion=True)
        assert ok is True

        # State machine MUST REMAIN WAITING_FOR_ACTIVATION
        assert assistant.state_machine.current_state == SessionState.WAITING_FOR_ACTIVATION

        # Spoken response was delivered via TTS
        assert assistant.tts.speak.call_count >= 1

        # Now test microphone voice input: without "Light" wake word, it MUST be ignored
        voice_accepted = assistant.enqueue_utterance("who are you")
        assert voice_accepted is False  # Rejected because wake word is missing!

        # With "Light" wake word, microphone voice input IS accepted
        voice_wake_accepted = assistant.enqueue_utterance("Light, who are you")
        assert voice_wake_accepted is True
    finally:
        assistant._queue_shutdown_event.set()
        assistant._action_executor.shutdown(wait=False)
        assistant._speech_executor.shutdown(wait=False)


def test_text_command_mic_mute_independence():
    """Verify text console works perfectly when microphone is muted."""
    assistant = make_test_assistant()
    try:
        # Mute microphone
        assistant.listener.set_mic_active(False)
        assert assistant.is_mic_active is False

        # Submit direct text command
        ok, st, _ = assistant.admit_text_command("who are you", wait_for_completion=True)
        assert ok is True
        assert st == "COMPLETED"

        # Assistant speaks response regardless of microphone mute state
        assert assistant.tts.speak.call_count >= 1
    finally:
        assistant._queue_shutdown_event.set()
        assistant._action_executor.shutdown(wait=False)
        assistant._speech_executor.shutdown(wait=False)


# ==============================================================================
# 4. Spoken Responses & Conversation Log Correlation
# ==============================================================================

def test_text_command_conversation_log_correlation():
    """Verify user utterance and assistant spoken events share the exact correlation ID."""
    assistant = make_test_assistant()
    try:
        # Admit and execute text command
        ok, st, _ = assistant.admit_text_command("who are you", request_id="corr_test_01", wait_for_completion=True)
        assert ok is True

        # Check broadcast events
        calls = [c[0][0] for c in assistant.bridge.broadcast_event.call_args_list]
        user_events = [json.loads(c) for c in calls if '"user_utterance"' in str(c)]
        spoken_events = [json.loads(c) for c in calls if '"assistant_spoken"' in str(c)]

        assert len(user_events) >= 1
        assert len(spoken_events) >= 1

        # The user utterance correlation_id and assistant spoken correlation_id must match item_id
        user_corr = user_events[-1].get("correlation_id")
        spoken_corr = spoken_events[-1].get("correlation_id")
        assert user_corr is not None
        assert spoken_corr is not None
        assert user_corr == spoken_corr
    finally:
        assistant._queue_shutdown_event.set()
        assistant._action_executor.shutdown(wait=False)
        assistant._speech_executor.shutdown(wait=False)


# ==============================================================================
# 5. Direct Music & Gateway Routing via Text
# ==============================================================================

def test_direct_music_command_via_text():
    """Verify typed music command 'pause music' routes directly without wake word."""
    assistant = make_test_assistant()
    try:
        ok, st, _ = assistant.admit_text_command("pause music", wait_for_completion=True)
        assert ok is True
        assert st == "COMPLETED"
        # MusicPlayer pause_music or pause was invoked
        assert assistant.music_player.pause.called or assistant.music_player.pause_music.called
    finally:
        assistant._queue_shutdown_event.set()
        assistant._action_executor.shutdown(wait=False)
        assistant._speech_executor.shutdown(wait=False)


def test_unknown_text_command_produces_spoken_feedback():
    """Verify unknown typed command does not fail silently; produces Hinglish TTS feedback."""
    assistant = make_test_assistant()
    try:
        assert assistant.state_machine.current_state == SessionState.WAITING_FOR_ACTIVATION

        # Unrecognized typed text
        ok, st, _ = assistant.admit_text_command("asdfghjkl qwertyuiop", wait_for_completion=True)
        assert ok is True

        # TTS was called with helpful failure message
        spoken_calls = [c[0][0] for c in assistant.tts.speak.call_args_list]
        assert any("Maaf kijiye, mujhe yeh command samajh nahi aayi." in s for s in spoken_calls)
    finally:
        assistant._queue_shutdown_event.set()
        assistant._action_executor.shutdown(wait=False)
        assistant._speech_executor.shutdown(wait=False)


# ==============================================================================
# 6. WebSocket Bridge Server Integration
# ==============================================================================

def test_bridge_server_handle_text_command():
    """Verify WebSocketBridgeServer._handle_text_command dispatches to assistant."""
    import asyncio
    assistant = make_test_assistant()
    server = WebSocketBridgeServer.__new__(WebSocketBridgeServer)
    server._assistant = assistant
    try:
        payload = {"text": "who are you", "request_id": "ws_txt_001"}
        res = asyncio.run(server._handle_text_command(payload))
        assert res["success"] is True
        assert res["status"] == "ACCEPTED"
        assert res["request_id"] == "ws_txt_001"
    finally:
        assistant._queue_shutdown_event.set()
        assistant._action_executor.shutdown(wait=False)
        assistant._speech_executor.shutdown(wait=False)


def test_bridge_server_handle_text_command_no_assistant():
    """Verify WebSocketBridgeServer gracefully handles missing assistant."""
    import asyncio
    server = WebSocketBridgeServer.__new__(WebSocketBridgeServer)
    server._assistant = None

    payload = {"text": "who are you", "request_id": "ws_txt_002"}
    res = asyncio.run(server._handle_text_command(payload))
    assert res["success"] is False
    assert res["status"] == "ASSISTANT_UNAVAILABLE"
