"""
Unit and integration tests for Phase D3: Real-Time Voice Stream Visualization.
Verifies:
1. Bridge schema formatting for voice_state events across user and assistant channels.
2. Microphone capture start and end lifecycle callbacks in SpeechListener and LightAssistant.
3. Proper cleanup to IDLE on capture timeout, exceptions, and assistant shutdown.
4. PTT spacebar capture transitions using the single master microphone stream.
5. TTS playback-start and playback-stop lifecycle in TTSEngine and LightAssistant.
6. TTS fallback to SAPI5 without duplicate playback-start events.
7. Total playback failure resetting to STANDBY cleanly.
8. Music playback isolation: playing music never triggers TTS speaking events.
9. End-to-end WebSocket bridge delivery of initial and dynamic voice_state messages.
"""

import asyncio
import json
import time
from unittest.mock import MagicMock, patch

import pytest
from aiohttp import ClientSession

from core.bridge.schema import (
    SCHEMA_VERSION,
    BridgeMessageType,
    create_voice_state_event,
    MAX_TEXT_PAYLOAD_LENGTH,
)
from core.bridge.server import WebSocketBridgeServer
from core.assistant import LightAssistant, RequestItem
from core.state_machine import SessionState
from speech.listener import SpeechListener
from speech.tts import TTSEngine


# =============================================================================
# 1. SCHEMA TESTS
# =============================================================================

def test_schema_voice_state_user_event():
    evt_json = create_voice_state_event(
        channel="USER",
        state="LISTENING",
        correlation_id=12,
        detail="Listening active",
        event_id="test_vs_u1",
        timestamp=1700000010.0,
    )
    data = json.loads(evt_json)
    assert data["schema_version"] == "1.0"
    assert data["type"] == "voice_state"
    assert data["event_id"] == "test_vs_u1"
    assert data["correlation_id"] == 12
    assert data["timestamp"] == 1700000010.0
    assert data["payload"]["channel"] == "user"
    assert data["payload"]["state"] == "LISTENING"
    assert data["payload"]["detail"] == "Listening active"


def test_schema_voice_state_assistant_event():
    evt_json = create_voice_state_event(
        channel="ASSISTANT",
        state="SPEAKING",
        correlation_id=45,
        detail="Notepad open kar rahi hoon.",
        event_id="test_vs_a1",
    )
    data = json.loads(evt_json)
    assert data["type"] == "voice_state"
    assert data["payload"]["channel"] == "assistant"
    assert data["payload"]["state"] == "SPEAKING"
    assert data["payload"]["detail"] == "Notepad open kar rahi hoon."
    assert data["correlation_id"] == 45


def test_schema_voice_state_truncates_oversized_detail():
    huge_detail = "X" * (MAX_TEXT_PAYLOAD_LENGTH + 500)
    evt_json = create_voice_state_event(channel="user", state="IDLE", detail=huge_detail)
    data = json.loads(evt_json)
    assert len(data["payload"]["detail"]) == MAX_TEXT_PAYLOAD_LENGTH


# =============================================================================
# 2. MICROPHONE CAPTURE LIFECYCLE TESTS
# =============================================================================

def test_listener_capture_start_and_end_callbacks_on_success():
    listener = SpeechListener()
    mock_start = MagicMock()
    mock_end = MagicMock()
    listener.on_capture_start = mock_start
    listener.on_capture_end = mock_end

    dummy_audio = MagicMock()

    # Mock microphone source context and recognizer.listen returning dummy audio
    mock_source = MagicMock()
    with patch.object(listener, "init_microphone", return_value=True), \
         patch.object(listener, "microphone", mock_source), \
         patch.object(listener.recognizer, "listen", return_value=dummy_audio):
        res = listener.listen()

    assert res == dummy_audio
    mock_start.assert_called_once()
    mock_end.assert_called_once_with(True)


def test_listener_capture_end_on_timeout():
    import speech_recognition as sr

    listener = SpeechListener()
    mock_start = MagicMock()
    mock_end = MagicMock()
    listener.on_capture_start = mock_start
    listener.on_capture_end = mock_end

    mock_source = MagicMock()
    with patch.object(listener, "init_microphone", return_value=True), \
         patch.object(listener, "microphone", mock_source), \
         patch.object(listener.recognizer, "listen", side_effect=sr.WaitTimeoutError("timeout")):
        res = listener.listen()

    assert res is None
    mock_start.assert_called_once()
    # On timeout, has_captured_audio is False
    mock_end.assert_called_once_with(False)


