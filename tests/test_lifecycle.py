"""
Unit tests for lifecycle and identity actions.
Verifies fixed identity response and resilient shutdown with independently guarded cleanups.
"""

import os
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from actions.identity import get_identity_response
from actions.lifecycle import graceful_shutdown, purge_temp_audio_files
from config.settings import FIXED_IDENTITY_RESPONSE


def test_fixed_identity_response():
    """Verifies that identity action returns the exact approved identity response."""
    success, text = get_identity_response()
    assert success is True
    assert text == FIXED_IDENTITY_RESPONSE
    assert text == "Main Light AI hoon, jise mere Boss ne banaya hai."


def test_purge_temp_audio_files(tmp_path):
    """Verifies that temporary audio files are purged safely."""
    # Create test temp files
    f1 = tmp_path / "light_audio_12345.mp3"
    f2 = tmp_path / "light_audio_test.mp3"
    f3 = tmp_path / "notes.txt"
    f1.write_text("audio data")
    f2.write_text("audio data")
    f3.write_text("keep this")

    count = purge_temp_audio_files(tmp_path)
    assert count == 2
    assert not f1.exists()
    assert not f2.exists()
    assert f3.exists()


@patch("actions.lifecycle.shutdown_audio_mixer")
@patch("actions.lifecycle.shutdown_listener")
@patch("actions.lifecycle.purge_temp_audio_files")
def test_graceful_shutdown_success(mock_purge, mock_listener, mock_mixer):
    """Verifies standard orderly shutdown sequence."""
    mock_tts = MagicMock()
    mock_list_obj = MagicMock()

    graceful_shutdown(tts_engine=mock_tts, listener=mock_list_obj, exit_process=False)

    mock_tts.speak.assert_called_once()
    mock_mixer.assert_called_once()
    mock_listener.assert_called_once_with(mock_list_obj)
    mock_purge.assert_called_once()


@patch("actions.lifecycle.shutdown_audio_mixer")
@patch("actions.lifecycle.shutdown_listener")
@patch("actions.lifecycle.purge_temp_audio_files")
def test_graceful_shutdown_tts_failure_does_not_abort(mock_purge, mock_listener, mock_mixer):
    """Verifies that TTS failure does not abort the remaining cleanup operations."""
    mock_tts = MagicMock()
    mock_tts.speak.side_effect = RuntimeError("TTS Engine crashed")

    graceful_shutdown(tts_engine=mock_tts, exit_process=False)

    mock_mixer.assert_called_once()
    mock_listener.assert_called_once()
    mock_purge.assert_called_once()


@patch("actions.lifecycle.shutdown_audio_mixer", side_effect=Exception("Mixer busy"))
@patch("actions.lifecycle.shutdown_listener")
@patch("actions.lifecycle.purge_temp_audio_files")
def test_graceful_shutdown_individual_cleanup_failure_resilience(mock_purge, mock_listener, mock_mixer):
    """Verifies that failure in mixer shutdown does not prevent listener release or temp file purge."""
    mock_list_obj = MagicMock()
    graceful_shutdown(listener=mock_list_obj, exit_process=False)

    mock_listener.assert_called_once_with(mock_list_obj)
    mock_purge.assert_called_once()
