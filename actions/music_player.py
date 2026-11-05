"""
Music Player Module for Light AI V1.0 (Phase 8.1).
Provides thread-safe background audio playback using VLC and yt-dlp.
Supports single song queries, sequential playlist execution, volume ducking, and stop controls.
"""

import collections
from dataclasses import dataclass, field
import os
from pathlib import Path
import queue
import random
import re
import shutil
import sys
import threading
import time
from typing import Optional, Tuple, Dict, List, Any, Union
import uuid

from config.settings import (
    VLC_DIR,
    MUSIC_NORMAL_VOLUME,
    MUSIC_DUCKED_VOLUME,
    DEFAULT_PLAYLISTS,
)
from config.playlist_loader import load_playlists, get_legacy_playlists_dict
from utils.logger import logger


@dataclass
class PlaylistSession:
    """Authoritative active playlist session state."""
    playlist_id: str
    name: str
    original_entries: List[Dict[str, str]]
    playback_order: List[int]
    current_index: int = 0
    is_shuffle: bool = False
    state: str = "IDLE"  # "IDLE" | "PLAYING" | "PAUSED" | "COMPLETED" | "STOPPED"
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    revision: int = 1

    @property
    def has_active_session(self) -> bool:
        return self.state in ("PLAYING", "PAUSED", "COMPLETED") and bool(self.original_entries)

# Windows DLL loading for libvlc
VLC_AVAILABLE = False
vlc_module = None

if sys.platform == "win32" and os.path.exists(str(VLC_DIR)):
    try:
        os.add_dll_directory(str(VLC_DIR))
    except Exception as e:
        logger.debug(f"[MUSIC] os.add_dll_directory notice: {e}")

try:
    import vlc as _vlc
    vlc_module = _vlc
    VLC_AVAILABLE = True
except (ImportError, OSError) as e:
    logger.debug(f"[MUSIC] Native VLC bindings unavailable: {e}")
    vlc_module = None
    VLC_AVAILABLE = False

try:
    import yt_dlp as _yt_dlp
    ytdl_module = _yt_dlp
    YTDLP_AVAILABLE = True
except ImportError as e:
    logger.debug(f"[MUSIC] yt-dlp module unavailable: {e}")
    ytdl_module = None
    YTDLP_AVAILABLE = False


_UNSET = object()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MASTER_COOKIE_PATH = PROJECT_ROOT / "assets" / "cookies.txt"
DEFAULT_RUNTIME_COOKIE_PATH = PROJECT_ROOT / "cookies.txt"


def setup_cookies(
    master_path: Optional[Union[str, Path]] = None,
    runtime_path: Optional[Union[str, Path]] = None,
) -> Optional[str]:
    """
    Safe two-file yt-dlp cookie management routine.
    - Master: assets/cookies.txt (original provided file, never modified by app or yt-dlp)
    - Runtime: cookies.txt (root directory, dynamically updated by yt-dlp)

    Rules:
    1. Master file must NEVER be modified by application code or yt-dlp.
    2. If master exists & non-empty and runtime is missing/empty, initialize runtime from master.
    3. If both exist & non-empty, preserve both (do not overwrite runtime).
    4. If master is missing or empty, do not overwrite valid runtime with empty.
    5. Returns the absolute resolved path to the runtime cookie file, or None if unavailable.
    """
    master = Path(master_path).resolve() if master_path is not None else DEFAULT_MASTER_COOKIE_PATH
    runtime = Path(runtime_path).resolve() if runtime_path is not None else DEFAULT_RUNTIME_COOKIE_PATH

    try:
        # Ensure assets directory exists without creating fake or empty cookie files
        master.parent.mkdir(parents=True, exist_ok=True)

        master_exists = master.is_file()
        master_has_data = master_exists and (master.stat().st_size > 0)

        runtime_exists = runtime.is_file()
        runtime_has_data = runtime_exists and (runtime.stat().st_size > 0)

        # Case 1: Master has data, runtime is missing or empty -> initialize runtime from master
        if master_has_data and not runtime_has_data:
            shutil.copy2(master, runtime)
            logger.info(f"[MUSIC] Initialized runtime cookie file from master: {runtime}")
            return str(runtime.resolve())

        # Case 2: Both exist with data -> preserve both, never overwrite runtime
        if master_has_data and runtime_has_data:
            logger.debug(f"[MUSIC] Both master and runtime cookie files exist; using runtime: {runtime}")
            return str(runtime.resolve())

        # Case 3: Master is missing or empty, but runtime has data -> preserve and use runtime
        if not master_has_data and runtime_has_data:
            logger.info(
                f"[MUSIC] Master cookie file missing or empty ({master}); "
                f"preserving existing runtime cookies: {runtime}"
            )
            return str(runtime.resolve())

        # Case 4: Neither has valid data -> log notice without printing content, return None
        logger.info("[MUSIC] No valid cookie file found. yt-dlp will proceed without cookies.")
        return None

    except Exception as e:
        logger.warning(f"[MUSIC] Cookie file setup error: {e}")
        if runtime.is_file() and runtime.stat().st_size > 0:
            return str(runtime.resolve())
        return None


