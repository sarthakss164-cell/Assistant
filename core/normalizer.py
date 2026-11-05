"""
Text normalizer module for Light AI V1.0.
Handles lowercase conversion, punctuation removal, whitespace normalization, and wake prefix extraction.
"""

import string
import unicodedata

# Wake word aliases in Latin and Devanagari
WAKE_WORDS = ("light", "लाइट", "lite")

# Specific punctuation characters to strip from speech transcripts
PUNCTUATION_CHARS = set(string.punctuation + "–—।¿¡«»")

def normalize_text(text: str) -> str:
    """Normalizes raw input text: lowercase, remove punctuation, collapse whitespace."""
    if not text or not isinstance(text, str):
        return ""
    # Normalize Unicode composition
    normalized = unicodedata.normalize("NFC", text.lower())
    # Replace punctuation with spaces
    cleaned = "".join(" " if ch in PUNCTUATION_CHARS else ch for ch in normalized)
    # Collapse multiple whitespaces
    return " ".join(cleaned.split()).strip()

def strip_wake_prefix(text: str) -> tuple[bool, str]:
    """
    Checks if text begins with the wake word (e.g. 'light', 'लाइट', 'lite').
    Returns: (has_prefix: bool, remainder: str)
    """
    normalized = normalize_text(text)
    if not normalized:
        return False, ""

    tokens = normalized.split()
    first_token = tokens[0]

    for wake in WAKE_WORDS:
        if first_token == wake:
            remainder = " ".join(tokens[1:])
            return True, remainder

    return False, normalized
