"""
Speech-to-Text (STT) module for Light AI V1.0.
Uses Google Speech Recognition exclusively as approved in Revision 6.
Handles unintelligible speech and network connectivity failures gracefully.
"""

from typing import Tuple, Optional
import speech_recognition as sr
from config.settings import STT_LANGUAGE, STT_REQUEST_TIMEOUT
from utils.logger import logger


class GoogleSpeechRecognizer:
    def __init__(
        self,
        language: str = STT_LANGUAGE,
        request_timeout: float = STT_REQUEST_TIMEOUT,
    ):
        self.language = language
        self.request_timeout = request_timeout
        self.recognizer = sr.Recognizer()

    def transcribe(self, audio_data: Optional[sr.AudioData]) -> Tuple[bool, Optional[str]]:
        """
        Transcribes captured audio data using Google Speech Recognition.
        Returns:
            (success: bool, text_or_error_type: Optional[str])
            - (True, "recognized text"): Speech recognized.
            - (True, ""): Speech was unintelligible / noise (sr.UnknownValueError).
            - (False, "network_error"): Internet or Google API unreachable (sr.RequestError).
            - (False, "audio_empty"): Audio data was None.
        """
        if audio_data is None:
            return (False, "audio_empty")

        try:
            # recognize_google connects to Google Speech Recognition web service
            text = self.recognizer.recognize_google(
                audio_data,
                language=self.language,
                # Note: speech_recognition does not support timeout parameter on recognize_google directly,
                # socket default timeout governs it.
            )
            logger.info(f"[HEARD] {text}")
            return (True, text)
        except sr.UnknownValueError:
            # Normal: audio could not be matched to intelligible words
            logger.debug("Speech unintelligible (UnknownValueError).")
            return (True, "")
        except sr.RequestError as e:
            logger.warning(f"Google Speech Recognition network/API failure: {e}")
            return (False, "network_error")
        except Exception as e:
            logger.error(f"Unexpected error during speech recognition: {e}")
            return (False, "error")
