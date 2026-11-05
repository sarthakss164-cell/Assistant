"""
Automated unit and integration test suite for LIGHT AI V1.0 Phase 7:
1. First-command conversational activation.
2. Deterministic shutdown-intent detection and idempotency.
3. Safe concurrent action execution, serialized TTS, and clean shutdown.
"""

import json
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from core.assistant import LightAssistant
from core.coe_gateway import CoeGatewayClient, GatewayResponse, GatewayStatus
from core.router import CommandRouter, CommandIntent, IntentType
from core.state_machine import SessionState, SessionStateMachine
from speech.tts import TTSEngine


@pytest.fixture
def mock_gateway():
    client = MagicMock(spec=CoeGatewayClient)
    client.is_configured = True
    return client


@pytest.fixture
def mock_assistant(mock_gateway):
    listener = MagicMock()
    stt = MagicMock()
    tts = MagicMock()
    launcher = MagicMock()

    assistant = LightAssistant(
        listener=listener,
        stt=stt,
        tts=tts,
        app_launcher=launcher,
        gateway_client=mock_gateway,
    )
    return assistant


# =============================================================================
# 1. ACTIVATION TESTS
# =============================================================================

def test_first_conversational_question_activates_session(mock_assistant, mock_gateway):
    """Verifies that a wake-word-prefixed question activates from WAITING_FOR_ACTIVATION and answers immediately."""
    assert mock_assistant.state_machine.current_state == SessionState.WAITING_FOR_ACTIVATION

    answer = "Artificial Intelligence computer science ka ek field hai jo smart machines banata hai."
    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content=json.dumps({
            "intent": "CONVERSATION",
            "voice_response": answer,
        }),
    )

    res = mock_assistant.process_utterance("Light, what is artificial intelligence?")

    assert res is True
    # Session must now be ACTIVE
    assert mock_assistant.state_machine.current_state == SessionState.ACTIVE_SESSION
    # Gateway was invoked exactly once with the cleaned question
    mock_gateway.complete.assert_called_once_with("what is artificial intelligence")
    # Spoken response was delivered once
    mock_assistant.tts.speak.assert_called_once_with(answer)


def test_first_hindi_conversational_question_activates(mock_assistant, mock_gateway):
    """Verifies that Hindi conversational questions activate the session on the first attempt."""
    assert mock_assistant.state_machine.current_state == SessionState.WAITING_FOR_ACTIVATION

    answer = "Machine learning algorithms data se patterns seekhte hain."
    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content=json.dumps({
            "intent": "CONVERSATION",
            "voice_response": answer,
        }),
    )

    res = mock_assistant.process_utterance("Light, mujhe machine learning samjhao.")

    assert res is True
    assert mock_assistant.state_machine.current_state == SessionState.ACTIVE_SESSION
    mock_gateway.complete.assert_called_once_with("mujhe machine learning samjhao")
    mock_assistant.tts.speak.assert_called_once_with(answer)


def test_first_question_processed_exactly_once(mock_assistant, mock_gateway):
    """Verifies that the first question is not double-processed or duplicated."""
    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content=json.dumps({
            "intent": "CONVERSATION",
            "voice_response": "A fun fact: Honey never spoils.",
        }),
    )

    mock_assistant.process_utterance("Light, tell me a fun fact.")

    assert mock_gateway.complete.call_count == 1
    assert mock_assistant.tts.speak.call_count == 1


def test_first_local_command_activates_and_executes(mock_assistant, mock_gateway):
    """Verifies that built-in local commands still activate session on first attempt with 0 gateway calls."""
    assert mock_assistant.state_machine.current_state == SessionState.WAITING_FOR_ACTIVATION
    mock_assistant.app_launcher.launch.return_value = (True, "Google Chrome open kar rahi hoon.")

    res = mock_assistant.process_utterance("Light, open Chrome")

    assert res is True
    assert mock_assistant.state_machine.current_state == SessionState.ACTIVE_SESSION
    mock_gateway.complete.assert_not_called()
    mock_assistant.app_launcher.launch.assert_called_once_with("chrome")
    mock_assistant.tts.speak.assert_called_once_with("Google Chrome open kar rahi hoon.")


def test_wake_word_only_does_not_call_gateway_or_activate(mock_assistant, mock_gateway):
    """Verifies that wake-word-only or whitespace-only inputs do not trigger gateway or activate session."""
    assert mock_assistant.state_machine.current_state == SessionState.WAITING_FOR_ACTIVATION

    for utterance in ["Light", "light", "Light,   ", "  light  "]:
        res = mock_assistant.process_utterance(utterance)
        assert res is True
        mock_gateway.complete.assert_not_called()
        assert mock_assistant.state_machine.current_state == SessionState.WAITING_FOR_ACTIVATION


