"""
Logger utility for Light AI V1.0
Provides structured terminal logging with automatic redaction of sensitive contact phone numbers.
"""

import logging
import re
import sys

def setup_logger(name: str = "LightAI") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S"
        )
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
    return logger

logger = setup_logger()

def mask_phone_for_log(phone: str) -> str:
    """Masks a phone number, showing only country prefix and last 4 digits."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) >= 6:
        return f"{digits[:2]}******{digits[-4:]}"
    return "******"