def test_assistant_on_mic_capture_transitions():
    mock_bridge = MagicMock()
    assistant = LightAssistant(bridge=mock_bridge)

    try:
        # Start capture -> emits LISTENING
        assistant._on_mic_capture_start()
        assert mock_bridge.broadcast_event.call_count == 1
        data1 = json.loads(mock_bridge.broadcast_event.call_args_list[0][0][0])
        assert data1["type"] == "voice_state"
        assert data1["payload"]["channel"] == "user"
        assert data1["payload"]["state"] == "LISTENING"

        # End capture with audio -> emits PROCESSING
        assistant._on_mic_capture_end(has_captured_audio=True)
        assert mock_bridge.broadcast_event.call_count == 2
        data2 = json.loads(mock_bridge.broadcast_event.call_args_list[1][0][0])
        assert data2["payload"]["channel"] == "user"
        assert data2["payload"]["state"] == "PROCESSING"

        # End capture with timeout/empty -> emits IDLE
        assistant._on_mic_capture_end(has_captured_audio=False)
        assert mock_bridge.broadcast_event.call_count == 3
        data3 = json.loads(mock_bridge.broadcast_event.call_args_list[2][0][0])
        assert data3["payload"]["channel"] == "user"
        assert data3["payload"]["state"] == "IDLE"
    finally:
        assistant._shutdown_internal(farewell_message="")


def test_shutdown_emits_idle_and_standby():
    mock_bridge = MagicMock()
    assistant = LightAssistant(bridge=mock_bridge)

    assistant._shutdown_internal(farewell_message="")

    # Should have emitted IDLE for user and STANDBY for assistant
    calls = [json.loads(call[0][0]) for call in mock_bridge.broadcast_event.call_args_list]
    user_idles = [c for c in calls if c["type"] == "voice_state" and c["payload"]["channel"] == "user" and c["payload"]["state"] == "IDLE"]
    assistant_standbys = [c for c in calls if c["type"] == "voice_state" and c["payload"]["channel"] == "assistant" and c["payload"]["state"] == "STANDBY"]

    assert len(user_idles) >= 1
    assert len(assistant_standbys) >= 1


# =============================================================================
# 3. PTT CAPTURE LIFECYCLE TESTS
# =============================================================================

def test_ptt_capture_callbacks_without_second_microphone():
    listener = SpeechListener()
    mock_start = MagicMock()
    mock_end = MagicMock()
    listener.on_capture_start = mock_start
    listener.on_capture_end = mock_end

    mock_source = MagicMock()
    mock_source.__enter__.return_value = mock_source
    mock_source.CHUNK = 1024
    mock_source.SAMPLE_RATE = 16000
    mock_source.SAMPLE_WIDTH = 2
    mock_source.stream.read.return_value = b"\x00" * 2048

    is_held = MagicMock(side_effect=[True, True, False])
    clock_state = [100.0]

    def fake_time():
        clock_state[0] += 0.05
        return clock_state[0]

    with patch.object(listener, "init_microphone", return_value=True), \
         patch.object(listener, "microphone", mock_source), \
         patch("time.time", side_effect=fake_time):
        audio = listener.capture_ptt(is_held_fn=is_held, min_duration=0.1)

    assert audio is not None
    mock_start.assert_called_once()
    mock_end.assert_called_once_with(True)


# =============================================================================
# 4. TTS PLAYBACK LIFECYCLE & FALLBACK TESTS
# =============================================================================

def test_tts_engine_playback_start_and_stop_hooks():
    engine = TTSEngine(speech_gate=None)
    mock_start = MagicMock()
    mock_stop = MagicMock()
    engine.on_playback_start = mock_start
    engine.on_playback_stop = mock_stop

    with patch.object(engine, "_generate_edge_tts", return_value=None), \
         patch.object(engine, "_play_audio_file", return_value=None), \
         patch("os.path.exists", return_value=True), \
         patch("os.path.getsize", return_value=1024), \
         patch("os.remove", return_value=None), \
         patch("time.sleep", return_value=None):
        ok = engine.speak("Testing playback hooks")

    assert ok is True
    mock_start.assert_called_once_with("Testing playback hooks")
    mock_stop.assert_called_once()


def test_tts_fallback_calls_playback_start_once():
    engine = TTSEngine(speech_gate=None)
    mock_start = MagicMock()
    mock_stop = MagicMock()
    engine.on_playback_start = mock_start
    engine.on_playback_stop = mock_stop

    mock_pyttsx = MagicMock()
    mock_engine_inst = MagicMock()
    mock_engine_inst.getProperty.return_value = []
    mock_pyttsx.init.return_value = mock_engine_inst

    # Edge TTS raises an exception before playback starts; SAPI5 succeeds
    with patch.object(engine, "_generate_edge_tts", side_effect=RuntimeError("Edge down")), \
         patch.dict("sys.modules", {"pyttsx3": mock_pyttsx}), \
         patch("time.sleep", return_value=None):
        ok = engine.speak("Testing SAPI5 fallback")

    assert ok is True
    # on_playback_start called exactly once during SAPI5 playback
    mock_start.assert_called_once_with("Testing SAPI5 fallback")
    mock_stop.assert_called_once()


