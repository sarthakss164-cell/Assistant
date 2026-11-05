"""
Text-to-Speech (TTS) module for Light AI V1.0.
Features:
- Primary: Microsoft Edge TTS using hi-IN-SwaraNeural.
- Fallback: Local Windows SAPI5 (pyttsx3 / Microsoft Kalpana).
- Playback via pygame.mixer with automatic temp file cleanup.
- Approved 400 ms post-playback acoustic settling guard.
"""

import asyncio
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Optional, Any, Callable

from config.settings import (
    BASE_DIR,
    PRIMARY_TTS_VOICE,
    FALLBACK_SAPI_NAME,
    TTS_RATE,
    TTS_PITCH,
    ACOUSTIC_GUARD_DELAY,
)
from utils.logger import logger


class TTSEngine:
    def __init__(
        self,
        primary_voice: str = PRIMARY_TTS_VOICE,
        rate: str = TTS_RATE,
        pitch: str = TTS_PITCH,
        acoustic_delay: float = ACOUSTIC_GUARD_DELAY,
        speech_gate: Optional[Any] = None,
        on_speaking_start: Optional[Callable[[], Any]] = None,
        on_speaking_finish: Optional[Callable[[], Any]] = None,
        on_speech_completed: Optional[Callable[[str, bool], Any]] = None,
        on_playback_start: Optional[Callable[[str], Any]] = None,
        on_playback_stop: Optional[Callable[[], Any]] = None,
    ):
        self.primary_voice = primary_voice
        self.rate = rate
        self.pitch = pitch
        self.acoustic_delay = acoustic_delay
        self.speech_gate = speech_gate
        self.on_speaking_start = on_speaking_start
        self.on_speaking_finish = on_speaking_finish
        self.on_speech_completed = on_speech_completed
        self.on_playback_start = on_playback_start
        self.on_playback_stop = on_playback_stop
        self._mixer_initialized = False
        self._speak_lock = threading.Lock()
        self._is_speaking = False
        self._playback_active = False

    @property
    def is_speaking(self) -> bool:
        """Indicates whether audio generation or playback is currently in progress."""
        return self._is_speaking

    def _init_mixer(self) -> bool:
        """Initializes pygame mixer safely."""
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            self._mixer_initialized = True
            return True
        except Exception as e:
            logger.error(f"Failed to initialize pygame mixer: {e}")
            return False

    def _prepare_text_for_edge_tts(self, text: str) -> str:
        """
        Applies targeted phonetic normalization for Hindi neural voices (hi-IN-SwaraNeural).
        Replaces Latin-script Hindi words that collide with English vocabulary
        (e.g., 'mere' /mɪər/ -> 'मेरे' /meːreː/) to ensure accurate Hindi pronunciation.
        """
        return re.sub(r"\bmere\b", "मेरे", text, flags=re.IGNORECASE)

    async def _generate_edge_tts(self, text: str, output_path: str) -> None:
        """Generates MP3 audio file using edge-tts with phonetic preparation."""
        import edge_tts
        tts_text = self._prepare_text_for_edge_tts(text)
        communicate = edge_tts.Communicate(
            text=tts_text,
            voice=self.primary_voice,
            rate=self.rate,
            pitch=self.pitch,
        )
        await communicate.save(output_path)

    def _play_audio_file(self, file_path: str) -> None:
        """Plays an audio file via pygame.mixer and waits for completion."""
        import pygame
        if not self._init_mixer():
            raise RuntimeError("Audio mixer unavailable.")

        pygame.mixer.music.load(file_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.04)

        pygame.mixer.music.stop()
        try:
            pygame.mixer.music.unload()
        except AttributeError:
            pass

    def _fallback_speak_sapi5(self, text: str) -> None:
        """Fallback to local Windows SAPI5 via pyttsx3."""
        # For English SAPI5 voices, replace 'mere' with 'mehre' so it sounds like 'meh-ray'
        spoken_text = re.sub(r"\bmere\b", "mehre", text, flags=re.IGNORECASE)
        logger.info(f"Using local SAPI5 fallback for speech output: '{spoken_text}'")
        try:
            import pyttsx3
            engine = pyttsx3.init()
            try:
                voices = engine.getProperty("voices")
                for voice in voices:
                    if FALLBACK_SAPI_NAME in voice.name.lower() or "hindi" in voice.name.lower():
                        engine.setProperty("voice", voice.id)
                        break
            except Exception as e:
                logger.debug(f"Could not configure specific SAPI5 voice: {e}")

            if not self._playback_active and self.on_playback_start:
                try:
                    self._playback_active = True
                    self.on_playback_start(spoken_text)
                except Exception as cb_err:
                    logger.debug(f"[TTS] on_playback_start notice: {cb_err}")

            engine.say(spoken_text)
            engine.runAndWait()
        except Exception as e:
            logger.error(f"SAPI5 fallback also failed: {e}")
            raise

    def speak(self, text: str) -> bool:
        """
        Speaks the given text using primary Edge TTS, falling back to local SAPI5 if needed.
        Applies acoustic settling delay after speech completes.
        Thread-safe: serializes multiple concurrent callers via _speak_lock.
        Returns:
            bool: True if speech was produced, False otherwise.
        """
        clean_text = text.strip()
        if not clean_text:
            return False

        with self._speak_lock:
            self._is_speaking = True
            if self.speech_gate:
                self.speech_gate.start_playback()
            if self.on_speaking_start:
                try:
                    self.on_speaking_start()
                except Exception as cb_err:
                    logger.debug(f"[TTS] on_speaking_start callback notice: {cb_err}")
            try:
                logger.info(f"[SPEAKING] {clean_text}")
                temp_audio_file = str(BASE_DIR / f"light_audio_{uuid.uuid4().hex[:8]}.mp3")
                speech_successful = False

                # Attempt Primary: Edge TTS
                try:
                    asyncio.run(self._generate_edge_tts(clean_text, temp_audio_file))
                    if os.path.exists(temp_audio_file) and os.path.getsize(temp_audio_file) > 0:
                        if not self._playback_active and self.on_playback_start:
                            try:
                                self._playback_active = True
                                self.on_playback_start(clean_text)
                            except Exception as cb_err:
                                logger.debug(f"[TTS] on_playback_start callback notice: {cb_err}")
                        self._play_audio_file(temp_audio_file)
                        speech_successful = True
                except Exception as edge_err:
                    logger.warning(f"Edge TTS failed ({edge_err}). Attempting SAPI5 fallback.")
                    try:
                        self._fallback_speak_sapi5(clean_text)
                        speech_successful = True
                    except Exception as sapi_err:
                        logger.error(f"All TTS providers failed: {sapi_err}")
                        speech_successful = False
                finally:
                    # Clean up temp file immediately
                    if os.path.exists(temp_audio_file):
                        try:
                            os.remove(temp_audio_file)
                        except Exception as del_err:
                            logger.debug(f"Failed to remove temp audio file '{temp_audio_file}': {del_err}")

                    # Apply the approved acoustic settling delay (400 ms) to reduce self-recognition
                    time.sleep(self.acoustic_delay)

                if speech_successful and self.on_speech_completed:
                    try:
                        self.on_speech_completed(clean_text, True)
                    except Exception as cb_err:
                        logger.debug(f"[TTS] on_speech_completed callback notice: {cb_err}")

                return speech_successful
            finally:
                try:
                    if self.on_playback_stop:
                        try:
                            self.on_playback_stop()
                        except Exception as cb_err:
                            logger.debug(f"[TTS] on_playback_stop callback notice: {cb_err}")
                    self._playback_active = False

                    if self.on_speaking_finish:
                        try:
                            self.on_speaking_finish()
                        except Exception as cb_err:
                            logger.debug(f"[TTS] on_speaking_finish callback notice: {cb_err}")
                    if self.speech_gate:
                        self.speech_gate.stop_playback()
                finally:
                    self._is_speaking = False
