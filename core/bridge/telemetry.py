"""
Real-time Windows system telemetry collector for LIGHT AI V1.0.
Collects non-blocking CPU, RAM, disk, battery, and process data using psutil and Windows APIs.
Handles missing hardware, headless environments, and access-denied states gracefully.
"""

import collections
import ctypes
import os
import sys
import threading
import time
from typing import Any, Dict, Optional

try:
    import psutil
except ImportError:
    psutil = None


class TelemetryCollector:
    """
    Thread-safe, non-blocking telemetry collector for Windows systems.
    Maintains CPU history buffer and formats telemetry for bridge delivery.
    """

    def __init__(self, history_length: int = 20):
        self._history_length = history_length
        self._cpu_history: collections.deque[float] = collections.deque(
            [0.0] * history_length, maxlen=history_length
        )
        self._history_lock = threading.Lock()
        self._last_sample_time: float = 0.0
        self._music_player: Optional[Any] = None
        self._gateway_client: Optional[Any] = None
        self._session_memory: Optional[Any] = None
        self._assistant: Optional[Any] = None

        # Prime the psutil cpu_percent tracker non-blockingly
        if psutil:
            try:
                psutil.cpu_percent(interval=None)
            except Exception:
                pass

    def get_system_metrics(self) -> Dict[str, Any]:
        """
        Samples actual CPU, RAM, Disk, and Battery readings.
        Handles missing battery hardware and unavailable metrics gracefully.
        """
        if not psutil:
            return {
                "ram_used_gb": 0.0,
                "ram_total_gb": 0.0,
                "ram_percent": 0.0,
                "cpu_percent": 0.0,
                "cpu_history": list(self._cpu_history),
                "storage_used_gb": 0.0,
                "storage_total_gb": 0.0,
                "storage_percent": 0.0,
                "storage_drive": "C:",
                "battery_percent": None,
                "battery_charging": False,
                "has_battery": False,
                "error": "psutil library not available",
            }

        # 1. CPU Usage (non-blocking sampling)
        try:
            cpu_val = float(psutil.cpu_percent(interval=None))
        except Exception:
            cpu_val = 0.0

        with self._history_lock:
            self._cpu_history.append(cpu_val)
            cpu_history_snapshot = list(self._cpu_history)

        # 2. RAM Usage
        try:
            mem = psutil.virtual_memory()
            ram_used_gb = round(mem.used / (1024**3), 1)
            ram_total_gb = round(mem.total / (1024**3), 1)
            ram_percent = round(mem.percent, 1)
        except Exception:
            ram_used_gb = 0.0
            ram_total_gb = 0.0
            ram_percent = 0.0

        # 3. Disk Usage (System Drive)
        sys_drive = os.environ.get("SystemDrive", "C:")
        if not sys_drive.endswith("\\"):
            sys_drive_path = f"{sys_drive}\\"
        else:
            sys_drive_path = sys_drive

        try:
            disk = psutil.disk_usage(sys_drive_path)
            storage_used_gb = round(disk.used / (1024**3), 1)
            storage_total_gb = round(disk.total / (1024**3), 1)
            storage_percent = round(disk.percent, 1)
            storage_drive_label = sys_drive.rstrip("\\")
        except Exception:
            storage_used_gb = 0.0
            storage_total_gb = 0.0
            storage_percent = 0.0
            storage_drive_label = "C:"

        # 4. Battery / Power Cell
        try:
            batt = psutil.sensors_battery()
            if batt is not None:
                battery_percent = round(batt.percent, 1)
                battery_charging = bool(batt.power_plugged)
                has_battery = True
            else:
                battery_percent = None
                battery_charging = True  # Operating on AC mains
                has_battery = False
        except Exception:
            battery_percent = None
            battery_charging = True
            has_battery = False

        return {
            "ram_used_gb": ram_used_gb,
            "ram_total_gb": ram_total_gb,
            "ram_percent": ram_percent,
            "cpu_percent": cpu_val,
            "cpu_history": cpu_history_snapshot,
            "storage_used_gb": storage_used_gb,
            "storage_total_gb": storage_total_gb,
            "storage_percent": storage_percent,
            "storage_drive": storage_drive_label,
            "battery_percent": battery_percent,
            "battery_charging": battery_charging,
            "has_battery": has_battery,
        }

    def get_foreground_window_info(self) -> Dict[str, Any]:
        """
        Retrieves the current foreground window title, process name, and PID
        using Windows User32 APIs, with safe handling of headless/access-denied states.
        """
        if sys.platform != "win32":
            return {
                "foreground_app": "NON-WINDOWS PLATFORM",
                "foreground_pid": None,
            }

        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return {
                    "foreground_app": "DESKTOP / SYSTEM",
                    "foreground_pid": None,
                }

            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            target_pid = pid.value if pid.value else None

            # Get Window Title
            length = user32.GetWindowTextLengthW(hwnd)
            title = ""
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value.strip()

            proc_name = ""
            if target_pid and psutil:
                try:
                    p = psutil.Process(target_pid)
                    proc_name = p.name()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    proc_name = "System"
                except Exception:
                    proc_name = "Unknown"

            # Clean and truncate overly long title for HUD presentation
            if len(title) > 45:
                title = title[:42] + "..."

            if proc_name and title:
                display_label = f"{proc_name.upper()} ({title})"
            elif proc_name:
                display_label = proc_name.upper()
            elif title:
                display_label = title.upper()
            else:
                display_label = "ACTIVE FOREGROUND APPLICATION"

            return {
                "foreground_app": display_label,
                "foreground_pid": target_pid,
            }
        except Exception:
            return {
                "foreground_app": "DESKTOP ENVIRONMENT",
                "foreground_pid": None,
            }

    def get_process_watcher_data(self) -> Dict[str, Any]:
        """
        Inspects real foreground and background process states.
        Only reports genuine background workers (e.g. assistant children or core process);
        never invents fake worker processes.
        """
        t0 = time.time()
        fg_info = self.get_foreground_window_info()

        active_process = "IDLE (NO ACTIVE WORKER)"
        active_pid: Optional[int] = None

        if psutil:
            try:
                curr_proc = psutil.Process()
                children = curr_proc.children(recursive=True)
                if children:
                    # Pick the most recent active child worker
                    child = children[0]
                    active_process = f"{child.name()} [CHILD WORKER]"
                    active_pid = child.pid
                else:
                    # Check if any dedicated tool workers are running system-wide
                    found_worker = False
                    for p in psutil.process_iter(["name", "pid"]):
                        try:
                            n = (p.info["name"] or "").lower()
                            if "yt-dlp" in n or "vlc" in n or "ffmpeg" in n:
                                active_process = f"{p.info['name']} [ACTIVE WORKER]"
                                active_pid = p.info["pid"]
                                found_worker = True
                                break
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            continue

                    if not found_worker:
                        # Report current assistant runtime process
                        active_process = f"{curr_proc.name()} [LIGHT AI ENGINE]"
                        active_pid = curr_proc.pid
            except Exception:
                active_process = "LIGHT AI ENGINE [STANDBY]"
                active_pid = os.getpid()

        latency_ms = max(1, round((time.time() - t0) * 1000))

        return {
            "foreground_app": fg_info.get("foreground_app", "DESKTOP / SYSTEM"),
            "foreground_pid": fg_info.get("foreground_pid"),
            "active_process": active_process,
            "active_process_pid": active_pid,
            "tool_latency_ms": latency_ms,
        }

    def set_music_player(self, player: Any) -> None:
        """Sets the authoritative MusicPlayer instance for telemetry snapshots."""
        self._music_player = player

    def set_gateway_client(self, client: Any) -> None:
        """Sets the active CoeGatewayClient instance for AI Core telemetry."""
        self._gateway_client = client

    def set_session_memory(self, memory: Any) -> None:
        """Sets the active SessionMemory instance for AI Core telemetry."""
        self._session_memory = memory

    def set_assistant(self, assistant: Any) -> None:
        """Sets the active assistant instance for querying microphone, gateway, and memory."""
        self._assistant = assistant
        if assistant:
            if hasattr(assistant, "gateway_client") and self._gateway_client is None:
                self.set_gateway_client(assistant.gateway_client)
            if hasattr(assistant, "session_memory") and self._session_memory is None:
                self.set_session_memory(assistant.session_memory)

    def collect_snapshot(self) -> Dict[str, Any]:
        """
        Collects a full telemetry and process watcher snapshot for broadcast.
        """
        sys_metrics = self.get_system_metrics()
        proc_watcher = self.get_process_watcher_data()

        music_snapshot = {
            "state": "IDLE",
            "is_playing": False,
            "title": "",
            "artist": "",
            "duration_seconds": 0.0,
            "position_seconds": 0.0,
            "source": "YouTube",
            "playlist": [],
            "last_played": None,
        }

        playlist_snapshot = {
            "has_active_session": False,
            "playlist_id": None,
            "name": None,
            "entries": [],
            "current_index": -1,
            "is_shuffle": False,
            "state": "IDLE",
            "revision": 0,
        }

        if self._music_player is not None and hasattr(self._music_player, "get_state_snapshot"):
            try:
                raw_snap = self._music_player.get_state_snapshot()
                if isinstance(raw_snap, dict):
                    music_snapshot.update(raw_snap)
            except Exception:
                pass

        if self._music_player is not None and hasattr(self._music_player, "get_playlist_snapshot"):
            try:
                pl_snap = self._music_player.get_playlist_snapshot()
                if isinstance(pl_snap, dict):
                    playlist_snapshot.update(pl_snap)
            except Exception:
                pass

        mic_is_active = True
        assistant = getattr(self, "_assistant", None)
        if assistant and getattr(assistant, "listener", None):
            mic_is_active = getattr(assistant.listener, "is_mic_active", True)

        # Collect AI Core telemetry
        ai_core_snap = None
        gw = self._gateway_client
        if gw is None and self._assistant is not None:
            gw = getattr(self._assistant, "gateway_client", None)

        sm = self._session_memory
        if sm is None and self._assistant is not None:
            sm = getattr(self._assistant, "session_memory", None)

        if gw is not None and hasattr(gw, "get_telemetry_snapshot"):
            try:
                ai_core_snap = gw.get_telemetry_snapshot()
            except Exception:
                pass

        if ai_core_snap is None:
            from config.settings import COE_AI_MODEL
            ai_core_snap = {
                "provider": "CoE AI Gateway",
                "base_url": "",
                "configured_model": COE_AI_MODEL,
                "resolved_model": None,
                "is_configured": False,
                "gateway_status": "STANDBY",
                "runtime_state": "IDLE",
                "in_flight_requests": 0,
                "last_request_status": None,
                "last_error_category": None,
                "last_request_latency_ms": None,
                "last_successful_latency_ms": None,
                "avg_latency_ms": None,
                "recent_latencies_ms": [],
                "success_count": 0,
                "failure_count": 0,
                "last_success_timestamp": None,
                "last_tokens": None,
                "session_tokens": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "context_capacity": None,
                "remaining_tokens": None,
                "utilization_percentage": None,
                "history_included": False,
            }

        # Enrich with session memory state
        if sm is not None:
            turns_count = len(getattr(sm, "turns", []))
            max_turns = getattr(sm, "max_turns", 10)
            ai_core_snap["session_memory_turns"] = turns_count
            ai_core_snap["session_memory_max_turns"] = max_turns
            ai_core_snap["session_memory_available"] = True
            if turns_count == 0:
                ai_core_snap["session_memory_status"] = "EMPTY"
            elif turns_count >= max_turns:
                ai_core_snap["session_memory_status"] = "MAX_CAPACITY"
            else:
                ai_core_snap["session_memory_status"] = "ACTIVE"
        else:
            ai_core_snap["session_memory_turns"] = 0
            ai_core_snap["session_memory_max_turns"] = 10
            ai_core_snap["session_memory_available"] = False
            ai_core_snap["session_memory_status"] = "UNAVAILABLE"

        uptime_seconds = 0
        actions_count = 0
        if self._assistant is not None:
            start_t = getattr(self._assistant, "start_time", None)
            if start_t:
                uptime_seconds = int(time.time() - start_t)
            history = getattr(self._assistant, "_task_history", None)
            if history is not None:
                actions_count = len(history)

        ai_core_snap["uptime_seconds"] = uptime_seconds
        ai_core_snap["actions_executed_count"] = actions_count

        return {
            "system_metrics": sys_metrics,
            "process_watcher": proc_watcher,
            "music": music_snapshot,
            "playlist": playlist_snapshot,
            "microphone": {"is_active": mic_is_active},
            "ai_core": ai_core_snap,
        }

