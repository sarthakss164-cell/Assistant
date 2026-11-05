"""
Push-to-Talk (PTT) Controller module for Light AI V1.0 (Phase 8.3).
Provides global Spacebar press-and-hold detection across applications using
Windows GetAsyncKeyState without requiring administrator privileges.
Detects physical down/up state transitions while strictly ignoring auto-repeat.
"""

import ctypes
import sys
import threading
import time
from typing import Optional, Callable, Any
from utils.logger import logger

VK_SPACE = 0x20


def _default_windows_space_check() -> bool:
    """Queries physical Spacebar state globally on Windows."""
    if sys.platform == "win32":
        try:
            # Most significant bit (0x8000) indicates key is physically held down
            return bool(ctypes.windll.user32.GetAsyncKeyState(VK_SPACE) & 0x8000)
        except Exception as e:
            logger.debug(f"[PTT] GetAsyncKeyState call notice: {e}")
            return False
    return False


class PushToTalkController:
    """
    Monitors physical Spacebar state globally in a lightweight background daemon thread.
    Triggers on_press and on_release callbacks strictly on physical state transitions.
    """

    def __init__(
        self,
        key_check_fn: Optional[Callable[[], bool]] = None,
        on_press: Optional[Callable[[], Any]] = None,
        on_release: Optional[Callable[[], Any]] = None,
        poll_interval: float = 0.015,
    ):
        self._key_check = key_check_fn if key_check_fn is not None else _default_windows_space_check
        self.on_press = on_press
        self.on_release = on_release
        self.poll_interval = poll_interval

        self._running = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()

        self._is_pressed = False
        self._press_event = threading.Event()
        self._release_event = threading.Event()
        self._release_event.set()

    @property
    def is_pressed(self) -> bool:
        """Returns True if the Spacebar is currently physically pressed down."""
        with self._lock:
            return self._is_pressed

    @property
    def is_running(self) -> bool:
        """Returns True if the background monitoring thread is active."""
        return self._running.is_set()

    def start(self) -> None:
        """Starts the background keyboard polling loop if not already running."""
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._running.set()
                self._thread = threading.Thread(
                    target=self._monitor_loop,
                    name="LightPttMonitor",
                    daemon=True,
                )
                self._thread.start()
                logger.info("[PTT] Global Push-to-Talk monitor started.")

    def stop(self) -> None:
        """Stops the keyboard polling loop cleanly and resets press state."""
        self._running.clear()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

        with self._lock:
            was_pressed = self._is_pressed
            self._is_pressed = False
            self._press_event.clear()
            self._release_event.set()

        if was_pressed and self.on_release:
            try:
                self.on_release()
            except Exception as e:
                logger.debug(f"[PTT] on_release error during stop: {e}")

        logger.info("[PTT] Global Push-to-Talk monitor stopped.")

    def wait_for_press(self, timeout: Optional[float] = None) -> bool:
        """
        Blocks until Spacebar is physically pressed down or timeout elapses.
        Returns True if pressed, False if timed out.
        Consumes the press event so callers do not re-trigger within the same physical hold.
        """
        pressed = self._press_event.wait(timeout=timeout)
        if pressed:
            self._press_event.clear()
        return pressed

    def wait_for_release(self, timeout: Optional[float] = None) -> bool:
        """
        Blocks until Spacebar is physically released or timeout elapses.
        Returns True if released, False if timed out.
        """
        return self._release_event.wait(timeout=timeout)

    def simulate_press(self) -> None:
        """Test helper to simulate physical Spacebar key-down transition."""
        self._handle_state_transition(raw_down=True)

    def simulate_release(self) -> None:
        """Test helper to simulate physical Spacebar key-up transition."""
        self._handle_state_transition(raw_down=False)

    def _handle_state_transition(self, raw_down: bool) -> None:
        """Thread-safe transition handler that strictly suppresses auto-repeat."""
        with self._lock:
            if raw_down and not self._is_pressed:
                # Transition: UP -> DOWN (new press session)
                self._is_pressed = True
                self._release_event.clear()
                self._press_event.set()
                logger.info("[PTT] Spacebar DOWN detected.")
                if self.on_press:
                    try:
                        self.on_press()
                    except Exception as e:
                        logger.error(f"[PTT] on_press callback error: {e}", exc_info=True)

            elif not raw_down and self._is_pressed:
                # Transition: DOWN -> UP (session finalized)
                self._is_pressed = False
                self._press_event.clear()
                self._release_event.set()
                logger.info("[PTT] Spacebar UP detected.")
                if self.on_release:
                    try:
                        self.on_release()
                    except Exception as e:
                        logger.error(f"[PTT] on_release callback error: {e}", exc_info=True)

    def _monitor_loop(self) -> None:
        """Lightweight polling worker loop."""
        while self._running.is_set():
            try:
                raw_down = bool(self._key_check())
            except Exception as e:
                logger.debug(f"[PTT] Key check error: {e}")
                raw_down = False

            self._handle_state_transition(raw_down)
            time.sleep(self.poll_interval)
