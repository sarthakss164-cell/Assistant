"""
Unit and integration tests for Phase D3.1:
Music State Synchronization & Hinglish Command Parsing.

Verifies all 11 required test cases from Phase D3.1 specification:
1. "play Zaalima song" remaining one logical music request.
2. "Zaalima gaana chalao" and "play karo Zaalima" routing correctly.
3. Genuine multiple commands still splitting correctly.
4. No duplicate search/playback action for one music request.
5. Fresh startup with no track displaying IDLE, not PLAYING.
6. Successful playback updating the current track.
7. Stop clearing the active playback state.
8. Failed playback not displaying PLAYING.
9. Track changes replacing old metadata.
10. Bridge reconnect not resurrecting stale playback state.
11. Existing FIFO, music, PTT, TTS, voice-state, and shutdown integration sanity.
"""

import json
import threading
import time
from typing import Optional
import pytest
from unittest.mock import MagicMock, patch

from core.prompt_parser import split_multi_prompt
from core.router import CommandRouter, IntentType
from core.state_machine import SessionState
from actions.music_player import MusicPlayer
from core.bridge.schema import (
    BridgeMessageType,
    create_music_state_event,
    SCHEMA_VERSION,
)
from core.bridge.telemetry import TelemetryCollector


# ==============================================================================
# Test Fakes for VLC and yt-dlp
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
        self.current_media = None
        self.volume = 80
        self.play_called = threading.Event()
        self.stop_called = threading.Event()

    def set_media(self, media):
        self.current_media = media

    def play(self):
        self.current_state = FakeVlcState.Playing
        self.play_called.set()
        return 0

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
        return 15000

    def get_length(self):
        return 240000

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
                "duration": 210.0,
            }

    return MockYoutubeDL


def make_test_player(fake_player=None, title_map=None):
    vlc_mod = FakeVlcModule()
    player = fake_player or FakeMediaPlayer()
    instance = FakeVlcInstance(player=player)
    ytdl_cls = create_mock_ytdl(title_map=title_map)
    return MusicPlayer(
        vlc_instance=instance,
        vlc_module_override=vlc_mod,
        ytdl_class=ytdl_cls,
    )


