"""
Light AI V1.0 - Core Configuration Settings
"""

import math
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from utils.logger import logger

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
CONTACTS_FILE = CONFIG_DIR / "contacts.json"
ALLOWLIST_FILE = CONFIG_DIR / "app_allowlist.json"
CHATS_DIR = BASE_DIR / "chats"

# Session Memory & Chat Persistence (Phase D5.0)
SESSION_MEMORY_MAX_TURNS = 10

# Load local environment file if present (excluded from Git)
load_dotenv(BASE_DIR / ".env")

# Assistant Identity & Prefix
ASSISTANT_NAME = "Light"
WAKE_PREFIX = "light"
FIXED_IDENTITY_RESPONSE = "Main Light AI hoon, jise mere Boss ne banaya hai."

# Approved Exact Standalone Exit Commands
APPROVED_EXIT_COMMANDS = (
    "exit",
    "stop",
    "stop listening",
    "terminate",
    "good bye",
    "goodbye",
    "bye",
    "shut down",
    "shutdown",
    "band ho jao",
    "bas karo",
    "ab band ho jao",
)

# Browser Configuration
PREFERRED_BROWSER = "brave"  # Preferred browser for generic web tasks (Brave, Chrome, Edge)

# Speech Recognition Configuration
STT_LANGUAGE = "en-IN"
MIC_LISTEN_TIMEOUT = 5.0        # Bounded seconds to wait for speech to start
MIC_PHRASE_TIME_LIMIT = None    # None: Captures complete utterance without premature truncation
MIC_PAUSE_THRESHOLD = 1.0       # Approximately 1 second of continuous silence to finalize utterance
MIC_NON_SPEAKING_DURATION = 0.5 # Silence duration to retain before/after speech
MIC_MIN_ENERGY_THRESHOLD = 300.0# Safeguard floor to avoid hyper-sensitivity in quiet environments
STT_REQUEST_TIMEOUT = 5.0       # Socket timeout for Google STT API call

# Text-to-Speech (TTS) Configuration
PRIMARY_TTS_VOICE = "hi-IN-SwaraNeural"
FALLBACK_TTS_VOICE = "Microsoft Kalpana"
FALLBACK_SAPI_NAME = "kalpana"
TTS_RATE = "+10%"
TTS_PITCH = "+2Hz"
ACOUSTIC_GUARD_DELAY = 0.400    # 400 ms settling guard after audio playback

# Command & Feedback Guards
COMMAND_DEBOUNCE_SECONDS = 2.0  # Suppress identical commands received within 2s
WHATSAPP_CONFIRM_TIMEOUT = 10.0 # Total timeout window for WhatsApp confirmation dialog

# CoE AI Gateway Configuration (OpenAI-compatible)
def parse_timeout(env_val: Optional[str], default: float = 10.0) -> float:
    """
    Parses and validates timeout configuration.
    Accepts: Finite positive numbers > 0.0.
    Rejects: None, empty/whitespace strings, non-numeric strings, NaN, +/-Infinity, <= 0.0.
    Never exposes raw secrets or malformed tokens in logs.
    """
    if env_val is None:
        return default

    cleaned = str(env_val).strip()
    if not cleaned:
        return default

    try:
        val = float(cleaned)
        if math.isfinite(val) and val > 0.0:
            return val
    except (ValueError, TypeError):
        pass

    logger.warning("Invalid COE_AI_TIMEOUT_SECONDS configured. Defaulting to 10.0 seconds.")
    return default


COE_AI_BASE_URL = os.getenv("COE_AI_BASE_URL", "https://ai.tcetcercd.in/v1").strip()
COE_AI_MODEL = os.getenv("COE_AI_MODEL", "qwen3.6").strip()
COE_AI_KEY = os.getenv("COE_AI_KEY", "").strip()
COE_AI_TIMEOUT_SECONDS = parse_timeout(os.getenv("COE_AI_TIMEOUT_SECONDS"), default=10.0)

def parse_optional_int(val: Optional[str]) -> Optional[int]:
    if not val:
        return None
    try:
        v = int(val.strip())
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None

COE_AI_CONTEXT_CAPACITY: Optional[int] = parse_optional_int(os.getenv("COE_AI_CONTEXT_CAPACITY"))

# Music Playback Configuration (Phase 8 & D4.2)
VLC_DIR = Path(r"C:\Program Files\VideoLAN\VLC")
MUSIC_NORMAL_VOLUME = 80
MUSIC_DUCKED_VOLUME = 20

# D4.2 Configuration Migration: Playlists are authoritative in config/playlist.json.
# DEFAULT_PLAYLISTS is lazily/dynamically resolved from config/playlist.json for backward compatibility.
def get_default_playlists():
    from config.playlist_loader import get_legacy_playlists_dict
    return get_legacy_playlists_dict()

class _PlaylistsProxy(dict):
    """Proxy dictionary that delegates to config/playlist.json to prevent competing sources."""
    def _data(self):
        return get_default_playlists()
    def __getitem__(self, key):
        return self._data()[key]
    def __iter__(self):
        return iter(self._data())
    def __len__(self):
        return len(self._data())
    def __contains__(self, key):
        return key in self._data()
    def get(self, key, default=None):
        return self._data().get(key, default)
    def items(self):
        return self._data().items()
    def keys(self):
        return self._data().keys()
    def values(self):
        return self._data().values()

DEFAULT_PLAYLISTS = _PlaylistsProxy()

