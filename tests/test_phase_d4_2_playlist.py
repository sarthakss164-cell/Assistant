"""
Phase D4.2 Comprehensive Test Suite — Playlist System, Spotify HUD & Functional Mic Mute
LIGHT AI V1.0
"""

import os
import json
import tempfile
import threading
from typing import Optional, Dict, Any
import pytest
from unittest.mock import MagicMock, patch

from config.playlist_loader import load_playlists, get_legacy_playlists_dict
from actions.music_player import MusicPlayer, PlaylistSession
from core.router import CommandRouter, IntentType
from core.state_machine import SessionState
from speech.listener import SpeechListener
from core.assistant import LightAssistant
from core.bridge.schema import (
    validate_incoming_message,
    create_playlist_state_event,
    create_mic_state_event,
    ALLOWED_INBOUND_TYPES,
    ALLOWED_PLAYLIST_ACTIONS,
    ALLOWED_MIC_ACTIONS,
)
from core.bridge.telemetry import TelemetryCollector
from core.bridge.server import WebSocketBridgeServer


# ==============================================================================
# Fakes for VLC and yt-dlp in testing
# ==============================================================================

class FakeVlcState:
    NothingSpecial = 0
    Opening = 1
    Buffering = 2
    Playing = 3
    Paused = 4
    Stopped = 5
    Ended = 6
    Error = 7


class FakeVlcModule:
    State = FakeVlcState


class FakeMediaPlayer:
    def __init__(self):
        self.current_state = FakeVlcState.Stopped
        self.volume = 80
        self._time_ms = 0
        self._length_ms = 240000

    def play(self):
        self.current_state = FakeVlcState.Playing
        return 0

    def pause(self):
        if self.current_state == FakeVlcState.Playing:
            self.current_state = FakeVlcState.Paused
        elif self.current_state == FakeVlcState.Paused:
            self.current_state = FakeVlcState.Playing

    def set_pause(self, do_pause):
        self.current_state = FakeVlcState.Paused if do_pause else FakeVlcState.Playing

    def stop(self):
        self.current_state = FakeVlcState.Stopped
        return 0

    def get_state(self):
        return self.current_state

    def audio_get_volume(self):
        return self.volume

    def audio_set_volume(self, vol):
        self.volume = vol
        return 0

    def get_time(self):
        return self._time_ms

    def set_time(self, t_ms):
        self._time_ms = t_ms
        return 0

    def get_length(self):
        return self._length_ms

    def is_seekable(self):
        return 1

    def set_media(self, media):
        pass

    def release(self):
        pass


class FakeVlcInstance:
    def __init__(self, player: Optional[FakeMediaPlayer] = None):
        self.player = player or FakeMediaPlayer()

    def media_player_new(self):
        return self.player

    def media_new(self, url):
        return f"VLC_MEDIA_FOR_{url}"

    def release(self):
        pass


def create_mock_ytdl(title_map=None):
    title_map = title_map or {}

    class MockYoutubeDL:
        def __init__(self, opts=None):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

        def extract_info(self, query, download=False):
            clean = query.replace("ytsearch1:", "").strip()
            title = title_map.get(clean, f"Title for {clean}")
            return {
                "url": f"https://mock-stream.internal/{clean}.mp3",
                "title": title,
                "artist": "Mock Artist",
                "duration": 240.0,
            }

    return MockYoutubeDL


def make_test_player(fake_player=None, title_map=None, playlists=None):
    vlc_mod = FakeVlcModule()
    player = fake_player or FakeMediaPlayer()
    instance = FakeVlcInstance(player=player)
    ytdl_cls = create_mock_ytdl(title_map=title_map)
    return MusicPlayer(
        vlc_instance=instance,
        vlc_module_override=vlc_mod,
        ytdl_class=ytdl_cls,
        playlists=playlists,
    )


# ============================================================================
# 1. Config Migration & Loader Tests
# ============================================================================

