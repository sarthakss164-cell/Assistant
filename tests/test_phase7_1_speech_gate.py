"""
Unit and integration tests for Phase 7.1: Safe Speech-Output Gating.
Verifies prevention of TTS-to-microphone feedback loops, serialized speech queueing,
error resilience, and non-blocking concurrent action execution.
"""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest
import speech_recognition as sr

from core.assistant import LightAssistant
from core.router import CommandRouter, CommandIntent, IntentType
from core.speech_gate import SpeechOutputGate
from core.state_machine import SessionState, StateMachine
from speech.listener import SpeechListener
from speech.tts import TTSEngine


@pytest.fixture
def mock_audio():
    """Mock sr.AudioData instance for speech listener."""
    audio = MagicMock(spec=sr.AudioData)
    audio.get_raw_data.return_value = b"RIFF" + b"\x00" * 100
    return audio


@pytest.fixture
def speech_gate():
    """Fresh SpeechOutputGate instance."""
    return SpeechOutputGate(settling_delay=0.0)


class TestSpeechOutputGateBasics:
    """Direct unit tests for SpeechOutputGate state transitions."""

    def test_gate_initial_state(self, speech_gate):
        assert not speech_gate.is_active
        assert not speech_gate.is_playing
        assert speech_gate.pending_count == 0
        assert speech_gate.wait_for_idle(timeout=0.1) is True

    def test_gate_playback_lifecycle(self, speech_gate):
        speech_gate.start_playback()
        assert speech_gate.is_active
        assert speech_gate.is_playing

        speech_gate.stop_playback()
        assert not speech_gate.is_active
        assert not speech_gate.is_playing
        assert speech_gate.wait_for_idle(timeout=0.1) is True

    def test_gate_playback_context(self, speech_gate):
        with speech_gate.playback_context():
            assert speech_gate.is_active
            assert speech_gate.is_playing
        assert not speech_gate.is_active

    def test_gate_queued_speech_lifecycle(self, speech_gate):
        speech_gate.mark_speech_queued()
        assert speech_gate.is_active
        assert not speech_gate.is_playing
        assert speech_gate.pending_count == 1

        with speech_gate.playback_context():
            assert speech_gate.is_active
            assert speech_gate.is_playing

        speech_gate.mark_speech_completed()
        assert not speech_gate.is_active
        assert speech_gate.pending_count == 0

    def test_gate_resets_cleanly(self, speech_gate):
        speech_gate.mark_speech_queued()
        speech_gate.start_playback()
        assert speech_gate.is_active

        speech_gate.reset()
        assert not speech_gate.is_active
        assert speech_gate.pending_count == 0
        assert speech_gate.wait_for_idle(timeout=0.1) is True


class TestMicrophoneGating:
    """Verifies listener interactions with speech output gate."""

    def test_microphone_audio_during_playback_is_ignored(self, speech_gate, mock_audio):
        listener = SpeechListener(speech_gate=speech_gate)
        listener.microphone = MagicMock()

        # Gate is active during capture -> audio must be discarded
        speech_gate.start_playback()
        with patch.object(listener.recognizer, "listen", return_value=mock_audio):
            captured = listener.listen()
            assert captured is None

        speech_gate.stop_playback()

    def test_microphone_discards_audio_overlapping_recent_playback(self, speech_gate, mock_audio):
        listener = SpeechListener(speech_gate=speech_gate)
        listener.microphone = MagicMock()

        capture_timestamp = time.time()
        # Simulate playback that ended just as or right after capture started
        speech_gate.start_playback()
        time.sleep(0.01)
        speech_gate.stop_playback()

        # Audio returned should be discarded because playback overlapped with capture start
        with patch.object(listener.recognizer, "listen", return_value=mock_audio):
            with patch("speech.listener.time.time", return_value=capture_timestamp):
                captured = listener.listen()
                assert captured is None

    def test_listener_waits_for_playback_to_finish(self, speech_gate, mock_audio):
        listener = SpeechListener(speech_gate=speech_gate)
        listener.microphone = MagicMock()

        # Start playback, schedule stop after 0.05s
        speech_gate.start_playback()

        def _delayed_stop():
            time.sleep(0.05)
            speech_gate.stop_playback()

        t = threading.Thread(target=_delayed_stop)
        t.start()

        with patch.object(listener.recognizer, "listen", return_value=mock_audio):
            captured = listener.listen()
            assert captured == mock_audio

        t.join()


