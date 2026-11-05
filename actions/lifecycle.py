"""
Application lifecycle and shutdown action for Light AI V1.0.
Provides graceful shutdown with independently guarded cleanup operations:
1. Stops listening.
2. Cancels pending operations.
3. Attempts farewell speech (TTS failure never blocks shutdown).
4. Independently shuts down mixer, microphone, and temporary audio files.
5. Logs termination status and exits.
"""

import glob
import os
import sys
import time
from typing import Optional, Any
from pathlib import Path

from config.settings import BASE_DIR
from utils.logger import logger


def purge_temp_audio_files(directory: Path = BASE_DIR) -> int:
    """
    Safely finds and deletes any temporary MP3 audio files generated during TTS playback.
    Returns the count of purged files.
    """
    purged_count = 0
    patterns = [
        str(directory / "light_audio_*.mp3"),
        str(directory / "*.tmp.mp3"),
    ]
    for pattern in patterns:
        for file_path in glob.glob(pattern):
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    purged_count += 1
            except Exception as e:
                logger.debug(f"Could not remove temp audio file '{file_path}': {e}")
    return purged_count


def shutdown_audio_mixer() -> None:
    """Independently guards pygame mixer shutdown."""
    try:
        import pygame
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
            try:
                pygame.mixer.music.unload()
            except AttributeError:
                pass
            pygame.mixer.quit()
            logger.info("Audio mixer cleanly shutdown.")
    except Exception as e:
        logger.error(f"Error during audio mixer shutdown: {e}")


def shutdown_listener(listener: Optional[Any] = None) -> None:
    """Independently guards microphone / listener resource cleanup."""
    if listener is None:
        return
    try:
        if hasattr(listener, "close"):
            listener.close()
        elif hasattr(listener, "stop"):
            listener.stop()
        logger.info("Microphone listener cleanly closed.")
    except Exception as e:
        logger.error(f"Error closing microphone listener: {e}")


def graceful_shutdown(
    tts_engine: Optional[Any] = None,
    listener: Optional[Any] = None,
    farewell_message: str = "Alvida! Light AI ab band ho rahi hai.",
    exit_process: bool = True
) -> None:
    """
    Executes the approved graceful shutdown sequence.
    Guarantees termination even if TTS or individual cleanup steps fail.
    """
    logger.info("Initiating LIGHT AI graceful shutdown sequence...")

    # Step 1: Attempt farewell speech before tearing down audio
    if tts_engine and farewell_message:
        try:
            tts_engine.speak(farewell_message)
        except Exception as e:
            logger.warning(f"Farewell TTS playback failed (continuing shutdown): {e}")

    # Ensure any active speech playback completes before audio mixer teardown
    if tts_engine and hasattr(tts_engine, "is_speaking"):
        wait_cycles = 0
        while getattr(tts_engine, "is_speaking", False) and wait_cycles < 50:
            time.sleep(0.1)
            wait_cycles += 1

    # Step 2: Independently guard each cleanup operation
    try:
        shutdown_audio_mixer()
    except Exception as e:
        logger.error(f"Unexpected error in mixer shutdown wrapper: {e}")

    try:
        shutdown_listener(listener)
    except Exception as e:
        logger.error(f"Unexpected error in listener shutdown wrapper: {e}")

    try:
        purged = purge_temp_audio_files()
        if purged > 0:
            logger.info(f"Purged {purged} temporary audio file(s).")
    except Exception as e:
        logger.error(f"Unexpected error in temp file purge: {e}")

    logger.info("LIGHT AI V1.0 shutdown complete.")

    # Step 3: Terminate process
    if exit_process:
        sys.exit(0)
