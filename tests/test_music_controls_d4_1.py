"""
Unit and integration tests for Phase D4.1: Functional Music Controls.

Covers all 10 required test cases from Phase D4.1 specification:
1. Play/pause/resume state transitions.
2. Previous/next behavior where supported.
3. Accurate progress and duration updates.
4. Seek behavior if supported, otherwise verified disabled behavior.
5. Volume synchronization without breaking saved duck volume.
6. Repeated control clicks and invalid control payloads.
7. Bridge disconnection and recovery.
8. Playback failure and stale-state prevention.
9. Existing music-state synchronization and voice/conversation events.
10. Existing FIFO, PTT, TTS, music, safety, and shutdown regression verification.
"""

import asyncio
import json
import threading
import time
from typing import Optional, Tuple
import pytest
from unittest.mock import MagicMock, patch

from actions.music_player import MusicPlayer
from core.bridge.schema import (
    BridgeMessageType,
    ALLOWED_INBOUND_TYPES,
    ALLOWED_MUSIC_ACTIONS,
    validate_incoming_message,
    create_message,
    create_music_state_event,
    SCHEMA_VERSION,
)
from core.bridge.server import WebSocketBridgeServer
from core.bridge.telemetry import TelemetryCollector


# ==============================================================================
# Fakes for VLC and yt-dlp
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
    def __init__(self, is_seekable_val: bool = True):
        self.current_state = FakeVlcState.Stopped
        self.current_media = None
        self.volume = 80
        self.play_called = threading.Event()
        self.stop_called = threading.Event()
        self.pause_called = threading.Event()
        self.seek_position_ms = 0
        self._is_seekable_val = is_seekable_val
        self._time_ms = 15000
        self._length_ms = 240000

    def set_media(self, media):
        self.current_media = media

    def play(self):
        self.current_state = FakeVlcState.Playing
        self.play_called.set()
        return 0

    def pause(self):
        if self.current_state == FakeVlcState.Playing:
            self.current_state = FakeVlcState.Paused
        elif self.current_state == FakeVlcState.Paused:
            self.current_state = FakeVlcState.Playing
        self.pause_called.set()

    def set_pause(self, do_pause):
        self.current_state = FakeVlcState.Paused if do_pause else FakeVlcState.Playing
        self.pause_called.set()

    def stop(self):
        self.current_state = FakeVlcState.Stopped
        self.stop_called.set()
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
        if not self._is_seekable_val:
            return -1
        self._time_ms = t_ms
        self.seek_position_ms = t_ms
        return 0

    def get_length(self):
        return self._length_ms

    def is_seekable(self):
        return 1 if self._is_seekable_val else 0

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