class TestSelfEchoPreventionAndConcurrency:
    """Verifies that assistant output cannot trigger secondary commands."""

    def test_self_echo_cannot_trigger_second_action(self, mock_audio):
        """
        Simulates the reported bug:
        1. User says 'Light, open Chrome'.
        2. Chrome launches concurrently with ack 'Google Chrome open kar rahi hoon.'
        3. Listener is gated while TTS speaks, preventing self-recognition from executing search.
        """
        gate = SpeechOutputGate()
        listener = SpeechListener(speech_gate=gate)
        listener.microphone = MagicMock()

        mock_app_launcher = MagicMock()
        mock_app_launcher.launch.return_value = (True, "Launching Google Chrome")

        mock_tts = MagicMock()
        playback_in_progress = threading.Event()
        release_playback = threading.Event()

        def _fake_speak(text):
            playback_in_progress.set()
            release_playback.wait(timeout=1.0)
            return True

        mock_tts.speak.side_effect = _fake_speak

        assistant = LightAssistant(
            listener=listener,
            tts=mock_tts,
            app_launcher=mock_app_launcher,
        )
        assistant.speech_gate = gate
        listener.speech_gate = gate

        # Activate session
        assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)

        # Trigger "Light, open Chrome"
        assistant.process_utterance("Light, open Chrome")

        # Confirm speech task started and gate is active
        assert playback_in_progress.wait(timeout=0.5) is True
        assert gate.is_active is True

        # While speech is playing, listener must wait and not capture audio prematurely
        listen_result = []

        def _listen_worker():
            with patch.object(listener.recognizer, "listen", return_value=mock_audio):
                res = listener.listen()
                listen_result.append(res)

        listen_thread = threading.Thread(target=_listen_worker)
        listen_thread.start()

        # Brief sleep: confirm listener is waiting on speech gate and has not captured
        time.sleep(0.05)
        assert len(listen_result) == 0

        # Release speech playback
        release_playback.set()
        listen_thread.join(timeout=1.0)

        # Confirm gate deactivated, listener resumed cleanly after playback, and no secondary command occurred
        assert len(listen_result) == 1
        assert listen_result[0] == mock_audio
        assert gate.wait_for_idle(timeout=0.5) is True
        assert mock_app_launcher.launch.call_count == 1
        mock_app_launcher.launch.assert_called_once_with("chrome")

    def test_listening_resumes_after_normal_playback(self, mock_audio):
        gate = SpeechOutputGate()
        listener = SpeechListener(speech_gate=gate)
        listener.microphone = MagicMock()

        mock_tts = MagicMock()
        mock_tts.speak.return_value = True

        assistant = LightAssistant(
            listener=listener,
            tts=mock_tts,
        )
        assistant.speech_gate = gate
        listener.speech_gate = gate
        assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)

        # Run concurrent task
        assistant._execute_concurrent_action_and_speech(
            action_func=lambda: True,
            ack_text="Action done",
            action_name="test_action",
        )

        # Wait for speech to complete
        assert gate.wait_for_idle(timeout=1.0) is True

        # Now listener should cleanly capture next command
        with patch.object(listener.recognizer, "listen", return_value=mock_audio):
            audio = listener.listen()
            assert audio == mock_audio

    def test_listening_resumes_if_tts_raises_exception(self):
        gate = SpeechOutputGate()
        listener = SpeechListener(speech_gate=gate)
        listener.microphone = MagicMock()

        mock_tts = MagicMock()
        mock_tts.speak.side_effect = RuntimeError("Audio mixer failed")

        assistant = LightAssistant(
            listener=listener,
            tts=mock_tts,
        )
        assistant.speech_gate = gate
        listener.speech_gate = gate

        # Execute concurrent speech that fails
        assistant._execute_concurrent_action_and_speech(
            action_func=lambda: True,
            ack_text="Broken speech",
            action_name="failing_action",
        )

        # Verify gate still cleanly returns to idle despite exception
        assert gate.wait_for_idle(timeout=1.0) is True
        assert not gate.is_active

    def test_queued_speech_no_listening_gap_between_consecutive_tasks(self):
        gate = SpeechOutputGate()
        mock_tts = MagicMock()

        task1_started = threading.Event()
        task1_release = threading.Event()
        task2_started = threading.Event()
        task2_release = threading.Event()

        def _fake_speak(text):
            if text == "Task 1":
                task1_started.set()
                task1_release.wait(timeout=1.0)
            elif text == "Task 2":
                task2_started.set()
                task2_release.wait(timeout=1.0)
            return True

        mock_tts.speak.side_effect = _fake_speak

        assistant = LightAssistant(tts=mock_tts)
        assistant.speech_gate = gate

        # Queue Task 1 and Task 2 back-to-back
        assistant._execute_concurrent_action_and_speech(lambda: True, "Task 1", "t1")
        assistant._execute_concurrent_action_and_speech(lambda: True, "Task 2", "t2")

        # Task 1 starts
        assert task1_started.wait(timeout=0.5) is True
        assert gate.is_active is True
        assert gate.pending_count >= 1

        # Release Task 1
        task1_release.set()

        # Task 2 starts immediately without gate returning to idle
        assert task2_started.wait(timeout=0.5) is True
        assert gate.is_active is True

        # Release Task 2
        task2_release.set()

        # Both finished -> gate now idle
        assert gate.wait_for_idle(timeout=1.0) is True
        assert not gate.is_active

    def test_first_user_command_after_playback_accepted_normally(self):
        gate = SpeechOutputGate()
        mock_app_launcher = MagicMock()
        mock_app_launcher.launch.return_value = (True, "Launched")
        mock_tts = MagicMock()
        mock_tts.speak.return_value = True

        assistant = LightAssistant(
            tts=mock_tts,
            app_launcher=mock_app_launcher,
        )
        assistant.speech_gate = gate
        assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)

        # First command: Chrome
        assistant.process_utterance("Light, open Chrome")
        time.sleep(0.05)
        assert gate.wait_for_idle(timeout=1.0) is True
        assert mock_app_launcher.launch.call_count == 1

        # Second command immediately after playback: Notepad
        assistant.process_utterance("open Notepad")
        time.sleep(0.05)
        assert gate.wait_for_idle(timeout=1.0) is True
        assert mock_app_launcher.launch.call_count == 2

    def test_first_command_conversational_activation_still_works(self):
        mock_tts = MagicMock()
        mock_tts.speak.return_value = True

        assistant = LightAssistant(tts=mock_tts)
        assert assistant.state_machine.current_state == SessionState.WAITING_FOR_ACTIVATION

        assistant.process_utterance("Light, who are you?")
        assert assistant.state_machine.current_state == SessionState.ACTIVE_SESSION
        assert mock_tts.speak.call_count >= 1

    def test_chrome_launch_and_ack_remain_concurrent(self):
        gate = SpeechOutputGate()
        mock_app_launcher = MagicMock()
        mock_tts = MagicMock()

        action_running = threading.Event()
        speech_running = threading.Event()
        action_done = threading.Event()
        speech_done = threading.Event()

        def _slow_launch(app):
            action_running.set()
            speech_running.wait(timeout=1.0)  # Action observes speech running concurrently
            action_done.set()
            return True, "Chrome launched"

        def _slow_speak(text):
            speech_running.set()
            action_running.wait(timeout=1.0)  # Speech observes action running concurrently
            speech_done.set()
            return True

        mock_app_launcher.launch.side_effect = _slow_launch
        mock_tts.speak.side_effect = _slow_speak

        assistant = LightAssistant(
            tts=mock_tts,
            app_launcher=mock_app_launcher,
        )
        assistant.speech_gate = gate
        assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)

        assistant.process_utterance("Light, open Chrome")

        # Confirm both executed concurrently
        assert action_done.wait(timeout=1.0) is True
        assert speech_done.wait(timeout=1.0) is True

    def test_graceful_shutdown_waits_for_farewell_before_mixer_teardown(self):
        mock_tts = MagicMock()
        farewell_playing = threading.Event()
        farewell_released = threading.Event()

        def _farewell_speak(msg):
            farewell_playing.set()
            farewell_released.wait(timeout=1.0)
            return True

        mock_tts.speak.side_effect = _farewell_speak

        assistant = LightAssistant(tts=mock_tts)
        assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)

        shutdown_thread = threading.Thread(
            target=assistant.handle_intent,
            args=(CommandIntent(intent_type=IntentType.EXIT),),
        )
        shutdown_thread.start()

        # Confirm farewell playback is waited on
        assert farewell_playing.wait(timeout=0.5) is True
        farewell_released.set()
        shutdown_thread.join(timeout=2.0)

        assert assistant.state_machine.current_state == SessionState.SHUTDOWN
        assert not assistant.running
        assert not assistant.speech_gate.is_active