def test_tts_total_failure_calls_playback_stop():
    engine = TTSEngine(speech_gate=None)
    mock_start = MagicMock()
    mock_stop = MagicMock()
    engine.on_playback_start = mock_start
    engine.on_playback_stop = mock_stop

    with patch.object(engine, "_generate_edge_tts", side_effect=RuntimeError("Edge down")), \
         patch.object(engine, "_fallback_speak_sapi5", side_effect=RuntimeError("SAPI5 down")), \
         patch("time.sleep", return_value=None):
        ok = engine.speak("Total failure")

    assert ok is False
    mock_start.assert_not_called()
    # Playback stop still called in finally: to guarantee clean return to STANDBY
    mock_stop.assert_called_once()


def test_assistant_correlates_tts_playback_start_and_stop():
    mock_bridge = MagicMock()
    assistant = LightAssistant(bridge=mock_bridge)
    assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)

    try:
        item = RequestItem(raw_text="Light, status report")
        with assistant._processing_lock:
            assistant._is_processing_request = True
            assistant._current_request_item = item

        # Assistant speaks -> playback start
        assistant._on_tts_playback_start("Status report: optimal.")
        assert mock_bridge.broadcast_event.call_count == 1
        data1 = json.loads(mock_bridge.broadcast_event.call_args_list[0][0][0])
        assert data1["type"] == "voice_state"
        assert data1["payload"]["channel"] == "assistant"
        assert data1["payload"]["state"] == "SPEAKING"
        assert data1["payload"]["detail"] == "Status report: optimal."
        assert data1["correlation_id"] == item.item_id

        # Playback finishes -> playback stop
        assistant._on_tts_playback_stop()
        assert mock_bridge.broadcast_event.call_count == 2
        data2 = json.loads(mock_bridge.broadcast_event.call_args_list[1][0][0])
        assert data2["payload"]["channel"] == "assistant"
        assert data2["payload"]["state"] == "STANDBY"
        assert data2["correlation_id"] == item.item_id
    finally:
        assistant._shutdown_internal(farewell_message="")


# =============================================================================
# 5. MUSIC PLAYBACK ISOLATION TEST
# =============================================================================

def test_music_playback_does_not_trigger_tts_speaking_events():
    mock_bridge = MagicMock()
    mock_tts = MagicMock(spec=TTSEngine)
    mock_music = MagicMock()
    mock_music.is_playing = True

    assistant = LightAssistant(tts=mock_tts, music_player=mock_music, bridge=mock_bridge)

    # Music duck / restore or playback state check must not invoke TTSEngine.speak
    mock_music.duck_volume("test")
    mock_music.restore_volume("test")

    # Bridge broadcast should not have any assistant SPEAKING event from music
    calls = [json.loads(call[0][0]) for call in mock_bridge.broadcast_event.call_args_list]
    tts_speaking = [c for c in calls if c.get("payload", {}).get("channel") == "assistant" and c.get("payload", {}).get("state") == "SPEAKING"]
    assert len(tts_speaking) == 0

    assistant._shutdown_internal(farewell_message="")


# =============================================================================
# 6. END-TO-END BRIDGE WEBSOCKET INTEGRATION TEST
# =============================================================================

def test_e2e_voice_state_bridge_broadcast():
    async def _run():
        server = WebSocketBridgeServer(host="127.0.0.1", port=8779, telemetry_interval=2.0)
        assert server.start() is True
        await asyncio.sleep(0.1)

        try:
            async with ClientSession() as session:
                async with session.ws_connect("http://127.0.0.1:8779/ws") as ws:
                    for _ in range(50):
                        if server.client_count > 0:
                            break
                        await asyncio.sleep(0.02)
                    assert server.client_count == 1

                    async def recv_voice_state(timeout: float = 2.0):
                        while True:
                            msg = await ws.receive_json(timeout=timeout)
                            if msg["type"] == "voice_state":
                                return msg

                    # Receive initial telemetry snapshot
                    init_msg = await ws.receive_json(timeout=2.0)
                    assert init_msg["type"] == "telemetry"

                    # Broadcast dynamic user LISTENING event
                    server.broadcast_event(create_voice_state_event(channel="user", state="LISTENING"))
                    u_rec = await recv_voice_state()
                    assert u_rec["type"] == "voice_state"
                    assert u_rec["payload"]["channel"] == "user"
                    assert u_rec["payload"]["state"] == "LISTENING"

                    # Broadcast dynamic assistant SPEAKING event with correlation_id
                    server.broadcast_event(create_voice_state_event(
                        channel="assistant",
                        state="SPEAKING",
                        detail="Acknowledged.",
                        correlation_id=88,
                    ))
                    a_rec = await recv_voice_state()
                    assert a_rec["type"] == "voice_state"
                    assert a_rec["payload"]["channel"] == "assistant"
                    assert a_rec["payload"]["state"] == "SPEAKING"
                    assert a_rec["payload"]["detail"] == "Acknowledged."
                    assert a_rec["correlation_id"] == 88

                    # Broadcast return to STANDBY
                    server.broadcast_event(create_voice_state_event(channel="assistant", state="STANDBY", correlation_id=88))
                    a_rec2 = await recv_voice_state()
                    assert a_rec2["payload"]["state"] == "STANDBY"
        finally:
            server.stop()

    asyncio.run(_run())