def test_load_playlists_valid():
    """Verify that load_playlists loads hindi, english, story with exact ordering."""
    playlists = load_playlists()
    assert "hindi" in playlists
    assert "english" in playlists
    assert "story" in playlists

    # Verify hindi songs
    hindi = playlists["hindi"]
    songs = hindi["songs"]
    assert len(songs) >= 3
    assert songs[0]["title"] == "Zaalima"
    assert "zaalima" in songs[0]["query"].lower()

    # Legacy dictionary representation
    legacy = get_legacy_playlists_dict()
    assert isinstance(legacy, dict)
    assert "hindi" in legacy
    assert "Zaalima" in legacy["hindi"][0]


def test_load_playlists_malformed_rejection():
    """Verify that missing or malformed playlist files raise ValueError/FileNotFoundError."""
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as tmp:
        tmp.write("INVALID JSON")
        tmp_path = tmp.name

    try:
        with pytest.raises(ValueError, match="Malformed JSON"):
            load_playlists(tmp_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    # Missing file
    with pytest.raises(FileNotFoundError):
        load_playlists("non_existent_playlist_file_999.json")

    # Empty playlists
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as tmp:
        json.dump({"playlists": {}}, tmp)
        tmp_path = tmp.name

    try:
        with pytest.raises(ValueError, match="Playlist configuration is empty"):
            load_playlists(tmp_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


# ============================================================================
# 2. Authoritative Playlist Session & Engine Lifecycle Tests
# ============================================================================

def test_playlist_session_lifecycle():
    """Verify PlaylistSession creation, track advancement, bounds, and completion."""
    player = make_test_player()

    # Initial state
    snap = player.get_playlist_snapshot()
    assert snap["has_active_session"] is False
    assert snap["entries"] == []

    # Standalone mode checks: next/previous disabled
    ok, msg = player.next_track()
    assert ok is False
    assert "standalone" in msg.lower()
    ok, msg = player.previous_track()
    assert ok is False

    # Start hindi playlist
    ok, msg = player.play_playlist("hindi")
    assert ok is True
    assert player._playlist_session is not None
    assert player._playlist_session.playlist_id == "hindi"
    assert player._playlist_session.current_index == 0
    assert player._playlist_session.state == "PLAYING"

    snap = player.get_playlist_snapshot()
    assert snap["has_active_session"] is True
    assert len(snap["entries"]) >= 3
    assert snap["current_index"] == 0

    # Next track advances index
    player.next_track()
    assert player._playlist_session.current_index == 1
    assert player.get_playlist_snapshot()["current_index"] == 1

    # Previous track: threshold logic
    # If position > 3.0s, restarts current song (stays at index 1)
    player._position_seconds = 5.0
    player.previous_track()
    assert player._playlist_session.current_index == 1
    assert player._position_seconds == 0.0

    # If position <= 3.0s, goes to previous track (index 0)
    player._position_seconds = 1.0
    player.previous_track()
    assert player._playlist_session.current_index == 0

    # At index 0, previous_track() does not go below 0
    player._position_seconds = 0.0
    player.previous_track()
    assert player._playlist_session.current_index == 0


def test_playlist_shuffle_toggle():
    """Verify shuffle toggling retains current song at top and restores original order."""
    player = make_test_player()
    player.play_playlist("hindi")
    initial_order = list(player._playlist_session.playback_order)
    rev1 = player._playlist_session.revision

    # Toggle shuffle ON
    ok, is_shuffle = player.toggle_shuffle()
    assert ok is True
    assert is_shuffle is True
    assert player._playlist_session.is_shuffle is True
    assert player._playlist_session.revision > rev1
    assert player._playlist_session.current_index == 0

    # Toggle shuffle OFF: restores sequential order [0..n-1]
    rev2 = player._playlist_session.revision
    ok, is_shuffle = player.toggle_shuffle()
    assert ok is True
    assert is_shuffle is False
    assert player._playlist_session.is_shuffle is False
    assert player._playlist_session.revision > rev2
    assert player._playlist_session.playback_order == initial_order


def test_playlist_song_selection_and_scoped_search():
    """Verify index selection and scoped song search without global fallback."""
    player = make_test_player()
    player.play_playlist("hindi")

    # Select song by index
    ok, msg = player.play_playlist_song_by_index(2)
    assert ok is True
    assert player._playlist_session.current_index == 2

    # Invalid index rejected
    ok, msg = player.play_playlist_song_by_index(999)
    assert ok is False

    # Scoped search: song in playlist
    ok, msg = player.play_playlist_song_by_title("zaalima")
    assert ok is True
    assert "Zaalima" in msg

    # Scoped search: song NOT in playlist
    ok, msg = player.play_playlist_song_by_title("Random Unknown Song XYZ")
    assert ok is False
    assert "playlist mein nahi hai" in msg


def test_playlist_stop_and_completion():
    """Verify stop_playlist and completion state retention."""
    player = make_test_player()
    player.play_playlist("hindi")
    snap1 = player.get_playlist_snapshot()
    assert snap1["has_active_session"] is True

    # Stop playlist
    player.stop_playlist()
    snap2 = player.get_playlist_snapshot()
    assert snap2["has_active_session"] is False


# ============================================================================
# 3. Router Intent Matching Tests
# ============================================================================

def test_router_playlist_and_music_intents():
    """Verify regex-based routing for playlist and playback control commands."""
    router = CommandRouter()
    st = SessionState.ACTIVE_SESSION

    # Play playlist commands
    assert router.route("play hindi playlist", st).intent_type == IntentType.PLAY_PLAYLIST
    assert router.route("play english playlist", st).intent_type == IntentType.PLAY_PLAYLIST
    assert router.route("start story playlist", st).intent_type == IntentType.PLAY_PLAYLIST
    assert router.route("light hindi playlist play karo", st).intent_type == IntentType.PLAY_PLAYLIST

    # Navigation commands
    assert router.route("next song", st).intent_type == IntentType.NEXT_SONG
    assert router.route("skip track", st).intent_type == IntentType.NEXT_SONG
    assert router.route("agla gaana bajao", st).intent_type == IntentType.NEXT_SONG
    assert router.route("previous song", st).intent_type == IntentType.PREVIOUS_SONG
    assert router.route("pichhla gaana", st).intent_type == IntentType.PREVIOUS_SONG

    # Playback pause/resume/stop
    assert router.route("pause music", st).intent_type == IntentType.PAUSE_MUSIC
    assert router.route("pause song", st).intent_type == IntentType.PAUSE_MUSIC
    assert router.route("resume music", st).intent_type == IntentType.RESUME_MUSIC
    assert router.route("continue playing", st).intent_type == IntentType.RESUME_MUSIC

    # Shuffle and stop playlist
    assert router.route("shuffle playlist", st).intent_type == IntentType.SHUFFLE_PLAYLIST
    assert router.route("toggle shuffle", st).intent_type == IntentType.SHUFFLE_PLAYLIST
    assert router.route("stop playlist", st).intent_type == IntentType.STOP_PLAYLIST


# ============================================================================
# 4. Microphone Toggle & Audio Safeguards Tests
# ============================================================================

def test_speech_listener_mic_mute():
    """Verify listener respects _mic_active toggle immediately."""
    listener = SpeechListener()
    assert listener.is_mic_active is True

    with patch("speech.listener.sr.Microphone"), patch("speech.listener.sr.Recognizer"):
        # Mute listener
        listener.set_mic_active(False)
        assert listener.is_mic_active is False

        # listen() returns None immediately without capturing
        result = listener.listen()
        assert result is None

        # capture_ptt() returns None immediately
        ptt_result = listener.capture_ptt(is_held_fn=lambda: True, max_duration=1.0)
        assert ptt_result is None

        # Unmute
        listener.set_mic_active(True)
        assert listener.is_mic_active is True


def test_assistant_mic_state_toggle():
    """Verify Assistant set_mic_active emits mic_state and does not disrupt player."""
    assistant = LightAssistant.__new__(LightAssistant)
    assistant.listener = SpeechListener()
    assistant.music_player = make_test_player()
    assistant.bridge = MagicMock()
    assistant.is_running = True

    # Toggle to muted
    assistant.set_mic_active(False)
    assert assistant.is_mic_active is False
    assert assistant.listener.is_mic_active is False

    # Check bridge broadcast
    assistant.bridge.broadcast_event.assert_called()
    calls = [c[0][0] for c in assistant.bridge.broadcast_event.call_args_list]
    mic_events = [json.loads(c) for c in calls if '"mic_state"' in str(c)]
    assert len(mic_events) > 0
    assert mic_events[-1]["payload"]["is_active"] is False

    # Unmute
    assistant.set_mic_active(True)
    assert assistant.is_mic_active is True
    assert assistant.listener.is_mic_active is True


# ============================================================================
# 5. Bridge Protocol, Schema & Telemetry Tests
# ============================================================================

def test_bridge_schema_validation():
    """Verify validation of playlist_control and mic_control messages."""
    assert "playlist_control" in ALLOWED_INBOUND_TYPES
    assert "mic_control" in ALLOWED_INBOUND_TYPES

    # Valid playlist control message
    valid_playlist_msg = {
        "schema_version": "1.0",
        "type": "playlist_control",
        "timestamp": 1234567.89,
        "payload": {"action": "toggle_shuffle"},
    }
    is_valid, data, err = validate_incoming_message(json.dumps(valid_playlist_msg))
    assert is_valid is True
    assert err is None

    # Valid select_song message
    valid_select = {
        "schema_version": "1.0",
        "type": "playlist_control",
        "timestamp": 1234567.89,
        "payload": {"action": "select_song", "index": 2},
    }
    is_valid, data, err = validate_incoming_message(json.dumps(valid_select))
    assert is_valid is True

    # Invalid playlist action rejected
    invalid_playlist_msg = {
        "schema_version": "1.0",
        "type": "playlist_control",
        "timestamp": 1234567.89,
        "payload": {"action": "hack_system"},
    }
    is_valid, data, err = validate_incoming_message(json.dumps(invalid_playlist_msg))
    assert is_valid is False
    assert "Unsupported or prohibited playlist action" in err

    # Valid mic control
    valid_mic_msg = {
        "schema_version": "1.0",
        "type": "mic_control",
        "timestamp": 1234567.89,
        "payload": {"action": "set_active", "value": False},
    }
    is_valid, data, err = validate_incoming_message(json.dumps(valid_mic_msg))
    assert is_valid is True

    # Invalid mic control
    invalid_mic = {
        "schema_version": "1.0",
        "type": "mic_control",
        "timestamp": 1234567.89,
        "payload": {"action": "destroy_mic"},
    }
    is_valid, data, err = validate_incoming_message(json.dumps(invalid_mic))
    assert is_valid is False


def test_telemetry_snapshot_includes_playlist_and_mic():
    """Verify TelemetryCollector includes playlist and microphone in snapshot."""
    assistant = LightAssistant.__new__(LightAssistant)
    assistant.listener = SpeechListener()
    assistant.music_player = make_test_player()
    assistant.bridge = MagicMock()
    assistant.is_running = True

    collector = TelemetryCollector()
    collector.set_assistant(assistant)
    snapshot = collector.collect_snapshot()

    assert "playlist" in snapshot
    assert "microphone" in snapshot
    assert snapshot["playlist"]["has_active_session"] is False
    assert snapshot["microphone"]["is_active"] is True


def test_bridge_server_dispatch_playlist_and_mic():
    """Verify WebSocketBridgeServer dispatches playlist and mic actions asynchronously."""
    server = WebSocketBridgeServer(host="127.0.0.1", port=8765)
    player = make_test_player()
    player.play_playlist("hindi")
    server._music_player = player
    mock_assistant = MagicMock()
    server.set_assistant(mock_assistant)

    # Dispatch playlist action
    res = server._dispatch_playlist_action(player, {"action": "toggle_shuffle"})
    assert res["success"] is True

    # Dispatch select song action
    res = server._dispatch_playlist_action(player, {"action": "select_song", "index": 2})
    assert "success" in res

    # Dispatch mic action
    res = server._dispatch_mic_action({"action": "set_active", "value": False})
    assert res["success"] is True
    mock_assistant.set_mic_active.assert_called_with(False)