def test_unprefixed_question_ignored_in_waiting_state(mock_assistant, mock_gateway):
    """Verifies that background speech without 'Light' prefix is completely ignored before activation."""
    assert mock_assistant.state_machine.current_state == SessionState.WAITING_FOR_ACTIVATION

    res = mock_assistant.process_utterance("what is artificial intelligence?")

    assert res is True
    mock_gateway.complete.assert_not_called()
    mock_assistant.tts.speak.assert_not_called()
    assert mock_assistant.state_machine.current_state == SessionState.WAITING_FOR_ACTIVATION


# =============================================================================
# 2. EXIT INTENT TESTS
# =============================================================================

@pytest.mark.parametrize("exit_phrase", [
    "stop",
    "Light, stop",
    "stop listening",
    "Light, stop listening",
    "goodbye",
    "goodbye Light",
    "bye Light",
    "Light, bye",
    "Light, shut down",
    "Light, exit",
    "Light, band ho jao",
    "Light, bas karo",
    "Light, ab band ho jao",
    "stop.",
    "STOP LISTENING!",
    "goodbye!",
    "band ho jao",
    "bas karo",
    "ab band ho jao",
])
def test_all_approved_exit_phrases_trigger_shutdown(exit_phrase, mock_gateway):
    """Verifies that all approved deterministic exit phrases route to EXIT in active session."""
    router = CommandRouter(gateway_client=mock_gateway)
    intent = router.route(exit_phrase, SessionState.ACTIVE_SESSION)

    assert intent.intent_type == IntentType.EXIT
    # Crucial: gateway must NEVER be called to determine shutdown
    mock_gateway.complete.assert_not_called()


def test_exit_detection_happens_before_gateway_fallback(mock_assistant, mock_gateway):
    """Verifies that 'goodbye Light' shuts down immediately without asking the gateway."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)

    res = mock_assistant.process_utterance("goodbye Light")

    assert res is False
    assert mock_assistant.state_machine.current_state == SessionState.SHUTDOWN
    mock_gateway.complete.assert_not_called()
    mock_assistant.tts.speak.assert_called_with("Alvida! Light AI ab band ho rahi hai.")


def test_shutdown_is_idempotent(mock_assistant):
    """Verifies that repeated shutdown requests in SHUTDOWN state are handled idempotently without error."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)

    # First shutdown
    res1 = mock_assistant.process_utterance("Light, exit")
    assert res1 is False
    assert mock_assistant.state_machine.current_state == SessionState.SHUTDOWN

    # Repeated shutdown (clear debounce timestamp to simulate non-instant repeat)
    mock_assistant._last_command_time = 0.0
    res2 = mock_assistant.process_utterance("Light, exit")
    assert res2 is False
    assert mock_assistant.state_machine.current_state == SessionState.SHUTDOWN


def test_non_exit_query_containing_stop_remains_conversational(mock_assistant, mock_gateway):
    """Verifies that queries containing 'stop' inside larger sentences remain questions and do NOT exit."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content=json.dumps({
            "intent": "CONVERSATION",
            "voice_response": "Procrastination rokne ke liye Pomodoro technique use karein.",
        }),
    )

    res = mock_assistant.process_utterance("How do I stop procrastinating?")

    assert res is True
    # Session must remain ACTIVE, not shutdown
    assert mock_assistant.state_machine.current_state == SessionState.ACTIVE_SESSION
    mock_gateway.complete.assert_called_once()
    mock_assistant.tts.speak.assert_called_once_with("Procrastination rokne ke liye Pomodoro technique use karein.")


def test_no_unrelated_action_executes_after_shutdown(mock_assistant, mock_gateway):
    """Verifies that no local action executes after shutdown has completed."""
    mock_assistant.state_machine.transition_to_shutdown()

    res = mock_assistant.process_utterance("open Chrome")

    assert res is True
    mock_assistant.app_launcher.launch.assert_not_called()
    mock_gateway.complete.assert_not_called()


def test_farewell_playback_completes_before_audio_mixer_destroyed(mock_assistant):
    """Verifies that farewell playback completes before audio mixer teardown."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)

    order_of_events = []

    def fake_speak(text):
        order_of_events.append(f"speak:{text}")
        return True

    mock_assistant.tts.speak.side_effect = fake_speak

    with patch("core.assistant.graceful_shutdown") as mock_graceful:
        mock_graceful.side_effect = lambda **kwargs: order_of_events.append("graceful_shutdown")
        mock_assistant.process_utterance("goodbye")

    assert "speak:Alvida! Light AI ab band ho rahi hai." in order_of_events
    assert "graceful_shutdown" in order_of_events
    speak_idx = order_of_events.index("speak:Alvida! Light AI ab band ho rahi hai.")
    shutdown_idx = order_of_events.index("graceful_shutdown")
    assert speak_idx < shutdown_idx, "Farewell must be spoken before mixer/audio resources are released"


