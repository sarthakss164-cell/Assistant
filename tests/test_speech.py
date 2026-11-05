"""
Unit tests for the speech layer (TTS, Listener, STT).
Verifies Edge TTS with SAPI5 fallback, acoustic guard delay,
Google Speech Recognition error handling, and continuous speech capture with ~1s silence detection.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import speech_recognition as sr
from speech.tts import TTSEngine
from speech.listener import SpeechListener
from speech.stt import GoogleSpeechRecognizer
from config.settings import MIC_MIN_ENERGY_THRESHOLD


# =============================================================================
# TTS Tests
# =============================================================================

def test_tts_empty_string():
    """Verifies that empty speech requests return False immediately without error."""
    engine = TTSEngine(acoustic_delay=0.0)
    assert engine.speak("") is False
    assert engine.speak("   ") is False


@patch("speech.tts.time.sleep")
@patch("speech.tts.TTSEngine._play_audio_file")
@patch("speech.tts.TTSEngine._generate_edge_tts", new_callable=AsyncMock)
@patch("os.path.exists", return_value=True)
@patch("os.path.getsize", return_value=1024)
@patch("os.remove")
def test_tts_primary_edge_success(mock_remove, mock_getsize, mock_exists, mock_edge, mock_play, mock_sleep):
    """Verifies primary Edge TTS path and settling delay execution."""
    engine = TTSEngine(acoustic_delay=0.4)
    result = engine.speak("Hello Light")

    assert result is True
    mock_edge.assert_called_once()
    mock_play.assert_called_once()
    mock_remove.assert_called_once()
    mock_sleep.assert_called_with(0.4)


@patch("speech.tts.time.sleep")
@patch("speech.tts.TTSEngine._generate_edge_tts", side_effect=RuntimeError("Edge TTS Offline"))
@patch("speech.tts.TTSEngine._fallback_speak_sapi5")
def test_tts_fallback_to_sapi5(mock_sapi, mock_edge, mock_sleep):
    """Verifies fallback to SAPI5 when Edge TTS fails."""
    engine = TTSEngine(acoustic_delay=0.1)
    result = engine.speak("Fallback test")

    assert result is True
    mock_edge.assert_called_once()
    mock_sapi.assert_called_once_with("Fallback test")
    mock_sleep.assert_called_with(0.1)


def test_tts_hindi_pronunciation_normalization():
    """Verifies that 'mere' is mapped to 'मेरे' for Edge TTS to prevent 'meer' pronunciation."""
    engine = TTSEngine()
    prepared = engine._prepare_text_for_edge_tts("Main Light AI hoon, jise mere Boss ne banaya hai.")
    assert "मेरे" in prepared
    assert "mere" not in prepared.lower()


# =============================================================================
# STT Tests
# =============================================================================

def test_stt_none_audio():
    """Verifies handling of None audio input."""
    stt = GoogleSpeechRecognizer()
    success, res = stt.transcribe(None)
    assert success is False
    assert res == "audio_empty"


def test_stt_successful_transcription():
    """Verifies successful Google Speech recognition."""
    stt = GoogleSpeechRecognizer()
    mock_audio = MagicMock(spec=sr.AudioData)

    with patch.object(stt.recognizer, "recognize_google", return_value="open chrome"):
        success, text = stt.transcribe(mock_audio)
        assert success is True
        assert text == "open chrome"


def test_stt_unintelligible_speech():
    """Verifies that sr.UnknownValueError returns success=True with empty string."""
    stt = GoogleSpeechRecognizer()
    mock_audio = MagicMock(spec=sr.AudioData)

    with patch.object(stt.recognizer, "recognize_google", side_effect=sr.UnknownValueError()):
        success, text = stt.transcribe(mock_audio)
        assert success is True
        assert text == ""


def test_stt_network_failure():
    """Verifies that sr.RequestError returns success=False with 'network_error'."""
    stt = GoogleSpeechRecognizer()
    mock_audio = MagicMock(spec=sr.AudioData)

    with patch.object(stt.recognizer, "recognize_google", side_effect=sr.RequestError("Connection dropped")):
        success, err = stt.transcribe(mock_audio)
        assert success is False
        assert err == "network_error"


# =============================================================================
# Listener & Continuous Speech Capture Tests
# =============================================================================

def test_listener_configuration_and_silence_detection():
    """
    Verifies that SpeechListener is configured with ~1.0 second silence detection,
    no premature phrase cutoff (phrase_time_limit=None), and dynamic energy adaptation.
    """
    listener = SpeechListener()
    assert listener.recognizer.pause_threshold == 1.0
    assert listener.phrase_time_limit is None
    assert listener.recognizer.dynamic_energy_threshold is True
    assert listener.recognizer.non_speaking_duration == 0.5


@patch("speech.listener.sr.Microphone")
def test_listener_ambient_noise_calibration_and_floor(mock_mic_cls):
    """Verifies ambient noise calibration and enforcement of the minimum energy floor."""
    mock_mic = MagicMock()
    mock_mic.__enter__.return_value = MagicMock()
    mock_mic.__exit__.return_value = None
    mock_mic_cls.return_value = mock_mic

    listener = SpeechListener()
    with patch.object(listener.recognizer, "adjust_for_ambient_noise") as mock_adjust:
        # Simulate very quiet room calibration
        listener.recognizer.energy_threshold = 50.0
        success = listener.init_microphone()

        assert success is True
        mock_adjust.assert_called_once()
        # Verify floor was enforced
        assert listener.recognizer.energy_threshold >= MIC_MIN_ENERGY_THRESHOLD


def test_listener_wait_timeout_graceful():
    """Verifies that WaitTimeoutError does not crash the listener and returns None."""
    listener = SpeechListener()
    listener.microphone = MagicMock()

    with patch.object(listener.recognizer, "listen", side_effect=sr.WaitTimeoutError()):
        audio = listener.listen()
        assert audio is None


def test_listener_continuous_speech_no_phrase_truncation():
    """Verifies that listener.listen calls recognizer.listen with phrase_time_limit=None."""
    listener = SpeechListener()
    listener.microphone = MagicMock()
    mock_audio = MagicMock(spec=sr.AudioData)

    with patch.object(listener.recognizer, "listen", return_value=mock_audio) as mock_listen:
        audio = listener.listen()
        assert audio == mock_audio
        mock_listen.assert_called_once()
        # Verify phrase_time_limit was None to prevent premature cutoffs
        _, kwargs = mock_listen.call_args
        assert kwargs.get("phrase_time_limit") is None


@patch("speech.listener.SpeechListener.init_microphone", return_value=False)
def test_listener_mic_init_failure_handled(mock_init):
    """Verifies that microphone initialization failure is handled gracefully without crashing."""
    listener = SpeechListener()
    audio = listener.listen()
    assert audio is None
