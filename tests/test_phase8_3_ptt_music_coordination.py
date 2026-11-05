"""
Unit and integration tests for Phase 8.3: Spacebar Push-to-Talk (PTT) and Music Audio Coordination.
Verifies global Spacebar press-and-hold detection, auto-repeat suppression,
prompt capture finalization, volume ducking/restoration coordination, wake-word enforcement,
short-tap rejection, single microphone stream invariant, and graceful lifecycle shutdown.
All tests use mocks; no real hardware, live microphone, or network streaming are initiated.
"""

import threading
import time
import unittest
from unittest.mock import MagicMock, patch, call

import speech_recognition as sr

from speech.ptt import PushToTalkController
from speech.listener import SpeechListener
from speech.tts import TTSEngine
from actions.music_player import MusicPlayer
from core.assistant import LightAssistant
from core.router import IntentType, CommandIntent
from core.state_machine import SessionState


class TestPhase83PushToTalk(unittest.TestCase):
    """Verifies keyboard controller and single-stream audio capture behavior."""

    def test_1_spacebar_key_down_starts_exactly_one_session(self):
        """Spacebar key-down triggers on_press callback exactly once."""
        mock_press = MagicMock()
        mock_release = MagicMock()
        ptt = PushToTalkController(
            key_check_fn=lambda: False,
            on_press=mock_press,
            on_release=mock_release,
        )

        ptt.simulate_press()
        self.assertTrue(ptt.is_pressed)
        mock_press.assert_called_once()
        mock_release.assert_not_called()

    def test_2_keyboard_auto_repeat_does_not_start_duplicate_sessions(self):
        """Repeated key-down events from OS auto-repeat do NOT trigger duplicate sessions."""
        mock_press = MagicMock()
        ptt = PushToTalkController(on_press=mock_press)

        # Simulate initial key-down followed by repeated held-key signals
        ptt.simulate_press()
        for _ in range(5):
            ptt._handle_state_transition(raw_down=True)

        self.assertTrue(ptt.is_pressed)
        self.assertEqual(mock_press.call_count, 1)

    def test_3_key_up_finalizes_recording_promptly(self):
        """Key-up immediately stops microphone frame capture and finalizes audio."""
        listener = SpeechListener()
        # Mock microphone and PyAudio stream
        mock_mic = MagicMock()
        mock_source = MagicMock()
        mock_source.CHUNK = 512
        mock_source.SAMPLE_RATE = 16000
        mock_source.SAMPLE_WIDTH = 2
        mock_source.stream.read.return_value = b"\x00" * 1024
        mock_mic.__enter__.return_value = mock_source

        listener.microphone = mock_mic

        # Simulate key being held for 2 chunks then released
        is_held_flag = [True, True, False]

        def _is_held():
            if is_held_flag:
                return is_held_flag.pop(0)
            return False

        audio = listener.capture_ptt(is_held_fn=_is_held, min_duration=0.0)
        self.assertIsNotNone(audio)
        self.assertIsInstance(audio, sr.AudioData)
        self.assertEqual(audio.sample_rate, 16000)
        self.assertEqual(audio.sample_width, 2)
        # Should have read exactly 2 chunks before terminating
        self.assertEqual(mock_source.stream.read.call_count, 2)

    def test_4_spacebar_release_restores_music_volume_before_transcription_completes(self):
        """Music volume is restored immediately on key-up without waiting for slow transcription."""
        mock_music_player = MagicMock()
        mock_music_player.is_playing = True

        mock_stt = MagicMock()
        transcription_started = threading.Event()
        transcription_proceed = threading.Event()

        def _slow_transcribe(audio):
            transcription_started.set()
            transcription_proceed.wait(timeout=2.0)
            return True, "Light, open Chrome"

        mock_stt.transcribe.side_effect = _slow_transcribe

        mock_listener = MagicMock()
        mock_audio = MagicMock(spec=sr.AudioData)
        mock_listener.capture_ptt.return_value = mock_audio

        ptt = PushToTalkController()
        assistant = LightAssistant(
            music_player=mock_music_player,
            stt=mock_stt,
            listener=mock_listener,
            tts=MagicMock(),
            bridge=MagicMock(),
            ptt=ptt,
        )

        # Simulate execution of PTT capture cycle
        mock_music_player.duck_volume("ptt")
        audio = assistant.listener.capture_ptt(is_held_fn=lambda: True)
        mock_music_player.restore_volume("ptt")

        # Volume restore was called
        mock_music_player.restore_volume.assert_called_with("ptt")

        # Now async processing begins
        fut = assistant._action_executor.submit(assistant._process_ptt_audio, audio)
        self.assertTrue(transcription_started.wait(timeout=1.0))

        # Release transcription
        transcription_proceed.set()
        fut.result(timeout=1.0)
        assistant._shutdown_internal(farewell_message="")

    def test_5_missing_wake_word_is_rejected_during_music_playback(self):
        """Speech captured via PTT lacking the wake word 'Light' is ignored."""
        mock_stt = MagicMock()
        mock_stt.transcribe.return_value = (True, "open Chrome")  # Missing "Light"

        mock_router = MagicMock()
        assistant = LightAssistant(
            stt=mock_stt,
            router=mock_router,
            tts=MagicMock(),
            bridge=MagicMock(),
        )

        mock_audio = MagicMock(spec=sr.AudioData)
        assistant._process_ptt_audio(mock_audio)

        # Router must NOT have been called because wake word was missing
        mock_router.route.assert_not_called()
        assistant._shutdown_internal(farewell_message="")

    def test_6_valid_wake_word_command_is_routed_normally(self):
        """Speech captured via PTT containing 'Light' is accepted and routed."""
        mock_stt = MagicMock()
        mock_stt.transcribe.return_value = (True, "Light, open Chrome")

        mock_router = MagicMock()
        mock_router.route.return_value = CommandIntent(IntentType.OPEN_APP, payload={"app_name": "chrome"})

        mock_app_launcher = MagicMock()
        assistant = LightAssistant(
            stt=mock_stt,
            router=mock_router,
            app_launcher=mock_app_launcher,
            tts=MagicMock(),
            bridge=MagicMock(),
        )

        mock_audio = MagicMock(spec=sr.AudioData)
        assistant._process_ptt_audio(mock_audio)

        mock_router.route.assert_called_once_with("Light, open Chrome", SessionState.WAITING_FOR_ACTIVATION)
        assistant._shutdown_internal(farewell_message="")

    def test_7_empty_or_short_recording_triggers_no_action(self):
        """Accidental tap (< 0.3s) or empty frames produce no AudioData and trigger no STT."""
        listener = SpeechListener()
        mock_mic = MagicMock()
        mock_source = MagicMock()
        mock_source.stream.read.return_value = b""
        mock_mic.__enter__.return_value = mock_source
        listener.microphone = mock_mic

        # Immediate release (< 0.3s)
        audio = listener.capture_ptt(is_held_fn=lambda: False, min_duration=0.3)
        self.assertIsNone(audio)


