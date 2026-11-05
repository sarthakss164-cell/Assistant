"""
Unit and integration tests for Phase 8.1: Music Playback Engine.
Verifies thread-safe VLC and yt-dlp playback, sequential playlist sequencing,
prompt stop handling, volume ducking, error resilience, and graceful shutdown.
All tests use mocks; no network calls or real hardware playback are initiated.
"""

import queue
import threading
import time
from typing import Optional, List, Dict, Any
from unittest.mock import MagicMock, patch

import pytest

from actions.music_player import MusicPlayer


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
        self.release_called = threading.Event()

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

    def release(self):
        self.release_called.set()


class FakeVlcInstance:
    def __init__(self, player: Optional[FakeMediaPlayer] = None):
        self.player = player or FakeMediaPlayer()
        self.release_called = threading.Event()

    def media_player_new(self):
        return self.player

    def media_new(self, url):
        return f"VLC_MEDIA_FOR_{url}"

    def release(self):
        self.release_called.set()


def create_mock_ytdl(title_map=None, fail_queries=None):
    """Factory returning a mock yt_dlp.YoutubeDL context manager class."""
    title_map = title_map or {}
    fail_queries = fail_queries or set()

    class MockYoutubeDL:
        def __init__(self, opts=None):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

        def extract_info(self, query, download=False):
            clean = query.replace("ytsearch1:", "").strip()
            if clean in fail_queries:
                raise RuntimeError(f"Simulated extraction failure for '{clean}'")
            title = title_map.get(clean, f"Title for {clean}")
            return {
                "url": f"https://mock-stream.internal/{clean}.mp3",
                "title": title,
            }

    return MockYoutubeDL


@pytest.fixture
def mock_player_env():
    """Returns a fully configured MusicPlayer with mock VLC and yt-dlp."""
    vlc_mod = FakeVlcModule()
    player = FakeMediaPlayer()
    instance = FakeVlcInstance(player=player)
    ytdl_cls = create_mock_ytdl(
        title_map={"zaalima": "Zaalima Song", "song2": "Second Track", "song3": "Third Track"}
    )
    music_player = MusicPlayer(
        vlc_instance=instance,
        vlc_module_override=vlc_mod,
        ytdl_class=ytdl_cls,
        playlists={
            "hindi": ["zaalima", "song2", "song3"],
            "single": ["zaalima"],
        },
        normal_volume=80,
        ducked_volume=20,
    )
    yield music_player, player, instance
    music_player.shutdown()


class TestMusicPlayerCore:
    """Core functionality tests for MusicPlayer."""

    def test_single_song_request_and_playback_init(self, mock_player_env):
        music_player, player, _ = mock_player_env

        ok, msg = music_player.play_song("zaalima")
        assert ok is True
        assert "Zaalima" in msg or "zaalima" in msg
        assert music_player.is_playing is True

        # Wait deterministically for play() to be invoked on VLC
        assert player.play_called.wait(timeout=1.0) is True
        assert player.current_media == "VLC_MEDIA_FOR_https://mock-stream.internal/zaalima.mp3"

    def test_sequential_playlist_playback_progression(self, mock_player_env):
        """
        Critical test: Verifies track 2 does NOT start before track 1 completes.
        Fixes the historical V3.0 playlist skipping bug.
        """
        music_player, player, _ = mock_player_env

        tracks_played = []
        track1_playing = threading.Event()
        track1_finish_signal = threading.Event()
        track2_playing = threading.Event()

        # Intercept set_media to monitor exact track order and timing
        orig_set_media = player.set_media

        def _monitored_set_media(media):
            orig_set_media(media)
            tracks_played.append(media)
            if "zaalima" in media:
                track1_playing.set()
            elif "song2" in media:
                track2_playing.set()

        player.set_media = _monitored_set_media

        # Custom get_state to simulate track 1 playing until signaled, then Ending
        def _dynamic_get_state():
            if len(tracks_played) == 1:
                if track1_finish_signal.is_set():
                    return FakeVlcState.Ended
                return FakeVlcState.Playing
            elif len(tracks_played) >= 2:
                return FakeVlcState.Playing
            return FakeVlcState.Stopped

        player.get_state = _dynamic_get_state

        ok, msg = music_player.play_playlist("hindi")
        assert ok is True
        assert music_player.is_playing is True

        # 1. Track 1 must start
        assert track1_playing.wait(timeout=1.0) is True
        assert len(tracks_played) == 1
        assert "zaalima" in tracks_played[0]

        # 2. Track 2 must NOT have started while Track 1 is still Playing
        time.sleep(0.05)
        assert len(tracks_played) == 1

        # 3. Signal Track 1 completion -> worker advances to Track 2
        track1_finish_signal.set()
        assert track2_playing.wait(timeout=1.0) is True
        assert len(tracks_played) >= 2
        assert "song2" in tracks_played[1]

    def test_stop_request_interrupts_playlist_promptly(self, mock_player_env):
        music_player, player, _ = mock_player_env

        ok, _ = music_player.play_playlist("hindi")
        assert ok is True
        assert player.play_called.wait(timeout=1.0) is True

        # Stop playback
        music_player.stop()

        assert music_player.is_playing is False
        assert music_player.current_track is None
        assert music_player.current_playlist is None
        assert player.stop_called.is_set()

    def test_failed_track_does_not_crash_worker(self, mock_player_env):
        """Failed track (yt-dlp extraction error) must be skipped, next track attempted."""
        music_player, player, _ = mock_player_env

        # Inject fail_queries for first track 'zaalima'
        music_player._ytdl_class = create_mock_ytdl(
            title_map={"song2": "Second Track"},
            fail_queries={"zaalima"},
        )

        second_track_started = threading.Event()
        orig_set_media = player.set_media

        def _track_spy(media):
            orig_set_media(media)
            if "song2" in media:
                second_track_started.set()

        player.set_media = _track_spy

        ok, _ = music_player.play_playlist("hindi")
        assert ok is True

        # Worker should recover from zaalima failure and advance to song2
        assert second_track_started.wait(timeout=1.5) is True
        assert player.current_media == "VLC_MEDIA_FOR_https://mock-stream.internal/song2.mp3"

    def test_repeated_stop_and_cleanup_are_safe(self, mock_player_env):
        music_player, player, _ = mock_player_env

        # Repeated stop calls should succeed without error
        assert music_player.stop() is True
        assert music_player.stop() is True
        assert music_player.stop() is True

        # Repeated cleanup / shutdown calls should succeed
        music_player.cleanup()
        music_player.cleanup()
        music_player.shutdown()
        assert music_player.is_playing is False


