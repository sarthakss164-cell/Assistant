"""
Microphone listener module for Light AI V1.0.
Captures continuous speech streams until silence threshold is satisfied using speech_recognition.
Avoids premature truncation of long commands and implements adaptive ambient noise filtering.
"""

import time
import threading
from typing import Optional, Any, Callable
import speech_recognition as sr
from config.settings import (
    MIC_LISTEN_TIMEOUT,
    MIC_PHRASE_TIME_LIMIT,
    MIC_PAUSE_THRESHOLD,
    MIC_NON_SPEAKING_DURATION,
    MIC_MIN_ENERGY_THRESHOLD,
)
from utils.logger import logger


class SpeechListener:
    def __init__(
        self,
        listen_timeout: float = MIC_LISTEN_TIMEOUT,
        phrase_time_limit: Optional[float] = MIC_PHRASE_TIME_LIMIT,
        pause_threshold: float = MIC_PAUSE_THRESHOLD,
        non_speaking_duration: float = MIC_NON_SPEAKING_DURATION,
        speech_gate: Optional[Any] = None,
        on_capture_start: Optional[Callable[[], Any]] = None,
        on_capture_end: Optional[Callable[[bool], Any]] = None,
    ):
        self.listen_timeout = listen_timeout
        self.phrase_time_limit = phrase_time_limit
        self.speech_gate = speech_gate
        self.on_capture_start = on_capture_start
        self.on_capture_end = on_capture_end
        self.recognizer = sr.Recognizer()

        # Silence detection: wait approximately 1 second of continuous silence after speech
        self.recognizer.pause_threshold = pause_threshold
        self.recognizer.non_speaking_duration = non_speaking_duration

        # Dynamic ambient noise adaptation
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.dynamic_energy_adjustment_damping = 0.15
        self.recognizer.dynamic_energy_ratio = 1.5

        self.microphone = None
        self._is_calibrated = False
        self._mic_active = threading.Event()
        self._mic_active.set()

    @property
    def is_mic_active(self) -> bool:
        """Returns True if microphone capture is enabled, False if MUTED."""
        return self._mic_active.is_set()

    def set_mic_active(self, active: bool) -> bool:
        """
        Authoritatively enables or disables microphone capture.
        Thread-safe and synchronous.
        """
        if active:
            self._mic_active.set()
            logger.info("[LISTENER] Microphone capture ENABLED (ACTIVE).")
        else:
            self._mic_active.clear()
            logger.info("[LISTENER] Microphone capture DISABLED (MUTED).")
        return self._mic_active.is_set()

    def init_microphone(self) -> bool:
        """Initializes the default microphone and performs ambient noise calibration."""
        try:
            self.microphone = sr.Microphone()
            with self.microphone as source:
                logger.info("Calibrating microphone for ambient noise (1 second)...")
                self.recognizer.adjust_for_ambient_noise(source, duration=1.0)
                # Safeguard against hyper-sensitivity in quiet environments
                if self.recognizer.energy_threshold < MIC_MIN_ENERGY_THRESHOLD:
                    self.recognizer.energy_threshold = MIC_MIN_ENERGY_THRESHOLD
                logger.info(f"Microphone calibrated. Energy threshold: {self.recognizer.energy_threshold:.1f}")
            self._is_calibrated = True
            return True
        except Exception as e:
            logger.error(f"Failed to initialize or calibrate microphone: {e}")
            return False

    def listen(self) -> Optional[sr.AudioData]:
        """
        Listens for a speech phrase continuously until the silence threshold is satisfied.
        Does not truncate long commands if user continues speaking.
        Returns:
            sr.AudioData if speech was captured, or None if timed out / error occurred / muted.
        """
        if not self._mic_active.is_set():
            # Muted: pause briefly so caller loop does not spin, then return None
            self._mic_active.wait(timeout=0.2)
            return None

        if self.microphone is None:
            if not self.init_microphone():
                return None

        # 1. Gate check: If assistant speech output is active or pending, wait for it to be idle
        if self.speech_gate and self.speech_gate.is_active:
            logger.debug("[LISTENER] Speech output gate is active. Waiting for playback to finish...")
            if not self.speech_gate.wait_for_idle(timeout=15.0):
                logger.warning("[LISTENER] Timed out waiting for speech output gate to become idle.")
                return None

        capture_start_time = time.time()
        has_captured_audio = False
        try:
            with self.microphone as source:
                if self.on_capture_start:
                    try:
                        self.on_capture_start()
                    except Exception as cb_err:
                        logger.debug(f"[LISTENER] on_capture_start error: {cb_err}")

                logger.debug("Listening for speech...")
                audio = self.recognizer.listen(
                    source,
                    timeout=self.listen_timeout,
                    phrase_time_limit=self.phrase_time_limit,
                )

                # 2. Gate check: Discard audio if speech output was active during capture
                if self.speech_gate and (
                    self.speech_gate.is_active
                    or self.speech_gate.was_active_since(capture_start_time)
                ):
                    logger.info("[LISTENER] Discarded audio captured during or overlapping with TTS playback.")
                    return None

                has_captured_audio = True
                return audio
        except sr.WaitTimeoutError:
            # Normal: user did not start speaking within listen_timeout
            logger.debug("Speech capture timed out (no speech detected).")
            return None
        except Exception as e:
            logger.warning(f"Microphone capture error: {e}")
            return None
        finally:
            if self.on_capture_end:
                try:
                    self.on_capture_end(has_captured_audio)
                except Exception as cb_err:
                    logger.debug(f"[LISTENER] on_capture_end error: {cb_err}")

    def capture_ptt(
        self,
        is_held_fn: Any,
        max_duration: float = 20.0,
        min_duration: float = 0.3,
    ) -> Optional[sr.AudioData]:
        """
        Captures PCM audio frames from the single master microphone stream
        strictly while is_held_fn() returns True.
        Terminates immediately when is_held_fn() returns False (key-up) or max_duration is reached.
        Returns sr.AudioData on valid capture, or None if too short / empty / error / muted.
        """
        if not self._mic_active.is_set():
            logger.debug("[PTT] Capture prevented: Microphone is MUTED.")
            return None

        if self.microphone is None:
            if not self.init_microphone():
                return None

        # 1. Gate check: If assistant speech output is active or pending, wait for it to be idle
        if self.speech_gate and self.speech_gate.is_active:
            logger.debug("[LISTENER_PTT] Speech gate is active. Waiting for idle...")
            if not self.speech_gate.wait_for_idle(timeout=5.0):
                return None

        frames: list[bytes] = []
        capture_start_time = time.time()
        has_audio = False

        try:
            with self.microphone as source:
                if self.on_capture_start:
                    try:
                        self.on_capture_start()
                    except Exception as cb_err:
                        logger.debug(f"[PTT] on_capture_start error: {cb_err}")

                chunk_size = getattr(source, "CHUNK", 1024)
                sample_rate = getattr(source, "SAMPLE_RATE", 16000)
                sample_width = getattr(source, "SAMPLE_WIDTH", 2)

                logger.info("[PTT] Spacebar microphone capture started.")
                while (time.time() - capture_start_time) < max_duration:
                    if not is_held_fn():
                        break
                    try:
                        data = source.stream.read(chunk_size)
                        if data:
                            frames.append(data)
                    except TypeError:
                        # Fallback for streams requiring exception_on_overflow parameter
                        try:
                            data = source.stream.read(chunk_size, exception_on_overflow=False)
                            if data:
                                frames.append(data)
                        except Exception as e:
                            logger.warning(f"[PTT] Stream read fallback error: {e}")
                            break
                    except Exception as read_err:
                        logger.warning(f"[PTT] Stream read error: {read_err}")
                        break

            duration = time.time() - capture_start_time
            if duration < min_duration or not frames:
                logger.info(f"[PTT] Capture too short ({duration:.2f}s) or empty. Discarded without action.")
                return None

            raw_bytes = b"".join(frames)
            has_audio = True
            logger.info(f"[PTT] Microphone capture ended. Captured {len(raw_bytes)} audio bytes over {duration:.2f}s.")
            return sr.AudioData(raw_bytes, sample_rate, sample_width)

        except Exception as e:
            logger.warning(f"[PTT] Microphone capture failed: {e}")
            return None
        finally:
            if self.on_capture_end:
                try:
                    self.on_capture_end(has_audio)
                except Exception as cb_err:
                    logger.debug(f"[PTT] on_capture_end error: {cb_err}")

    def close(self) -> None:
        """Releases microphone resources."""
        self.microphone = None
        if self.speech_gate:
            self.speech_gate.reset()
        logger.info("SpeechListener resources released.")