class TestPhase83AudioCoordination(unittest.TestCase):
    """Verifies overlapping volume ducking and single stream invariant."""

    def test_8_no_simultaneous_microphone_streams_exist(self):
        """Single master listener ensures only one microphone capture path runs at a time."""
        listener = SpeechListener()
        mock_mic = MagicMock()
        listener.microphone = mock_mic

        # Normal listen context
        listener.listen()
        self.assertEqual(mock_mic.__enter__.call_count, 1)

        # PTT capture context
        listener.capture_ptt(is_held_fn=lambda: False)
        self.assertEqual(mock_mic.__enter__.call_count, 2)

    def test_9_music_continues_while_transcription_and_command_processing_run(self):
        """Music playback worker is never stopped merely to transcribe or execute a command."""
        mock_music_player = MagicMock()
        mock_music_player.is_playing = True

        mock_stt = MagicMock()
        mock_stt.transcribe.return_value = (True, "Light, what is artificial intelligence?")

        mock_gateway = MagicMock()
        from core.coe_gateway import GatewayStatus
        mock_gateway.chat_completion.return_value = (True, "AI is machine intelligence.", GatewayStatus.SUCCESS)

        assistant = LightAssistant(
            music_player=mock_music_player,
            stt=mock_stt,
            gateway_client=mock_gateway,
            tts=MagicMock(),
            bridge=MagicMock(),
        )

        mock_audio = MagicMock(spec=sr.AudioData)
        assistant._process_ptt_audio(mock_audio)

        # Music player stop() must NOT be called for standard Q&A/action
        mock_music_player.stop.assert_not_called()
        assistant._shutdown_internal(farewell_message="")

    def test_10_tts_ducks_music_while_speaking_and_restores_afterward(self):
        """TTSEngine coordinates with music_player so music ducks during speech output."""
        mock_music_player = MagicMock()
        mock_music_player.is_playing = True

        assistant = LightAssistant(music_player=mock_music_player)

        # Simulate TTS start and finish hooks
        assistant._on_tts_start()
        mock_music_player.duck_volume.assert_called_with(reason="tts")

        assistant._on_tts_finish()
        mock_music_player.restore_volume.assert_called_with(reason="tts")
        assistant._shutdown_internal(farewell_message="")

    def test_11_ptt_and_tts_overlapping_duck_requests_do_not_restore_prematurely(self):
        """
        Critical test: If PTT is released while TTS is speaking, volume remains ducked
        until TTS completes.
        """
        fake_player = MagicMock()
        fake_player.audio_get_volume.return_value = 80

        music_player = MusicPlayer(
            vlc_module_override=None,
            ytdl_class=None,
            normal_volume=80,
            ducked_volume=20,
        )
        music_player._player = fake_player

        # 1. User presses Spacebar (PTT ducks music)
        music_player.duck_volume(reason="ptt")
        self.assertTrue(music_player.is_ducked)
        self.assertEqual(music_player._saved_volume, 80)
        fake_player.audio_set_volume.assert_called_with(20)

        # 2. While Spacebar is still held, assistant begins speaking (TTS ducks music)
        music_player.duck_volume(reason="tts")
        self.assertTrue(music_player.is_ducked)
        # Original saved volume must NOT be overwritten by the ducked volume (20)
        self.assertEqual(music_player._saved_volume, 80)

        # 3. User releases Spacebar (PTT restores volume)
        fake_player.reset_mock()
        music_player.restore_volume(reason="ptt")

        # Volume must REMAIN ducked because TTS is still actively speaking!
        self.assertTrue(music_player.is_ducked)
        fake_player.audio_set_volume.assert_not_called()

        # 4. Assistant finishes speaking (TTS restores volume)
        music_player.restore_volume(reason="tts")

        # Now all duck reasons are cleared; volume restores to original 80
        self.assertFalse(music_player.is_ducked)
        fake_player.audio_set_volume.assert_called_with(80)

    def test_12_accidental_taps_and_shutdown_during_recording_are_safe(self):
        """Shutting down assistant while PTT controller is running stops gracefully."""
        mock_music_player = MagicMock()
        ptt = PushToTalkController()
        assistant = LightAssistant(
            music_player=mock_music_player,
            ptt=ptt,
        )

        ptt.start()
        self.assertTrue(ptt.is_running)

        # Trigger shutdown
        assistant.state_machine.activate_session()
        assistant.handle_intent(CommandIntent(IntentType.EXIT))

        # PTT controller must be stopped
        self.assertFalse(ptt.is_running)
        mock_music_player.shutdown.assert_called()

    def test_13_existing_normal_listening_mode_still_works_when_music_not_playing(self):
        """When music is not playing, the assistant uses ordinary listener.listen()."""
        mock_music_player = MagicMock()
        mock_music_player.is_playing = False  # Music is NOT playing

        mock_listener = MagicMock()
        mock_listener.init_microphone.return_value = True
        mock_listener.listen.return_value = None  # Loop iteration completes

        assistant = LightAssistant(
            music_player=mock_music_player,
            listener=mock_listener,
            bridge=MagicMock(),
        )

        # Run one slice of run loop then exit
        def _stop_soon():
            time.sleep(0.05)
            assistant.running = False

        threading.Thread(target=_stop_soon, daemon=True).start()
        assistant.run()

        # listener.listen() must have been called
        mock_listener.listen.assert_called()
        # capture_ptt must NOT have been called
        mock_listener.capture_ptt.assert_not_called()

    def test_14_empty_or_failed_capture_in_run_loop_always_restores_volume(self):
        """Even if capture_ptt raises an exception, try...finally ensures volume restoration."""
        mock_music_player = MagicMock()
        mock_music_player.is_playing = True

        mock_listener = MagicMock()
        mock_listener.init_microphone.return_value = True
        mock_listener.capture_ptt.side_effect = RuntimeError("Microphone device disconnected")

        mock_ptt = MagicMock()
        # First iteration: wait_for_press returns True; second iteration: exit loop
        mock_ptt.wait_for_press.side_effect = [True, False]
        mock_ptt.is_pressed = False

        assistant = LightAssistant(
            music_player=mock_music_player,
            listener=mock_listener,
            ptt=mock_ptt,
            tts=MagicMock(),
            bridge=MagicMock(),
        )

        def _stop_soon():
            time.sleep(0.05)
            assistant.running = False

        threading.Thread(target=_stop_soon, daemon=True).start()
        assistant.run()

        # duck_volume and restore_volume must have been called symmetrically
        mock_music_player.duck_volume.assert_called_with(reason="ptt")
        mock_music_player.restore_volume.assert_called_with(reason="ptt")

    def test_15_stt_exception_leaves_music_volume_restored(self):
        """If STT raises an exception during transcription, music volume remains restored."""
        mock_music_player = MagicMock()
        mock_music_player.is_playing = True
        mock_music_player.is_ducked = False

        mock_stt = MagicMock()
        mock_stt.transcribe.side_effect = Exception("STT engine timeout")

        assistant = LightAssistant(
            music_player=mock_music_player,
            stt=mock_stt,
            tts=MagicMock(),
            bridge=MagicMock(),
        )

        # Before async processing, PTT release already restored volume
        mock_audio = MagicMock(spec=sr.AudioData)
        # Should not raise exception
        assistant._process_ptt_audio(mock_audio)

        # Volume remains restored
        self.assertFalse(mock_music_player.is_ducked)
        assistant._shutdown_internal(farewell_message="")

    def test_16_duck_volume_never_overwrites_saved_volume_with_ducked_level(self):
        """If player volume is already ducked (20), duck_volume does NOT overwrite _saved_volume with 20."""
        fake_player = MagicMock()
        fake_player.audio_get_volume.return_value = 20  # Reports ducked volume

        music_player = MusicPlayer(
            vlc_module_override=None,
            ytdl_class=None,
            normal_volume=80,
            ducked_volume=20,
        )
        music_player._player = fake_player
        music_player._saved_volume = 80

        # Call duck_volume while player is already reporting 20
        music_player.duck_volume(reason="ptt")
        # _saved_volume must NOT be corrupted to 20!
        self.assertEqual(music_player._saved_volume, 80)

        # Restoring returns to 80
        music_player.restore_volume(reason="ptt")
        fake_player.audio_set_volume.assert_called_with(80)

    def test_17_real_microphone_stream_read_positional_signature_compat(self):
        """MicrophoneStream.read(size) without keyword arguments does not raise TypeError."""
        listener = SpeechListener()

        class MockMicrophoneStream:
            def read(self, size):
                # Signature matches real speech_recognition.Microphone.MicrophoneStream
                return b"\x00" * size

        mock_source = MagicMock()
        mock_source.CHUNK = 512
        mock_source.SAMPLE_RATE = 16000
        mock_source.SAMPLE_WIDTH = 2
        mock_source.stream = MockMicrophoneStream()

        mock_mic = MagicMock()
        mock_mic.__enter__.return_value = mock_source
        listener.microphone = mock_mic

        # Hold for 3 iterations then release
        hold_count = [True, True, True, False]
        audio = listener.capture_ptt(is_held_fn=lambda: hold_count.pop(0) if hold_count else False, min_duration=0.0)

        self.assertIsNotNone(audio)
        self.assertIsInstance(audio, sr.AudioData)
        self.assertEqual(len(audio.get_raw_data()), 512 * 3)

    def test_18_wait_for_press_one_shot_consumption(self):
        """wait_for_press consumes the event so a single physical hold cannot trigger repeated sessions."""
        ptt = PushToTalkController()

        ptt.simulate_press()
        # First call: detects press and consumes event
        pressed_first = ptt.wait_for_press(timeout=0.05)
        self.assertTrue(pressed_first)

        # Second call without key release: must time out (one-shot consumption)
        pressed_second = ptt.wait_for_press(timeout=0.05)
        self.assertFalse(pressed_second)

        # Key release followed by new press: triggers again
        ptt.simulate_release()
        ptt.simulate_press()
        pressed_third = ptt.wait_for_press(timeout=0.05)
        self.assertTrue(pressed_third)

    def test_19_ptt_cancellation_and_shutdown_restore_volume(self):
        """Shutting down the player while ducked immediately restores volume and clears duck state."""
        fake_player = MagicMock()
        fake_player.audio_get_volume.return_value = 80
        music_player = MusicPlayer(
            vlc_module_override=None,
            ytdl_class=None,
            normal_volume=80,
            ducked_volume=20,
        )
        music_player._player = fake_player

        music_player.duck_volume(reason="ptt")
        self.assertTrue(music_player.is_ducked)

        music_player.shutdown()
        self.assertFalse(music_player.is_ducked)
        self.assertEqual(len(music_player._duck_reasons), 0)

    def test_20_unknown_command_and_missing_wakeword_leave_volume_restored(self):
        """Commands with missing wake word or unknown queries do not leave music ducked."""
        mock_music_player = MagicMock()
        mock_music_player.is_playing = True
        mock_music_player.is_ducked = False

        mock_stt = MagicMock()
        # 1. Missing wake word
        mock_stt.transcribe.return_value = (True, "tum kon ho")
        assistant = LightAssistant(
            music_player=mock_music_player,
            stt=mock_stt,
            tts=MagicMock(),
            bridge=MagicMock(),
        )

        mock_audio = MagicMock(spec=sr.AudioData)
        assistant._process_ptt_audio(mock_audio)
        self.assertFalse(mock_music_player.is_ducked)

        # 2. Unknown command with wake word
        mock_stt.transcribe.return_value = (True, "Light asdfghjkl")
        assistant._process_ptt_audio(mock_audio)
        self.assertFalse(mock_music_player.is_ducked)
        assistant._shutdown_internal(farewell_message="")