class TestMusicPlayerVolumeDucking:
    """Tests for volume preservation, ducking, and restoration."""

    def test_original_volume_preserved_and_restored_exactly(self, mock_player_env):
        music_player, player, _ = mock_player_env
        player.volume = 75

        assert music_player.duck_volume() is True
        assert music_player.is_ducked is True
        assert player.volume == 20

        assert music_player.restore_volume() is True
        assert music_player.is_ducked is False
        assert player.volume == 75

    def test_original_volume_below_50_preserved_exactly(self, mock_player_env):
        music_player, player, _ = mock_player_env
        player.volume = 35

        music_player.duck_volume()
        assert player.volume == 20

        music_player.restore_volume()
        assert player.volume == 35

    def test_repeated_duck_requests_do_not_overwrite_original_volume(self, mock_player_env):
        music_player, player, _ = mock_player_env
        player.volume = 90

        # First duck
        music_player.duck_volume()
        assert player.volume == 20

        # Second duck while already ducked
        music_player.duck_volume()
        assert player.volume == 20

        # Third duck with custom target
        music_player.duck_volume(target_volume=15)
        assert player.volume == 15

        # Restore must restore to the initial 90, NOT 20 or 15
        music_player.restore_volume()
        assert player.volume == 90
        assert music_player.is_ducked is False

    def test_repeated_restore_requests_are_safe(self, mock_player_env):
        music_player, player, _ = mock_player_env
        player.volume = 80

        music_player.duck_volume()
        assert player.volume == 20

        music_player.restore_volume()
        assert player.volume == 80

        # Second restore is a safe no-op
        assert music_player.restore_volume() is True
        assert player.volume == 80


class TestMusicPlayerResilienceAndLifecycle:
    """Edge cases, lifecycle shutdown, and dependency unavailability."""

    def test_missing_vlc_or_ytdlp_fails_gracefully(self):
        player_missing_vlc = MusicPlayer(
            vlc_instance=None,
            vlc_module_override=None,
            ytdl_class=create_mock_ytdl(),
        )
        assert player_missing_vlc.is_available is False
        ok, msg = player_missing_vlc.play_song("Zaalima")
        assert ok is False
        assert "available nahi hai" in msg

        player_missing_ytdl = MusicPlayer(
            vlc_instance=FakeVlcInstance(),
            vlc_module_override=FakeVlcModule(),
            ytdl_class=None,
        )
        assert player_missing_ytdl.is_available is False
        ok, msg = player_missing_ytdl.play_song("Zaalima")
        assert ok is False
        assert "available nahi hai" in msg

    def test_duplicate_worker_creation_is_prevented(self, mock_player_env):
        music_player, _, _ = mock_player_env

        music_player.play_song("song1")
        w1 = music_player._worker_thread
        assert w1 is not None and w1.is_alive()

        # Enqueue another song while worker is running
        music_player.play_song("song2")
        w2 = music_player._worker_thread

        # Same worker thread must be reused
        assert w1 is w2

    def test_new_playback_request_replaces_current_queue(self, mock_player_env):
        music_player, _, _ = mock_player_env

        music_player.play_playlist("hindi")
        assert music_player.current_playlist == "hindi"

        # Request a single song while playlist is queued
        music_player.play_song("Zaalima single")

        # Previous playlist queue should be replaced
        assert music_player.current_playlist is None
        assert music_player.current_track == "Zaalima single"

    def test_shutdown_signals_worker_and_releases_resources(self, mock_player_env):
        music_player, player, instance = mock_player_env

        music_player.play_song("test_track")
        assert music_player.is_playing is True

        music_player.shutdown()

        assert music_player.is_playing is False
        assert music_player._shutdown_event.is_set()
        assert player.release_called.is_set()
        assert instance.release_called.is_set()