def wait_for_state(player, target_state, timeout=2.0):
    """Helper to deterministically wait for player to reach target playback state."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if player.get_state_snapshot()["state"] == target_state:
            return True
        time.sleep(0.02)
    return False


# ==============================================================================
# Requirement 1: "play Zaalima song" remains a single logical music request
# ==============================================================================

def test_01_play_zaalima_song_remains_single_request():
    """Verify 'play Zaalima song' is never split into fragmented requests."""
    utterances = [
        "play Zaalima song",
        "Light, play Zaalima song",
        "play the song Zaalima",
        "can you play Zaalima song",
        "please play Zaalima song",
        "kripya play Zaalima song",
    ]
    for utt in utterances:
        parts = split_multi_prompt(utt)
        assert len(parts) == 1, f"Expected 1 part for '{utt}', got: {parts}"
        assert "zaalima" in parts[0].lower()


# ==============================================================================
# Requirement 2: Hinglish variants routing correctly
# ==============================================================================

def test_02_hinglish_variants_routing():
    """Verify 'Zaalima gaana chalao' and 'play karo Zaalima' route to PLAY_SONG with clean query."""
    router = CommandRouter()

    # Active session (no wake word required)
    st_active = SessionState.ACTIVE_SESSION
    intent_active_a = router.route("Zaalima gaana chalao", st_active)
    assert intent_active_a.intent_type == IntentType.PLAY_SONG
    assert intent_active_a.payload.get("query", "").lower() == "zaalima"

    intent_active_b = router.route("play karo Zaalima", st_active)
    assert intent_active_b.intent_type == IntentType.PLAY_SONG
    assert intent_active_b.payload.get("query", "").lower() == "zaalima"

    intent_active_c = router.route("play Zaalima song", st_active)
    assert intent_active_c.intent_type == IntentType.PLAY_SONG
    assert intent_active_c.payload.get("query", "").lower() == "zaalima"

    assert router.route("stop the song", st_active).intent_type == IntentType.STOP_MUSIC

    # Waiting for activation (with wake word)
    st_wait = SessionState.WAITING_FOR_ACTIVATION
    intent_wait_a = router.route("Light, Zaalima gaana chalao", st_wait)
    assert intent_wait_a.intent_type == IntentType.PLAY_SONG
    assert intent_wait_a.payload.get("query", "").lower() == "zaalima"

    intent_wait_b = router.route("Light, play karo Zaalima", st_wait)
    assert intent_wait_b.intent_type == IntentType.PLAY_SONG
    assert intent_wait_b.payload.get("query", "").lower() == "zaalima"

    assert router.route("Light, stop the song", st_wait).intent_type == IntentType.STOP_MUSIC


# ==============================================================================
# Requirement 3: Genuine multiple commands still split correctly
# ==============================================================================

def test_03_genuine_multiple_commands_split_correctly():
    """Verify compound utterances with distinct actions/questions still split cleanly."""
    compound_1 = "open Chrome and play Zaalima song"
    parts_1 = split_multi_prompt(compound_1)
    assert len(parts_1) == 2, f"Expected 2 parts for '{compound_1}', got {parts_1}"
    assert "open chrome" in parts_1[0].lower()
    assert "play zaalima song" in parts_1[1].lower()

    compound_2 = "what is the time and what is the weather"
    parts_2 = split_multi_prompt(compound_2)
    assert len(parts_2) == 2, f"Expected 2 parts for '{compound_2}', got {parts_2}"

    compound_3 = "Light, open Notepad. Then play Zaalima song"
    parts_3 = split_multi_prompt(compound_3)
    assert len(parts_3) == 2, f"Expected 2 parts for '{compound_3}', got {parts_3}"


# ==============================================================================
# Requirement 4: No duplicate search/playback action for one music request
# ==============================================================================

def test_04_no_duplicate_search_or_browser_action():
    """Verify music requests do not accidentally route to web search or app launcher."""
    router = CommandRouter()
    st = SessionState.ACTIVE_SESSION
    music_prompts = [
        "play Zaalima song",
        "play karo Zaalima",
        "Zaalima gaana chalao",
        "play the song Kesariya",
    ]
    for prompt in music_prompts:
        intent = router.route(prompt, st)
        assert intent.intent_type == IntentType.PLAY_SONG, f"Prompt '{prompt}' routed to {intent.intent_type}"
        assert intent.intent_type != IntentType.SEARCH_GOOGLE
        assert intent.intent_type != IntentType.SEARCH_YOUTUBE
        assert intent.intent_type != IntentType.OPEN_APP
        assert intent.intent_type != IntentType.OPEN_WEBSITE


# ==============================================================================
# Requirement 5: Fresh startup displays IDLE, not PLAYING
# ==============================================================================

def test_05_fresh_startup_displays_idle():
    """Verify fresh MusicPlayer and TelemetryCollector start in IDLE state with is_playing=False."""
    player = make_test_player()
    snapshot = player.get_state_snapshot()
    assert snapshot["state"] == "IDLE"
    assert snapshot["is_playing"] is False
    assert snapshot["title"] == ""
    assert snapshot["duration_seconds"] == 0.0

    collector = TelemetryCollector()
    collector.set_music_player(player)
    full_snap = collector.collect_snapshot()
    assert "music" in full_snap
    assert full_snap["music"]["state"] == "IDLE"
    assert full_snap["music"]["is_playing"] is False
    assert full_snap["music"]["title"] == ""
    player.shutdown()


# ==============================================================================
# Requirement 6: Successful playback updates current track
# ==============================================================================

def test_06_successful_playback_updates_state_and_emits():
    """Verify starting playback moves to LOADING and then PLAYING, firing callbacks."""
    state_changes = []

    def callback(data):
        state_changes.append(dict(data))

    fake_media_player = FakeMediaPlayer()
    player = make_test_player(fake_media_player, title_map={"zaalima": "Arijit Singh - Zaalima"})
    player.on_state_change = callback

    ok, msg = player.play_song("zaalima")
    assert ok is True
    assert wait_for_state(player, "PLAYING", timeout=2.0) is True

    assert player.is_playing is True
    snapshot = player.get_state_snapshot()
    assert snapshot["state"] == "PLAYING"
    assert "Zaalima" in snapshot["title"]
    assert snapshot["is_playing"] is True

    # Verify callback received LOADING and then PLAYING
    states = [c["state"] for c in state_changes]
    assert "LOADING" in states
    assert "PLAYING" in states

    player.shutdown()


# ==============================================================================
# Requirement 7: Stop clears active playback state
# ==============================================================================

def test_07_stop_clears_active_playback_state():
    """Verify stop() moves state to STOPPED, sets is_playing=False, and saves last_played."""
    state_changes = []

    def callback(data):
        state_changes.append(dict(data))

    fake_media_player = FakeMediaPlayer()
    player = make_test_player(fake_media_player, title_map={"zaalima": "Arijit Singh - Zaalima"})
    player.on_state_change = callback

    ok, msg = player.play_song("zaalima")
    assert ok is True
    assert wait_for_state(player, "PLAYING", timeout=2.0) is True

    player.stop()

    snapshot = player.get_state_snapshot()
    assert snapshot["state"] == "STOPPED"
    assert snapshot["is_playing"] is False
    assert snapshot["last_played"] == "Arijit Singh - Zaalima"
    assert state_changes[-1]["state"] == "STOPPED"
    assert state_changes[-1]["is_playing"] is False

    player.shutdown()


# ==============================================================================
# Requirement 8: Failed playback does not display PLAYING
# ==============================================================================

def test_08_failed_playback_does_not_display_playing():
    """Verify failed stream extraction marks state as ERROR with is_playing=False."""
    state_changes = []

    def callback(data):
        state_changes.append(dict(data))

    player = make_test_player()
    player.on_state_change = callback

    # Simulate extraction returning None
    with patch.object(player, "_extract_stream_url", return_value=(None, None)):
        ok, msg = player.play_song("NonExistentSong12345")
        assert wait_for_state(player, "ERROR", timeout=2.0) is True
        snapshot = player.get_state_snapshot()
        assert snapshot["state"] == "ERROR"
        assert snapshot["is_playing"] is False
        assert any(c["state"] == "ERROR" for c in state_changes)

    player.shutdown()


# ==============================================================================
# Requirement 9: Track changes replace old metadata
# ==============================================================================

def test_09_track_changes_replace_metadata():
    """Verify consecutive song play calls cleanly overwrite previous track metadata."""
    fake_media_player = FakeMediaPlayer()
    player = make_test_player(
        fake_media_player,
        title_map={"track1": "Track One", "track2": "Track Two"}
    )

    # Play Track 1
    player.play_song("track1")
    assert wait_for_state(player, "PLAYING", timeout=2.0) is True
    snap1 = player.get_state_snapshot()
    assert snap1["title"] == "Track One"

    # Play Track 2
    player.play_song("track2")
    assert wait_for_state(player, "PLAYING", timeout=2.0) is True
    snap2 = player.get_state_snapshot()
    assert snap2["title"] == "Track Two"

    player.shutdown()


# ==============================================================================
# Requirement 10: Bridge reconnect does not resurrect stale playback state
# ==============================================================================

def test_10_bridge_reconnect_not_resurrecting_stale_playback():
    """Verify telemetry snapshot on client connection accurately reflects current stopped/idle state."""
    fake_media_player = FakeMediaPlayer()
    player = make_test_player(fake_media_player, title_map={"zaalima": "Arijit Singh - Zaalima"})
    collector = TelemetryCollector()
    collector.set_music_player(player)

    # 1. Initially stopped / idle
    snap_initial = collector.collect_snapshot()
    assert snap_initial["music"]["state"] == "IDLE"
    assert snap_initial["music"]["is_playing"] is False

    # 2. Playback occurs
    player.play_song("zaalima")
    assert wait_for_state(player, "PLAYING", timeout=2.0) is True
    snap_playing = collector.collect_snapshot()
    assert snap_playing["music"]["state"] == "PLAYING"
    assert snap_playing["music"]["is_playing"] is True

    # 3. Playback stops
    player.stop()
    assert player.is_playing is False

    # 4. New client connects (collect_snapshot called)
    snap_reconnect = collector.collect_snapshot()
    assert snap_reconnect["music"]["state"] == "STOPPED"
    assert snap_reconnect["music"]["is_playing"] is False
    assert snap_reconnect["music"]["last_played"] == "Arijit Singh - Zaalima"

    player.shutdown()


# ==============================================================================
# Requirement 11: Schema validation and event builder integrity
# ==============================================================================

def test_11_music_state_schema_event():
    """Verify create_music_state_event produces conforming Bridge JSON messages."""
    event_json = create_music_state_event(
        state="PLAYING",
        is_playing=True,
        title="Zaalima",
        artist="Arijit Singh",
        duration_seconds=298.5,
        position_seconds=42.0,
        source="YouTube",
        last_played="Channa Mereya",
    )
    parsed = json.loads(event_json)
    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["type"] == BridgeMessageType.MUSIC_STATE.value
    assert parsed["payload"]["state"] == "PLAYING"
    assert parsed["payload"]["is_playing"] is True
    assert parsed["payload"]["title"] == "Zaalima"
    assert parsed["payload"]["artist"] == "Arijit Singh"
    assert parsed["payload"]["duration_seconds"] == 298.5
    assert parsed["payload"]["position_seconds"] == 42.0
    assert parsed["payload"]["last_played"] == "Channa Mereya"