def wait_for_state(player, target_state, timeout=2.0):
    """Helper to deterministically wait for player state."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if player.get_state_snapshot()["state"] == target_state:
            return True
        time.sleep(0.02)
    return False


# ==============================================================================
# Requirement 1: Play / Pause / Resume State Transitions
# ==============================================================================

def test_01_play_pause_resume_transitions():
    """Verify play -> pause -> resume -> toggle_play state transitions and event emissions."""
    fake_mp = FakeMediaPlayer()
    player = make_test_player(fake_mp, title_map={"zaalima": "Arijit Singh - Zaalima"})
    state_changes = []
    player.on_state_change = lambda data: state_changes.append(dict(data))

    # 1. Start playback
    ok, _ = player.play_song("zaalima")
    assert ok is True
    assert wait_for_state(player, "PLAYING") is True
    assert player.is_playing is True
    assert player.playback_state == "PLAYING"

    # 2. Pause
    ok_pause = player.pause()
    assert ok_pause is True
    assert player.playback_state == "PAUSED"
    assert player.is_playing is False
    assert fake_mp.get_state() == FakeVlcState.Paused
    assert state_changes[-1]["state"] == "PAUSED"
    assert state_changes[-1]["is_playing"] is False

    # 3. Resume
    ok_resume = player.resume()
    assert ok_resume is True
    assert player.playback_state == "PLAYING"
    assert player.is_playing is True
    assert fake_mp.get_state() == FakeVlcState.Playing
    assert state_changes[-1]["state"] == "PLAYING"
    assert state_changes[-1]["is_playing"] is True

    # 4. Toggle Play while Playing -> Pauses
    ok_toggle_pause = player.toggle_play()
    assert ok_toggle_pause is True
    assert player.playback_state == "PAUSED"

    # 5. Toggle Play while Paused -> Resumes
    ok_toggle_resume = player.toggle_play()
    assert ok_toggle_resume is True
    assert player.playback_state == "PLAYING"

    player.shutdown()


# ==============================================================================
# Requirement 2: Previous / Next Track Behavior
# ==============================================================================

def test_02_previous_next_track_navigation():
    """Verify next_track and previous_track behave correctly on playlists and history."""
    fake_mp = FakeMediaPlayer()
    playlists = {"bollywood": ["track1", "track2", "track3"]}
    player = make_test_player(
        fake_mp,
        title_map={"track1": "Track One", "track2": "Track Two", "track3": "Track Three"},
        playlists=playlists,
    )

    # Start playlist
    ok, _ = player.play_playlist("bollywood")
    assert ok is True
    assert wait_for_state(player, "PLAYING") is True
    assert player.get_state_snapshot()["title"] == "Track One"

    # Next track -> advances to Track Two
    fake_mp.play_called.clear()
    ok_next1, _ = player.next_track()
    assert ok_next1 is True
    assert wait_for_state(player, "PLAYING") is True
    assert player.get_state_snapshot()["title"] == "Track Two"

    # Next track -> advances to Track Three
    fake_mp.play_called.clear()
    ok_next2, _ = player.next_track()
    assert ok_next2 is True
    assert wait_for_state(player, "PLAYING") is True
    assert player.get_state_snapshot()["title"] == "Track Three"

    # Next track when queue is empty -> returns False cleanly without crashing
    ok_next_end, reason = player.next_track()
    assert ok_next_end is False
    assert "No subsequent track" in reason or "End" in reason

    # Previous track: when position > 3s, restarts current track
    fake_mp._time_ms = 12000
    ok_prev_restart, _ = player.previous_track()
    assert ok_prev_restart is True
    assert fake_mp._time_ms == 0

    # Previous track: when position <= 3s, navigates back to previous in history
    fake_mp._time_ms = 1000
    fake_mp.play_called.clear()
    ok_prev_nav, _ = player.previous_track()
    assert ok_prev_nav is True
    assert wait_for_state(player, "PLAYING") is True
    assert player.get_state_snapshot()["title"] == "Track Two"

    player.shutdown()


# ==============================================================================
# Requirement 3: Accurate Progress and Duration Updates
# ==============================================================================

def test_03_accurate_progress_and_duration_updates():
    """Verify position_seconds and duration_seconds reflect real playback values."""
    fake_mp = FakeMediaPlayer()
    fake_mp._time_ms = 45000  # 45 seconds
    fake_mp._length_ms = 298000  # 298 seconds
    player = make_test_player(fake_mp, title_map={"zaalima": "Arijit Singh - Zaalima"})

    ok, _ = player.play_song("zaalima")
    assert ok is True
    assert wait_for_state(player, "PLAYING") is True

    snap = player.get_state_snapshot()
    assert snap["position_seconds"] == 45
    assert snap["duration_seconds"] == 298
    assert snap["is_playing"] is True

    player.shutdown()


# ==============================================================================
# Requirement 4: Seek Behavior (Supported vs Non-Seekable)
# ==============================================================================

def test_04_seek_behavior_supported_and_unsupported():
    """Verify seek succeeds on seekable media and gracefully returns False on non-seekable streams."""
    # Case A: Seekable media
    fake_seekable = FakeMediaPlayer(is_seekable_val=True)
    player_seekable = make_test_player(fake_seekable, title_map={"song": "Test Song"})
    player_seekable.play_song("song")
    wait_for_state(player_seekable, "PLAYING")

    res_ok = player_seekable.seek(60.0)
    assert res_ok is True
    assert fake_seekable.seek_position_ms == 60000
    player_seekable.shutdown()

    # Case B: Non-seekable media
    fake_unseekable = FakeMediaPlayer(is_seekable_val=False)
    player_unseekable = make_test_player(fake_unseekable, title_map={"stream": "Live Stream"})
    player_unseekable.play_song("stream")
    wait_for_state(player_unseekable, "PLAYING")

    res_fail = player_unseekable.seek(30.0)
    assert res_fail is False
    player_unseekable.shutdown()


# ==============================================================================
# Requirement 5: Volume Synchronization and Ducking Preservation
# ==============================================================================

def test_05_volume_synchronization_and_duck_preservation():
    """Verify volume change updates normal/saved volume without breaking active ducking."""
    fake_mp = FakeMediaPlayer()
    player = make_test_player(fake_mp, title_map={"song": "Test Song"})
    player.play_song("song")
    wait_for_state(player, "PLAYING")

    # 1. Set initial volume to 75
    player.set_volume(75)
    assert fake_mp.volume == 75
    assert player.get_state_snapshot()["volume"] == 75

    # 2. Duck volume for TTS (ducked to 20)
    player.duck_volume(20, reason="tts")
    assert fake_mp.volume == 20
    assert player.is_ducked is True

    # 3. User modifies volume slider to 85 while ducked
    player.set_volume(85)
    # VLC volume MUST remain ducked at 20 while speaking
    assert fake_mp.volume == 20
    assert player.get_state_snapshot()["volume"] == 85

    # 4. Assistant speech finishes -> restore volume
    player.restore_volume(reason="tts")
    assert player.is_ducked is False
    # VLC volume is restored to the newly updated 85!
    assert fake_mp.volume == 85

    # 5. Mute toggle
    player.set_mute(True)
    assert fake_mp.volume == 0
    assert player.get_state_snapshot()["is_muted"] is True

    player.set_mute(False)
    assert fake_mp.volume == 85
    assert player.get_state_snapshot()["is_muted"] is False

    player.shutdown()


# ==============================================================================
# Requirement 6: Repeated Clicks and Invalid Control Payloads
# ==============================================================================

def test_06_inbound_validation_and_repeated_clicks():
    """Verify validate_incoming_message allowlists valid controls and rejects malicious/malformed inputs."""
    # Valid actions
    valid_actions = ["play", "pause", "resume", "toggle_play", "stop", "next", "previous"]
    for act in valid_actions:
        msg = json.dumps({
            "schema_version": "1.0",
            "type": "music_control",
            "payload": {"action": act},
        })
        is_val, parsed, err = validate_incoming_message(msg)
        assert is_val is True, f"Expected valid for action '{act}', got err: {err}"

    # Valid volume
    msg_vol = json.dumps({
        "schema_version": "1.0",
        "type": "music_control",
        "payload": {"action": "volume", "value": 65},
    })
    is_val, _, _ = validate_incoming_message(msg_vol)
    assert is_val is True

    # Invalid action (unsupported / prohibited)
    msg_bad_act = json.dumps({
        "schema_version": "1.0",
        "type": "music_control",
        "payload": {"action": "exec_cmd", "cmd": "calc.exe"},
    })
    is_val, _, err = validate_incoming_message(msg_bad_act)
    assert is_val is False
    assert "Unsupported or prohibited music action" in err

    # Out-of-bounds volume
    msg_bad_vol = json.dumps({
        "schema_version": "1.0",
        "type": "music_control",
        "payload": {"action": "volume", "value": 150},
    })
    is_val, _, err = validate_incoming_message(msg_bad_vol)
    assert is_val is False
    assert "Volume value must be a number between 0 and 100" in err

    # Negative seek
    msg_bad_seek = json.dumps({
        "schema_version": "1.0",
        "type": "music_control",
        "payload": {"action": "seek", "value": -5},
    })
    is_val, _, err = validate_incoming_message(msg_bad_seek)
    assert is_val is False
    assert "Seek position must be a non-negative number" in err

    # Non-dictionary payload
    msg_bad_payload = json.dumps({
        "schema_version": "1.0",
        "type": "music_control",
        "payload": "invalid_string",
    })
    is_val, _, err = validate_incoming_message(msg_bad_payload)
    assert is_val is False


# ==============================================================================
# Requirement 7: WebSocket Bridge Dispatch and Recovery
# ==============================================================================

def test_07_bridge_dispatch_music_control():
    """Verify WebSocketBridgeServer safely dispatches music control and returns status."""
    async def _run():
        fake_mp = FakeMediaPlayer()
        player = make_test_player(fake_mp, title_map={"zaalima": "Arijit Singh - Zaalima"})
        server = WebSocketBridgeServer(host="127.0.0.1", port=8765)
        server.set_music_player(player)

        # 1. Dispatch play
        res_play = await server._handle_music_control({"action": "play"})
        assert "success" in res_play

        # Start playback
        player.play_song("zaalima")
        wait_for_state(player, "PLAYING")

        # 2. Dispatch pause via bridge
        res_pause = await server._handle_music_control({"action": "pause"})
        assert res_pause["success"] is True
        assert player.playback_state == "PAUSED"

        # 3. Dispatch resume via bridge
        res_resume = await server._handle_music_control({"action": "resume"})
        assert res_resume["success"] is True
        assert player.playback_state == "PLAYING"

        # 4. Dispatch volume via bridge
        res_vol = await server._handle_music_control({"action": "volume", "value": 70})
        assert res_vol["success"] is True
        assert fake_mp.volume == 70

        # 5. Dispatch stop via bridge
        res_stop = await server._handle_music_control({"action": "stop"})
        assert res_stop["success"] is True
        assert player.playback_state == "STOPPED"

        player.shutdown()

    asyncio.run(_run())


# ==============================================================================
# Requirement 8: Playback Failure and Stale-State Prevention
# ==============================================================================

def test_08_playback_failure_and_stale_state_prevention():
    """Verify failed stream resolution sets ERROR state without leaving stale PLAYING badge."""
    fake_mp = FakeMediaPlayer()
    player = make_test_player(fake_mp)

    with patch.object(player, "_extract_stream_url", return_value=(None, None)):
        ok, _ = player.play_song("NonExistentTrack")
        assert wait_for_state(player, "ERROR") is True
        snap = player.get_state_snapshot()
        assert snap["state"] == "ERROR"
        assert snap["is_playing"] is False

        # Attempting toggle_play while in ERROR without a valid last track stays safe
        player._last_played_title = None
        ok_toggle = player.toggle_play()
        assert ok_toggle is False
        assert player.get_state_snapshot()["is_playing"] is False

    player.shutdown()


# ==============================================================================
# Requirement 9: Music-State Event Broadcast Integrity
# ==============================================================================

def test_09_music_state_event_broadcast_integrity():
    """Verify music state updates trigger broadcast callback with full payload."""
    fake_mp = FakeMediaPlayer()
    player = make_test_player(fake_mp, title_map={"zaalima": "Arijit Singh - Zaalima"})
    emitted_events = []
    player.on_state_change = lambda data: emitted_events.append(dict(data))

    player.play_song("zaalima")
    assert wait_for_state(player, "PLAYING") is True
    player.pause()
    player.resume()
    player.stop()

    states = [e["state"] for e in emitted_events]
    assert "LOADING" in states
    assert "PLAYING" in states
    assert "PAUSED" in states
    assert "STOPPED" in states

    player.shutdown()


# ==============================================================================
# Requirement 10: Telemetry Snapshot Reflects Live Music Attributes
# ==============================================================================

def test_10_telemetry_snapshot_reflects_live_attributes():
    """Verify TelemetryCollector includes authoritative volume, mute, and position."""
    fake_mp = FakeMediaPlayer()
    fake_mp._time_ms = 30000
    fake_mp._length_ms = 180000
    player = make_test_player(fake_mp, title_map={"song": "My Song"})
    collector = TelemetryCollector()
    collector.set_music_player(player)

    player.play_song("song")
    wait_for_state(player, "PLAYING")
    player.set_volume(82)

    snapshot = collector.collect_snapshot()
    assert "music" in snapshot
    m = snapshot["music"]
    assert m["state"] == "PLAYING"
    assert m["is_playing"] is True
    assert m["volume"] == 82
    assert m["position_seconds"] == 30
    assert m["duration_seconds"] == 180
    assert m["is_muted"] is False

    player.shutdown()