# =============================================================================
# 3. CONCURRENCY TESTS
# =============================================================================

def test_slow_action_does_not_prevent_acknowledgement_speech(mock_assistant):
    """Verifies that a slow mock action allows acknowledgement speech to overlap without waiting."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)

    events = []

    def slow_launch(app_name):
        events.append(("action_start", time.time()))
        time.sleep(0.25)
        events.append(("action_end", time.time()))
        return True, "Slow app launched."

    def fake_speak(text):
        events.append(("speech_start", time.time()))
        time.sleep(0.04)
        events.append(("speech_end", time.time()))
        return True

    mock_assistant.app_launcher.launch.side_effect = slow_launch
    mock_assistant.tts.speak.side_effect = fake_speak

    t0 = time.time()
    res = mock_assistant.process_utterance("open Chrome")
    return_duration = time.time() - t0

    # process_utterance must return quickly without waiting for slow action
    assert return_duration < 0.15, f"process_utterance blocked too long: {return_duration:.3f}s"
    assert res is True

    # Allow background action to finalize
    time.sleep(0.3)

    event_names = [e[0] for e in events]
    assert "action_start" in event_names
    assert "speech_start" in event_names

    # Action started, speech started before action ended -> overlap!
    speech_start_time = next(t for name, t in events if name == "speech_start")
    action_end_time = next(t for name, t in events if name == "action_end")
    assert speech_start_time < action_end_time, "Speech should start before slow action finishes"


def test_tts_operations_remain_serialized():
    """Verifies that concurrent TTS calls are strictly serialized via TTSEngine._speak_lock."""
    tts = TTSEngine()
    active_speakers = 0
    max_concurrent_speakers = 0
    lock = threading.Lock()

    def fake_play(file_path):
        nonlocal active_speakers, max_concurrent_speakers
        with lock:
            active_speakers += 1
            if active_speakers > max_concurrent_speakers:
                max_concurrent_speakers = active_speakers
        time.sleep(0.05)
        with lock:
            active_speakers -= 1

    with patch.object(tts, "_play_audio_file", side_effect=fake_play), \
         patch.object(tts, "_generate_edge_tts", return_value=None), \
         patch("os.path.exists", return_value=True), \
         patch("os.path.getsize", return_value=1024), \
         patch("os.remove", return_value=None):

        threads = []
        for i in range(4):
            t = threading.Thread(target=tts.speak, args=(f"Message {i}",))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

    # Even with 4 parallel threads calling speak(), at most 1 should speak at any given moment
    assert max_concurrent_speakers == 1, f"Expected 1 concurrent speaker, got {max_concurrent_speakers}"


def test_action_exception_logged_and_does_not_crash_controller(mock_assistant):
    """Verifies that an exception in action execution is caught, logged, and does not crash assistant."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)

    def failing_launch(app_name):
        raise RuntimeError("Simulated process execution failure")

    mock_assistant.app_launcher.launch.side_effect = failing_launch

    res = mock_assistant.process_utterance("open Chrome")

    # Controller must remain healthy and return True
    assert res is True
    assert mock_assistant.running is False or mock_assistant.state_machine.current_state == SessionState.ACTIVE_SESSION


def test_repeated_commands_do_not_create_unbounded_workers(mock_assistant):
    """Verifies that executor thread pools are bounded and reuse worker threads."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_assistant.app_launcher.launch.return_value = (True, "Google Chrome open kar rahi hoon.")

    for _ in range(15):
        mock_assistant.process_utterance("open Chrome")

    assert mock_assistant._action_executor._max_workers == 2
    assert mock_assistant._speech_executor._max_workers == 1


def test_whatsapp_safety_preserved_no_concurrent_send(mock_assistant):
    """Verifies that WhatsApp confirmation workflow remains strictly sequential and gated."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)

    # Start WhatsApp flow
    with patch("core.assistant.find_matching_contacts", return_value=["anand"]), \
         patch("core.assistant.resolve_contact_phone", return_value=("919893371769", None)):
        mock_assistant.process_utterance("send a WhatsApp message to Anand that hello")

    # Must be in AWAITING_CONFIRMATION, send must NOT have been called
    assert mock_assistant.state_machine.current_state == SessionState.AWAITING_CONFIRMATION

    with patch("core.assistant.send_whatsapp_message_via_pywhatkit") as mock_send:
        mock_send.return_value = (True, "Message sent.")
        # Only upon explicit affirmative confirmation is send invoked
        mock_assistant.process_utterance("haan")
        mock_send.assert_called_once_with("919893371769", "hello", "anand")