class MusicPlayer:
    """
    Thread-safe music player managing VLC playback and yt-dlp streaming URL resolution.
    Runs playback in a dedicated daemon worker thread.
    """

    def __init__(
        self,
        vlc_instance: Optional[Any] = None,
        vlc_module_override: Any = _UNSET,
        ytdl_class: Any = _UNSET,
        playlists: Optional[Dict[str, List[str]]] = None,
        normal_volume: int = MUSIC_NORMAL_VOLUME,
        ducked_volume: int = MUSIC_DUCKED_VOLUME,
        master_cookie_path: Optional[Union[str, Path]] = None,
        runtime_cookie_path: Optional[Union[str, Path]] = None,
    ):
        self._vlc_module = vlc_module if vlc_module_override is _UNSET else vlc_module_override
        self._ytdl_class = (
            (ytdl_module.YoutubeDL if YTDLP_AVAILABLE else None)
            if ytdl_class is _UNSET
            else ytdl_class
        )
        self.playlists: Dict[str, List[str]] = playlists or DEFAULT_PLAYLISTS
        self._normal_volume = normal_volume
        self._ducked_volume = ducked_volume

        # Cookie architecture (Master in assets/cookies.txt, Runtime in cookies.txt)
        self._master_cookie_path = (
            Path(master_cookie_path).resolve()
            if master_cookie_path is not None
            else DEFAULT_MASTER_COOKIE_PATH
        )
        self._runtime_cookie_path = (
            Path(runtime_cookie_path).resolve()
            if runtime_cookie_path is not None
            else DEFAULT_RUNTIME_COOKIE_PATH
        )
        self._cookie_file: Optional[str] = self._setup_cookie_files()

        # Volume state management
        self._saved_volume = self._normal_volume
        self._is_ducked = False
        self._duck_reasons: set[str] = set()
        self._volume_lock = threading.Lock()

        # Playback concurrency & queues
        self._track_queue: queue.Queue = queue.Queue()
        self._state_lock = threading.RLock()
        self._stop_event = threading.Event()
        self._shutdown_event = threading.Event()
        self._skip_track_event = threading.Event()
        self._track_history: collections.deque[str] = collections.deque(maxlen=20)
        self._is_muted: bool = False
        self._playlist_session: Optional[PlaylistSession] = None

        self._is_playing = False
        self._is_track_playing = False
        self._playback_state: str = "IDLE"  # "IDLE" | "LOADING" | "PLAYING" | "PAUSED" | "STOPPED" | "ERROR"
        self._current_track: Optional[str] = None
        self._current_artist: Optional[str] = None
        self._current_duration: int = 0
        self._last_played_title: Optional[str] = None
        self._current_playlist: Optional[str] = None
        self._last_extracted_meta: Dict[str, Any] = {}
        self.on_state_change: Optional[Any] = None

        self._worker_thread: Optional[threading.Thread] = None

        # Initialize VLC instance and player if available
        self._vlc_instance = vlc_instance
        self._player = None

        if self._vlc_module and not self._vlc_instance:
            try:
                self._vlc_instance = self._vlc_module.Instance("--no-xlib", "--quiet")
            except Exception as e:
                logger.warning(f"[MUSIC] Failed to create VLC instance: {e}")
                self._vlc_instance = None

        if self._vlc_instance:
            try:
                self._player = self._vlc_instance.media_player_new()
            except Exception as e:
                logger.warning(f"[MUSIC] Failed to create VLC media player: {e}")
                self._player = None

    @property
    def is_available(self) -> bool:
        """Indicates whether VLC and yt-dlp dependencies are available."""
        return (self._vlc_module is not None) and (self._ytdl_class is not None)

    @property
    def is_playing(self) -> bool:
        """Returns True if audio playback is actively ongoing or tracks are queued."""
        with self._state_lock:
            return self._is_playing

    @property
    def is_ducked(self) -> bool:
        """Returns True if volume is currently ducked."""
        with self._volume_lock:
            return self._is_ducked

    @property
    def current_track(self) -> Optional[str]:
        """Returns the title or query of the currently playing track."""
        with self._state_lock:
            return self._current_track

    @property
    def current_playlist(self) -> Optional[str]:
        """Returns the name of the currently active playlist, if any."""
        with self._state_lock:
            return self._current_playlist

    @property
    def has_active_playlist(self) -> bool:
        """Returns True if there is an active playlist session."""
        with self._state_lock:
            return bool(self._playlist_session and self._playlist_session.has_active_session)

    def get_current_track(self) -> Optional[str]:
        """Returns the title or query of the currently playing track."""
        return self.current_track

    def get_is_playing(self) -> bool:
        """Returns True if audio playback is actively ongoing or tracks are queued."""
        return self.is_playing

    @property
    def master_cookie_path(self) -> Path:
        """Returns the configured master cookie file path (assets/cookies.txt)."""
        return self._master_cookie_path

    @property
    def runtime_cookie_path(self) -> Path:
        """Returns the configured runtime cookie file path (cookies.txt)."""
        return self._runtime_cookie_path

    @property
    def cookie_file(self) -> Optional[str]:
        """Returns the absolute resolved runtime cookie path passed to yt-dlp, or None."""
        return self._cookie_file

    @property
    def playback_state(self) -> str:
        """Returns the current playback state: IDLE, LOADING, PLAYING, PAUSED, STOPPED, or ERROR."""
        with self._state_lock:
            return self._playback_state

    def get_state_snapshot(self) -> Dict[str, Any]:
        """Returns authoritative snapshot of current music playback state and metadata."""
        with self._state_lock:
            pos_sec = 0
            dur_sec = self._current_duration or 0
            if self._player and self._is_track_playing:
                try:
                    t_ms = self._player.get_time()
                    if isinstance(t_ms, (int, float)) and t_ms > 0:
                        pos_sec = int(t_ms / 1000)
                    l_ms = self._player.get_length()
                    if isinstance(l_ms, (int, float)) and l_ms > 0:
                        dur_sec = int(l_ms / 1000)
                except Exception:
                    pass

            is_active = (self._playback_state == "PLAYING")
            disp_title = self._current_track or (self._last_played_title if self._last_played_title else "")
            disp_subtitle = self._current_artist or ("LAST PLAYED" if (self._last_played_title and not is_active) else "STANDBY // READY FOR AUDIO")

            session = self._playlist_session
            playlist_snap = {
                "has_active_session": bool(session is not None),
                "playlist_id": session.playlist_id if session else None,
                "name": session.name if session else None,
                "entries": [
                    {
                        "id": f"{session.playlist_id}_{i}",
                        "title": session.original_entries[idx]["title"],
                        "query": session.original_entries[idx]["query"],
                    }
                    for i, idx in enumerate(session.playback_order)
                ] if session else [],
                "current_index": session.current_index if session else -1,
                "is_shuffle": session.is_shuffle if session else False,
                "state": session.state if session else "IDLE",
                "revision": session.revision if session else 0,
            }

            return {
                "state": self._playback_state,
                "is_playing": is_active,
                "title": disp_title,
                "artist": disp_subtitle,
                "duration_seconds": dur_sec,
                "position_seconds": pos_sec,
                "source": "VIA CUSTOM PLAYER",
                "playlist": session.name if session else self._current_playlist,
                "playlist_session": playlist_snap,
                "last_played": self._last_played_title,
                "volume": self._normal_volume,
                "is_muted": getattr(self, "_is_muted", False),
                "is_ducked": self._is_ducked,
            }

    def get_playlist_snapshot(self) -> Dict[str, Any]:
        """Returns snapshot of current playlist session."""
        with self._state_lock:
            session = self._playlist_session
            return {
                "has_active_session": bool(session is not None),
                "playlist_id": session.playlist_id if session else None,
                "name": session.name if session else None,
                "entries": [
                    {
                        "id": f"{session.playlist_id}_{i}",
                        "title": session.original_entries[idx]["title"],
                        "query": session.original_entries[idx]["query"],
                    }
                    for i, idx in enumerate(session.playback_order)
                ] if session else [],
                "current_index": session.current_index if session else -1,
                "is_shuffle": session.is_shuffle if session else False,
                "state": session.state if session else "IDLE",
                "revision": session.revision if session else 0,
            }

    def _emit_state_change(self) -> None:
        """Notifies registered listeners of music state updates."""
        if self.on_state_change:
            try:
                snapshot = self.get_state_snapshot()
                self.on_state_change(snapshot)
            except Exception as e:
                logger.debug(f"[MUSIC] on_state_change callback notice: {e}")

    def _setup_cookie_files(self) -> Optional[str]:
        """Runs the two-file cookie management routine for this player instance."""
        return setup_cookies(self._master_cookie_path, self._runtime_cookie_path)

    def _ensure_worker_running(self) -> None:
        """Ensures the background daemon worker thread is active."""
        with self._state_lock:
            if self._worker_thread is None or not self._worker_thread.is_alive():
                self._worker_thread = threading.Thread(
                    target=self._worker_loop,
                    name="LightMusicWorker",
                    daemon=True,
                )
                self._worker_thread.start()

    def _extract_stream_url(self, query: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Resolves a search query or URL into a playable audio stream URL via yt-dlp.
        Returns:
            (stream_url, title) or (None, None) on failure.
        """
        if not self._ytdl_class:
            logger.warning("[MUSIC] yt-dlp is not available for audio extraction.")
            return None, None

        clean_query = query.strip()
        if not clean_query:
            return None, None

        if clean_query.startswith("http://") or clean_query.startswith("https://"):
            search_target = clean_query
        else:
            search_target = f"ytsearch1:{clean_query}"

        ydl_opts = {
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }
        # Configure cookiefile using runtime path only (never master)
        if self._cookie_file and os.path.isfile(self._cookie_file):
            ydl_opts["cookiefile"] = str(Path(self._cookie_file).resolve())

        try:
            with self._ytdl_class(ydl_opts) as ydl:
                info = ydl.extract_info(search_target, download=False)
                if not info:
                    return None, None
                if "entries" in info and info["entries"]:
                    entry = info["entries"][0]
                else:
                    entry = info
                stream_url = entry.get("url")
                title = entry.get("title", clean_query)
                self._last_extracted_meta = {
                    "duration": int(entry.get("duration") or 0),
                    "artist": entry.get("artist") or entry.get("uploader") or entry.get("channel") or "",
                }
                return stream_url, title
        except Exception as e:
            logger.error(f"[MUSIC] Audio extraction failed for '{query}': {e}")
            return None, None

    def _play_single_track_sync(self, track_query: str) -> bool:
        """
        Synchronously resolves, loads, and plays a single track until completion or stop.
        Called exclusively by the background worker thread.
        """
        if self._stop_event.is_set() or self._shutdown_event.is_set():
            return False

        url, title = self._extract_stream_url(track_query)
        if not url:
            logger.warning(f"[MUSIC] Skipping unresolvable track: '{track_query}'")
            with self._state_lock:
                self._playback_state = "ERROR"
                self._is_track_playing = False
                self._is_playing = False
            self._emit_state_change()
            return False

        with self._state_lock:
            self._track_history.append(track_query)

        if self._stop_event.is_set() or self._shutdown_event.is_set():
            return False

        if not self._vlc_instance or not self._player:
            logger.warning("[MUSIC] VLC player unavailable for playback.")
            return False

        try:
            media = self._vlc_instance.media_new(url)
            self._player.set_media(media)

            with self._volume_lock:
                target_vol = self._ducked_volume if self._is_ducked else self._saved_volume
                self._player.audio_set_volume(target_vol)

            self._player.play()
            logger.info(f"[MUSIC] Started playback: '{title}' (vol={target_vol})")

            with self._state_lock:
                if self._stop_event.is_set() or self._shutdown_event.is_set():
                    try:
                        self._player.stop()
                    except Exception:
                        pass
                    return False
                self._current_track = title
                self._last_played_title = title
                meta = getattr(self, "_last_extracted_meta", {})
                self._current_artist = meta.get("artist") or ""
                self._current_duration = meta.get("duration") or 0
                self._playback_state = "PLAYING"
                self._is_playing = True
                self._is_track_playing = True
            self._emit_state_change()

            # Bounded wait for playback to transition into Playing/Buffering (allow up to 15s for network stream)
            start_wait = time.time()
            while time.time() - start_wait < 15.0:
                if self._stop_event.is_set() or self._shutdown_event.is_set():
                    self._player.stop()
                    with self._state_lock:
                        self._is_track_playing = False
                    return False

                state = self._player.get_state()
                if state in (self._vlc_module.State.Playing, self._vlc_module.State.Buffering):
                    with self._volume_lock:
                        target_vol = self._ducked_volume if self._is_ducked else self._saved_volume
                        self._player.audio_set_volume(target_vol)
                    break
                if state in (self._vlc_module.State.Ended, self._vlc_module.State.Error, self._vlc_module.State.Stopped):
                    logger.warning(f"[MUSIC] Track '{title}' ended prematurely with state: {state}")
                    with self._state_lock:
                        self._playback_state = "ERROR" if state == self._vlc_module.State.Error else "STOPPED"
                        self._is_track_playing = False
                    self._emit_state_change()
                    return False
                time.sleep(0.05)

            # Wait for track completion or interruption
            while not self._stop_event.is_set() and not self._shutdown_event.is_set():
                if self._skip_track_event.is_set():
                    logger.info(f"[MUSIC] Track '{title}' skipped by user command.")
                    self._skip_track_event.clear()
                    break
                state = self._player.get_state()
                if state in (self._vlc_module.State.Ended, self._vlc_module.State.Stopped, self._vlc_module.State.Error):
                    logger.info(f"[MUSIC] Track finished with state: {state}")
                    break
                if self._stop_event.wait(timeout=0.1):
                    break

            try:
                self._player.stop()
            except Exception:
                pass

            with self._state_lock:
                self._is_track_playing = False
                if self._stop_event.is_set():
                    self._playback_state = "STOPPED"
                elif self._track_queue.empty():
                    self._playback_state = "IDLE"
                    self._is_playing = False
                    self._current_track = None
            self._emit_state_change()
            return True

        except Exception as e:
            logger.error(f"[MUSIC] Error during track playback: {e}", exc_info=True)
            with self._state_lock:
                self._playback_state = "ERROR"
                self._is_track_playing = False
                self._is_playing = False
            self._emit_state_change()
            return False

    def _worker_loop(self) -> None:
        """Dedicated daemon worker loop processing queued tracks sequentially."""
        while not self._shutdown_event.is_set():
            try:
                track_query = self._track_queue.get(timeout=0.2)
            except queue.Empty:
                with self._state_lock:
                    if self._track_queue.empty() and not self._is_track_playing:
                        if self._playlist_session and self._playlist_session.state == "COMPLETED":
                            self._is_playing = False
                        else:
                            self._is_playing = False
                            self._current_track = None
                            self._current_artist = None
                            self._current_duration = 0
                            if self._playback_state not in ("STOPPED", "ERROR"):
                                self._playback_state = "IDLE"
                continue

            if self._stop_event.is_set():
                self._track_queue.task_done()
                continue

            try:
                self._play_single_track_sync(track_query)
            except Exception as e:
                logger.error(f"[MUSIC] Unexpected worker exception: {e}")
            finally:
                self._track_queue.task_done()

            with self._state_lock:
                if self._stop_event.is_set():
                    continue

                if self._playlist_session and self._playlist_session.state not in ("STOPPED", "IDLE"):
                    if not self._skip_track_event.is_set() and self._track_queue.empty() and not self._is_track_playing:
                        # Check if more tracks remain in active playback order
                        if self._playlist_session.current_index + 1 < len(self._playlist_session.playback_order):
                            self._playlist_session.current_index += 1
                            self._playlist_session.state = "PLAYING"
                            self._playlist_session.revision += 1
                            next_orig_idx = self._playlist_session.playback_order[self._playlist_session.current_index]
                            next_entry = self._playlist_session.original_entries[next_orig_idx]
                            self._track_queue.put(next_entry["query"])
                            self._current_track = next_entry["title"]
                            self._current_artist = ""
                            self._playback_state = "LOADING"
                            self._is_playing = True
                        else:
                            # Final song completed
                            logger.info(f"[MUSIC] Final playlist song completed for '{self._playlist_session.name}'.")
                            self._playlist_session.state = "COMPLETED"
                            self._playlist_session.revision += 1
                            self._is_playing = False
                            self._is_track_playing = False
                            self._playback_state = "IDLE"
                            self._current_track = None
                            self._current_artist = None
                            self._current_duration = 0
                else:
                    if self._track_queue.empty() and not self._is_track_playing:
                        self._is_playing = False
                        self._current_track = None
                        self._current_artist = None
                        self._current_duration = 0
                        self._current_playlist = None
                        if self._playback_state not in ("STOPPED", "ERROR"):
                            self._playback_state = "IDLE"
            self._emit_state_change()

    def play_song(self, query: str) -> Tuple[bool, str]:
        """
        Stops current playback and schedules a standalone single track for playback.
        Clears any active playlist session.
        Non-blocking.
        Returns:
            (success: bool, status_message: str)
        """
        clean_query = (query or "").strip()
        if not clean_query:
            return False, "Gaane ka naam nahi mila."

        if not self.is_available:
            return False, "VLC ya yt-dlp dependency available nahi hai."

        # Stop existing playback and clear pending tracks
        self.stop()

        with self._state_lock:
            self._playlist_session = None
            self._stop_event.clear()
            self._playback_state = "LOADING"
            self._current_playlist = None
            self._current_track = clean_query
            self._current_artist = ""
            self._current_duration = 0
            self._is_playing = True
            self._track_queue.put(clean_query)
        self._emit_state_change()

        self._ensure_worker_running()
        logger.info(f"[MUSIC] Enqueued standalone song: '{clean_query}'")
        return True, f"'{clean_query}' play kar rahi hoon."

    def play_playlist(self, name: str, shuffle: bool = False) -> Tuple[bool, str]:
        """
        Stops current playback and starts an authoritative PlaylistSession.
        Loads playlist from config/playlist.json (or injected playlists dict).
        Non-blocking.
        Returns:
            (success: bool, status_message: str)
        """
        clean_name = (name or "").strip().lower()
        if not clean_name:
            return False, "Playlist ka naam nahi mila."

        if not self.is_available:
            return False, "VLC ya yt-dlp dependency available nahi hai."

        matched_key = None
        pl_data = None

        # 1. Check custom self.playlists first if explicitly provided (e.g. mock playlists in tests)
        if self.playlists is not None and self.playlists is not DEFAULT_PLAYLISTS and isinstance(self.playlists, dict):
            for k in self.playlists:
                if k.lower() == clean_name or clean_name in k.lower():
                    matched_key = k
                    val = self.playlists[k]
                    if isinstance(val, dict) and "songs" in val:
                        pl_data = val
                    elif isinstance(val, list):
                        pl_data = {
                            "name": k.capitalize(),
                            "songs": [
                                s if isinstance(s, dict) else {"title": str(s), "query": str(s)}
                                for s in val
                            ],
                        }
                    break

        # 2. Check loaded playlists from config/playlist.json
        if not matched_key:
            try:
                loaded_pl = load_playlists()
                for k, v in loaded_pl.items():
                    if k.lower() == clean_name or clean_name in k.lower() or clean_name in v.get("name", "").lower():
                        matched_key = k
                        pl_data = v
                        break
            except Exception as e:
                logger.debug(f"[MUSIC] load_playlists lookup notice: {e}")

        if not matched_key or not pl_data or not pl_data.get("songs"):
            return False, f"Playlist '{name}' nahi mili."

        entries = pl_data["songs"]
        n = len(entries)
        order = list(range(n))
        if shuffle:
            random.shuffle(order)

        session = PlaylistSession(
            playlist_id=matched_key,
            name=pl_data.get("name", matched_key.capitalize()),
            original_entries=entries,
            playback_order=order,
            current_index=0,
            is_shuffle=bool(shuffle),
            state="PLAYING",
        )

        # Stop existing playback
        self.stop()

        with self._state_lock:
            self._playlist_session = session
            self._current_playlist = matched_key
            self._stop_event.clear()
            self._playback_state = "LOADING"
            first_entry = entries[order[0]]
            self._current_track = first_entry["title"]
            self._current_artist = ""
            self._current_duration = 0
            self._is_playing = True
            self._track_queue.put(first_entry["query"])

        self._emit_state_change()
        self._ensure_worker_running()
        logger.info(f"[MUSIC] Started playlist session '{matched_key}' ({n} tracks, shuffle={shuffle})")
        return True, f"{session.name} playlist play kar rahi hoon."

    def play_playlist_song_by_title(self, title_query: str) -> Tuple[bool, str]:
        """
        Searches ONLY within the active playlist session for a matching song title.
        If found: plays the matching playlist entry and updates current index.
        If not found: returns (False, f"Sir, {title_query} playlist mein nahi hai.")
        Does NOT invoke global YouTube/music search or modify playlist entries.
        """
        clean_q = (title_query or "").strip()
        if not clean_q:
            return False, "Gaane ka naam nahi mila."

        with self._state_lock:
            session = self._playlist_session
            if not session or not session.original_entries:
                return False, "Koi active playlist session nahi hai."

            normalized_query = re.sub(r"[^\w\s]", "", clean_q.lower()).strip()
            matched_orig_idx = None
            matched_title = ""

            for idx, entry in enumerate(session.original_entries):
                entry_norm = re.sub(r"[^\w\s]", "", entry["title"].lower()).strip()
                if entry_norm == normalized_query:
                    matched_orig_idx = idx
                    matched_title = entry["title"]
                    break

            if matched_orig_idx is None:
                for idx, entry in enumerate(session.original_entries):
                    entry_norm = re.sub(r"[^\w\s]", "", entry["title"].lower()).strip()
                    if normalized_query in entry_norm or entry_norm in normalized_query:
                        matched_orig_idx = idx
                        matched_title = entry["title"]
                        break

            if matched_orig_idx is None:
                return False, f"Sir, {clean_q} playlist mein nahi hai."

            try:
                order_idx = session.playback_order.index(matched_orig_idx)
            except ValueError:
                order_idx = 0

            return self.play_playlist_song_by_index(order_idx)

    def play_playlist_song_by_index(self, index: int) -> Tuple[bool, str]:
        """
        Plays the song at the specified index within the current active playback order.
        Thread-safe and authoritative.
        """
        with self._state_lock:
            session = self._playlist_session
            if not session:
                return False, "Koi active playlist session nahi hai."

            if not (0 <= index < len(session.playback_order)):
                return False, f"Invalid playlist index: {index}"

            session.current_index = index
            session.state = "PLAYING"
            session.revision += 1

            orig_idx = session.playback_order[index]
            target_entry = session.original_entries[orig_idx]
            query = target_entry["query"]
            title = target_entry["title"]

            # Drain queue
            while not self._track_queue.empty():
                try:
                    self._track_queue.get_nowait()
                    self._track_queue.task_done()
                except Exception:
                    break

            self._stop_event.clear()
            self._skip_track_event.set()
            if self._player:
                try:
                    self._player.stop()
                except Exception:
                    pass

            self._playback_state = "LOADING"
            self._current_track = title
            self._current_artist = ""
            self._is_playing = True
            self._track_queue.put(query)

        self._emit_state_change()
        self._ensure_worker_running()
        return True, f"Playing '{title}' from playlist."

    def toggle_shuffle(self) -> Tuple[bool, bool]:
        """
        Toggles shuffle mode on the active playlist session.
        When enabled: creates a shuffled playback order, preserving the current track.
        When disabled: restores exact original configured order, preserving the current track index.
        Returns:
            (success: bool, is_shuffle_enabled: bool)
        """
        with self._state_lock:
            session = self._playlist_session
            if not session or not session.original_entries:
                return False, False

            n = len(session.original_entries)
            if n <= 1:
                session.is_shuffle = not session.is_shuffle
                session.revision += 1
                self._emit_state_change()
                return True, session.is_shuffle

            curr_orig_idx = session.playback_order[session.current_index] if (0 <= session.current_index < len(session.playback_order)) else 0

            if not session.is_shuffle:
                # Enable shuffle: current track stays first
                remaining = [i for i in range(n) if i != curr_orig_idx]
                random.shuffle(remaining)
                session.playback_order = [curr_orig_idx] + remaining
                session.current_index = 0
                session.is_shuffle = True
                session.revision += 1
                self._emit_state_change()
                logger.info(f"[MUSIC] Shuffle enabled for playlist '{session.name}'.")
                return True, True
            else:
                # Disable shuffle: restore original [0, 1, ..., n-1]
                session.playback_order = list(range(n))
                session.current_index = curr_orig_idx
                session.is_shuffle = False
                session.revision += 1
                self._emit_state_change()
                logger.info(f"[MUSIC] Shuffle disabled for playlist '{session.name}'.")
                return True, False

    def stop_playlist(self) -> bool:
        """
        Dedicated STOP PLAYLIST control:
        Stops current playlist track, drains queue, clears active playlist session,
        and transitions UI to NO ACTIVE PLAYLIST state.
        """
        self._stop_event.set()

        while not self._track_queue.empty():
            try:
                self._track_queue.get_nowait()
                self._track_queue.task_done()
            except Exception:
                break

        if self._player:
            try:
                self._player.stop()
            except Exception:
                pass

        with self._volume_lock:
            if self._is_ducked and self._player:
                try:
                    self._player.audio_set_volume(self._saved_volume)
                except Exception:
                    pass
            self._duck_reasons.clear()
            self._is_ducked = False

        with self._state_lock:
            if self._current_track:
                self._last_played_title = self._current_track
            self._playlist_session = None
            self._current_playlist = None
            self._playback_state = "STOPPED"
            self._is_playing = False
            self._is_track_playing = False
            self._current_track = None
            self._current_artist = None
            self._current_duration = 0

        self._emit_state_change()
        logger.info("[MUSIC] Playlist stopped and session cleared.")
        return True

    def stop(self) -> bool:
        """
        Stops current playback immediately, empties queue, and clears playlist session.
        Thread-safe and idempotent.
        """
        self._stop_event.set()

        # Drain pending queue
        while not self._track_queue.empty():
            try:
                self._track_queue.get_nowait()
                self._track_queue.task_done()
            except (queue.Empty, ValueError):
                break

        if self._player:
            try:
                self._player.stop()
            except Exception as e:
                logger.debug(f"[MUSIC] Player stop notice: {e}")

        with self._volume_lock:
            if self._is_ducked and self._player:
                try:
                    self._player.audio_set_volume(self._saved_volume)
                except Exception:
                    pass
            self._duck_reasons.clear()
            self._is_ducked = False

        with self._state_lock:
            if self._current_track:
                self._last_played_title = self._current_track
            self._playback_state = "STOPPED"
            self._is_playing = False
            self._is_track_playing = False
            self._current_track = None
            self._current_artist = None
            self._current_duration = 0
            self._current_playlist = None
            self._playlist_session = None
        self._emit_state_change()

        logger.info("[MUSIC] Playback stopped and queue cleared.")
        return True

    def pause(self) -> bool:
        """Pauses the currently playing track."""
        with self._state_lock:
            if not self._player or self._playback_state != "PLAYING":
                return False
            try:
                if hasattr(self._player, "set_pause"):
                    self._player.set_pause(1)
                elif hasattr(self._player, "pause"):
                    self._player.pause()
                self._playback_state = "PAUSED"
                self._is_playing = False
                if self._playlist_session:
                    self._playlist_session.state = "PAUSED"
                    self._playlist_session.revision += 1
            except Exception as e:
                logger.warning(f"[MUSIC] Failed to pause: {e}")
                return False
        self._emit_state_change()
        logger.info("[MUSIC] Playback paused.")
        return True

    def resume(self) -> bool:
        """Resumes playback of the paused track."""
        with self._state_lock:
            if not self._player:
                return False
            if self._playlist_session and self._playlist_session.state == "COMPLETED":
                return self.play_playlist_song_by_index(0)[0]
            if self._playback_state != "PAUSED":
                return False
            try:
                if hasattr(self._player, "set_pause"):
                    self._player.set_pause(0)
                elif hasattr(self._player, "play"):
                    self._player.play()
                self._playback_state = "PLAYING"
                self._is_playing = True
                if self._playlist_session:
                    self._playlist_session.state = "PLAYING"
                    self._playlist_session.revision += 1
            except Exception as e:
                logger.warning(f"[MUSIC] Failed to resume: {e}")
                return False
        self._emit_state_change()
        logger.info("[MUSIC] Playback resumed.")
        return True

    def toggle_play(self) -> bool:
        """Toggles between play/resume and pause based on authoritative state."""
        with self._state_lock:
            curr_state = self._playback_state
        if curr_state == "PLAYING":
            return self.pause()
        elif curr_state == "PAUSED":
            return self.resume()
        elif curr_state in ("IDLE", "STOPPED"):
            if self._playlist_session:
                idx = self._playlist_session.current_index if self._playlist_session.current_index >= 0 else 0
                return self.play_playlist_song_by_index(idx)[0]
            if self._last_played_title:
                ok, _ = self.play_song(self._last_played_title)
                return ok
            return False
        return False

    def next_track(self) -> Tuple[bool, str]:
        """
        Selects next entry in current playlist order.
        Disabled in standalone mode (no playlist session).
        """
        with self._state_lock:
            session = self._playlist_session
            if not session:
                return False, "Playlist navigation unavailable in standalone mode."

            if session.current_index + 1 < len(session.playback_order):
                next_idx = session.current_index + 1
            else:
                return False, "End of playlist reached."

        return self.play_playlist_song_by_index(next_idx)

    def previous_track(self) -> Tuple[bool, str]:
        """
        Restarts current track if elapsed > 3.0s, or steps to previous track in playlist.
        Disabled in standalone mode (no playlist session).
        """
        with self._state_lock:
            session = self._playlist_session
            if not session:
                return False, "Playlist navigation unavailable in standalone mode."

            pos_sec = 0
            if self._player and self._is_track_playing:
                try:
                    t_ms = self._player.get_time()
                    if isinstance(t_ms, (int, float)) and t_ms > 0:
                        pos_sec = int(t_ms / 1000)
                except Exception:
                    pass
            if pos_sec <= 0 and getattr(self, "_position_seconds", 0) > 0:
                pos_sec = int(self._position_seconds)

            if pos_sec > 3 and self._player:
                try:
                    if hasattr(self._player, "set_time"):
                        self._player.set_time(0)
                        self._position_seconds = 0.0
                        logger.info("[MUSIC] Restarted current playlist track from beginning.")
                        return True, "Track restarted from beginning."
                except Exception:
                    pass

            if session.current_index > 0:
                prev_idx = session.current_index - 1
                return self.play_playlist_song_by_index(prev_idx)
            else:
                if self._player and hasattr(self._player, "set_time"):
                    try:
                        self._player.set_time(0)
                    except Exception:
                        pass
                return True, "At beginning of playlist; track restarted."

    def seek(self, position_seconds: float) -> bool:
        """Attempts to seek to target position in seconds if supported by media."""
        with self._state_lock:
            if not self._player or self._playback_state not in ("PLAYING", "PAUSED"):
                return False
            try:
                if hasattr(self._player, "is_seekable") and not self._player.is_seekable():
                    logger.debug("[MUSIC] Media stream is not seekable.")
                    return False
                target_ms = max(0, int(position_seconds * 1000))
                if hasattr(self._player, "set_time"):
                    res = self._player.set_time(target_ms)
                    return res == 0 or res is True
            except Exception as e:
                logger.warning(f"[MUSIC] Seek exception: {e}")
                return False
        return False

    def set_mute(self, is_muted: bool) -> bool:
        """Mutes or unmutes playback volume without losing normal volume setting."""
        with self._volume_lock:
            self._is_muted = bool(is_muted)
            if self._is_muted:
                if self._player:
                    try:
                        self._player.audio_set_volume(0)
                    except Exception:
                        pass
            else:
                target = self._ducked_volume if self._is_ducked else self._saved_volume
                if self._player:
                    try:
                        self._player.audio_set_volume(target)
                    except Exception:
                        pass
            self._emit_state_change()
            return True

    def duck_volume(self, target_volume: Optional[int] = None, reason: str = "default") -> bool:
        """
        Temporarily reduces music volume (e.g. during Push-to-Talk or assistant speech).
        Guarantees that repeated calls do not overwrite the original volume setting.
        Supports overlapping duck reasons without premature volume restoration.
        """
        with self._volume_lock:
            if not self._is_ducked:
                current_vol = -1
                if self._player:
                    try:
                        current_vol = self._player.audio_get_volume()
                    except Exception:
                        current_vol = -1

                if isinstance(current_vol, (int, float)) and current_vol > self._ducked_volume:
                    self._saved_volume = int(current_vol)
                elif isinstance(getattr(self, "_saved_volume", None), (int, float)) and self._saved_volume > self._ducked_volume:
                    pass
                else:
                    self._saved_volume = self._normal_volume
                self._is_ducked = True

            self._duck_reasons.add(reason)

            effective_duck = target_volume if target_volume is not None else self._ducked_volume
            if self._player:
                try:
                    self._player.audio_set_volume(effective_duck)
                except Exception as e:
                    logger.debug(f"[MUSIC] Failed to set ducked volume: {e}")

            logger.info(
                f"[MUSIC] Volume ducked to {effective_duck} (reason='{reason}', "
                f"active_reasons={sorted(list(self._duck_reasons))}, original={self._saved_volume})"
            )
            return True

    def restore_volume(self, reason: str = "default", force: bool = False) -> bool:
        """
        Restores music volume to the exact saved level prior to ducking.
        Safe against repeated calls.
        If other active duck reasons exist, volume remains ducked until all reasons are cleared.
        """
        with self._volume_lock:
            if not self._is_ducked:
                self._duck_reasons.discard(reason)
                return True

            self._duck_reasons.discard(reason)

            if self._duck_reasons and not force:
                logger.info(f"[MUSIC] Volume remains ducked due to active reasons: {sorted(list(self._duck_reasons))}")
                return True

            self._duck_reasons.clear()
            if self._player:
                try:
                    self._player.audio_set_volume(self._saved_volume)
                except Exception as e:
                    logger.warning(f"[MUSIC] Failed to restore volume: {e}")

            self._is_ducked = False
            logger.info(f"[MUSIC] Volume restored to {self._saved_volume} (reason='{reason}')")
            return True

    def set_volume(self, volume: int) -> bool:
        """Sets the normal music playback volume (0-100)."""
        with self._volume_lock:
            self._normal_volume = max(0, min(100, int(volume)))
            if not self._is_ducked:
                self._saved_volume = self._normal_volume
                if self._player:
                    try:
                        self._player.audio_set_volume(self._normal_volume)
                    except Exception as e:
                        logger.debug(f"[MUSIC] Failed to set volume: {e}")
            else:
                self._saved_volume = self._normal_volume
            return True

    def cleanup(self) -> None:
        """Alias for shutdown."""
        self.shutdown()

    def shutdown(self) -> None:
        """Stops all playback, drains queues, terminates worker, and releases VLC handles."""
        logger.info("Initiating MusicPlayer shutdown...")
        self._shutdown_event.set()
        self.stop()

        if self._player:
            try:
                self._player.stop()
                if hasattr(self._player, "release"):
                    self._player.release()
            except Exception as e:
                logger.debug(f"[MUSIC] Player release exception: {e}")
            self._player = None

        if self._vlc_instance:
            try:
                if hasattr(self._vlc_instance, "release"):
                    self._vlc_instance.release()
            except Exception as e:
                logger.debug(f"[MUSIC] Instance release exception: {e}")
            self._vlc_instance = None

        logger.info("MusicPlayer cleanly shutdown.")
