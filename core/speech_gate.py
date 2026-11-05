"""
Thread-safe Speech Output Gate for Light AI V1.0.
Coordinates TTS speech output and microphone capture to prevent acoustic self-feedback.
Ensures microphone does not record or route the assistant's own spoken output.

Half-duplex design:
While LIGHT AI is speaking (or speech is pending/settling), the microphone ignores
or discards audio. If a user speaks simultaneously while the assistant is speaking,
that speech is intentionally ignored to guarantee stability and prevent feedback loops.
"""

import threading
import time
from contextlib import contextmanager
from typing import Generator, Optional
from utils.logger import logger


class SpeechOutputGate:
    """
    Thread-safe gate representing whether assistant speech output is currently
    playing, pending playback, or settling acoustically.
    """

    def __init__(self, settling_delay: float = 0.0):
        self._lock = threading.RLock()
        self._playback_count: int = 0
        self._pending_count: int = 0
        self._idle_event = threading.Event()
        self._idle_event.set()  # Initially idle
        self._last_playback_stop_time: float = 0.0
        self.settling_delay = settling_delay

    @property
    def is_active(self) -> bool:
        """Returns True if speech is actively playing or queued/pending."""
        with self._lock:
            return (self._playback_count > 0) or (self._pending_count > 0)

    @property
    def is_playing(self) -> bool:
        """Returns True if audio playback is actively in progress."""
        with self._lock:
            return self._playback_count > 0

    @property
    def pending_count(self) -> int:
        """Returns count of queued/pending speech tasks."""
        with self._lock:
            return self._pending_count

    @property
    def last_playback_stop_time(self) -> float:
        """Timestamp when playback last completed."""
        with self._lock:
            return self._last_playback_stop_time

    def mark_speech_queued(self) -> None:
        """Indicates a speech task has been submitted/queued for playback."""
        with self._lock:
            self._pending_count += 1
            self._idle_event.clear()
            logger.debug(f"[SPEECH_GATE] Speech queued (pending={self._pending_count})")

    def mark_speech_completed(self) -> None:
        """Indicates a queued speech task has completed or aborted."""
        with self._lock:
            if self._pending_count > 0:
                self._pending_count -= 1
            logger.debug(
                f"[SPEECH_GATE] Speech task finished (pending={self._pending_count}, playing={self._playback_count})"
            )
            if self._playback_count == 0 and self._pending_count == 0:
                self._last_playback_stop_time = time.time()
                self._idle_event.set()

    def start_playback(self) -> None:
        """Activates gate for actual audio playback."""
        with self._lock:
            self._playback_count += 1
            self._idle_event.clear()
            logger.debug(f"[SPEECH_GATE] Playback started (playing={self._playback_count})")

    def stop_playback(self) -> None:
        """Deactivates gate after audio playback and acoustic settling finish."""
        with self._lock:
            if self._playback_count > 0:
                self._playback_count -= 1
            self._last_playback_stop_time = time.time()
            logger.debug(
                f"[SPEECH_GATE] Playback stopped (playing={self._playback_count}, pending={self._pending_count})"
            )
            if self._playback_count == 0 and self._pending_count == 0:
                self._idle_event.set()

    @contextmanager
    def playback_context(self) -> Generator[None, None, None]:
        """Context manager for scoping playback operations with guaranteed cleanup."""
        self.start_playback()
        try:
            yield
        finally:
            self.stop_playback()

    def wait_for_idle(self, timeout: Optional[float] = 15.0) -> bool:
        """
        Blocks until speech playback and all pending speech tasks have concluded.
        Returns:
            True if idle, False if timed out.
        """
        if not self.is_active:
            return True
        return self._idle_event.wait(timeout=timeout)

    def was_active_since(self, timestamp: float) -> bool:
        """
        Checks whether speech output was active at or after the given timestamp.
        Used to detect if microphone capture overlapped with TTS playback.
        """
        with self._lock:
            if self._playback_count > 0 or self._pending_count > 0:
                return True
            return (self._last_playback_stop_time + self.settling_delay) > timestamp

    def reset(self) -> None:
        """Forcibly resets gate to idle state (e.g. during shutdown or error recovery)."""
        with self._lock:
            self._playback_count = 0
            self._pending_count = 0
            self._last_playback_stop_time = time.time()
            self._idle_event.set()
            logger.debug("[SPEECH_GATE] Gate forcibly reset to idle.")
