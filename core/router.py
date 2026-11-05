"""
Command router module for Light AI V1.0.
Maps normalized speech into deterministic intents, enforces the strict 4-command exit set,
and manages state-specific routing rules.
"""

from enum import Enum, auto
from typing import List, Dict, Any, Optional
import re
from core.normalizer import normalize_text, strip_wake_prefix
from core.state_machine import SessionState
from config.settings import APPROVED_EXIT_COMMANDS, DEFAULT_PLAYLISTS
from core.intent_validator import IntentValidator, ValidationResult
from core.coe_gateway import CoeGatewayClient, GatewayResponse, GatewayStatus
from utils.logger import logger

class IntentType(Enum):
    IGNORED = auto()
    EXIT = auto()
    IDENTITY = auto()
    OPEN_APP = auto()
    OPEN_WEBSITE = auto()
    SEARCH_GOOGLE = auto()
    SEARCH_YOUTUBE = auto()
    WHATSAPP_START = auto()
    CLARIFICATION = auto()
    CONFIRM_YES = auto()
    CONFIRM_NO = auto()
    CONTACT_SELECT = auto()
    CONVERSATION = auto()
    PLAY_SONG = auto()
    PLAY_PLAYLIST = auto()
    STOP_MUSIC = auto()
    PAUSE_MUSIC = auto()
    RESUME_MUSIC = auto()
    NEXT_SONG = auto()
    PREVIOUS_SONG = auto()
    SHUFFLE_PLAYLIST = auto()
    STOP_PLAYLIST = auto()
    UNKNOWN = auto()

class CommandIntent:
    def __init__(
        self,
        intent_type: IntentType,
        payload: Optional[Dict[str, Any]] = None,
        raw_text: str = "",
        should_activate_session: bool = False
    ):
        self.intent_type = intent_type
        self.payload = payload or {}
        self.raw_text = raw_text
        self.should_activate_session = should_activate_session

    def __repr__(self):
        return f"<CommandIntent type={self.intent_type.name} payload={self.payload} activate={self.should_activate_session}>"

# Deterministic Exit / Shutdown Regex:
# Matches approved standalone exit commands with optional leading or trailing wake word.
# Does NOT match phrases where exit words appear as part of a larger utterance (e.g. "How do I stop procrastinating?").
EXIT_COMMAND_REGEX = re.compile(
    r"^\s*(?:light\s*,?\s*)?"
    r"(?:exit|stop(?:\s+listening)?|terminate|good\s*bye|bye(?:\s+bye)?|shut\s*down|shutdown|band\s+ho\s+jao|bas\s+karo|ab\s+band\s+ho\s+jao)"
    r"(?:\s*,?\s*light)?"
    r"[.!?]?\s*$",
    re.IGNORECASE
)
STANDALONE_EXIT_REGEX = EXIT_COMMAND_REGEX

# Confirmation Regexes
AFFIRMATIVE_REGEX = re.compile(
    r"^\s*(?:haan|han|haa|ha|yes|yeah|yep|bhejo|send|send\s+karo|haan\s+bhejo|han\s+bhejo|haa\s+bhejo|ha\s+bhejo|haan\s+send(?:\s+karo)?|yes\s+send)[.!?]?\s*$",
    re.IGNORECASE
)
NEGATIVE_REGEX = re.compile(
    r"^\s*(?:nahi|nahin|na|no|nope|cancel|cancel\s+karo|ruko|mat\s+bhejo|nahi\s+bhejo|nahin\s+bhejo|nahi\s+cancel(?:\s+karo)?|nahin\s+cancel(?:\s+karo)?|no\s+cancel)[.!?]?\s*$",
    re.IGNORECASE
)

# Contact Disambiguation Ordinals Map
ORDINAL_MAP: Dict[str, int] = {
    "pehla": 0, "first": 0, "1": 0, "one": 0, "ek": 0, "1st": 0,
    "doosra": 1, "second": 1, "2": 1, "two": 1, "do": 1, "2nd": 1,
    "teesra": 2, "third": 2, "3": 2, "three": 2, "teen": 2, "3rd": 2,
    "chautha": 3, "fourth": 3, "4": 3, "four": 3, "char": 3, "4th": 3,
}

# Identity Query Regex:
# Supports canonical query, approved phonetic variations (hu r u, who r u, etc.), and Hindi equivalents
IDENTITY_REGEX = re.compile(
    r"^(?:"
    r"who\s+are\s+you|"
    r"who\s+r\s+you|"
    r"who\s+are\s+u|"
    r"who\s+r\s+u|"
    r"hu\s+r\s+u|"
    r"who\s+made\s+you|"
    r"introduce\s+yourself|"
    r"tell\s+me\s+about\s+yourself|"
    r"tum\s+kaun\s+ho|"
    r"aap\s+kaun\s+hai"
    r")$",
    re.IGNORECASE
)

# Deterministic Music Regexes & Ambiguity Sets
STOP_MUSIC_REGEX = re.compile(
    r"^(?:"
    r"(?:stop|band\s+karo|roko)\s+(?:the\s+)?(?:music|playback|song|songs|gaana|gaane)|"
    r"(?:music|playback|song|songs|gaana|gaane)\s+(?:ko\s+)?(?:stop|band\s+karo|roko)(?:\s+karo)?|"
    r"stop\s+playing|"
    r"music\s+stop|"
    r"gaana\s+band|"
    r"gaane\s+band"
    r")$",
    re.IGNORECASE
)

STOP_PLAYLIST_REGEX = re.compile(
    r"^(?:"
    r"(?:stop|band\s+karo|roko)\s+(?:the\s+)?playlist|"
    r"playlist\s+(?:ko\s+)?(?:stop|band\s+karo|roko)(?:\s+karo)?|"
    r"stop\s+playlist|"
    r"playlist\s+stop|"
    r"playlist\s+band"
    r")$",
    re.IGNORECASE
)

SHUFFLE_PLAYLIST_REGEX = re.compile(
    r"^(?:"
    r"(?:shuffle|mix)\s+(?:the\s+)?playlist|"
    r"playlist\s+(?:ko\s+)?(?:shuffle|mix)(?:\s+karo)?|"
    r"shuffle\s+on|"
    r"shuffle\s+off|"
    r"toggle\s+shuffle|"
    r"shuffle\s+playlist|"
    r"playlist\s+shuffle"
    r")$",
    re.IGNORECASE
)

NEXT_SONG_REGEX = re.compile(
    r"^(?:"
    r"(?:next|skip|agla|agle)\s+(?:the\s+)?(?:song|track|gaana|gaane)(?:\s+karo|\s+bajao|\s+chalao|\s+play\s+karo)?|"
    r"(?:song|track|gaana)\s+(?:change\s+karo|badlo|skip\s+karo|next\s+karo)|"
    r"next\s+song|"
    r"agla\s+gaana(?:\s+bajao|\s+chalao|\s+karo)?|"
    r"next|"
    r"skip"
    r")$",
    re.IGNORECASE
)

PREVIOUS_SONG_REGEX = re.compile(
    r"^(?:"
    r"(?:previous|prev|pichla|pichhla|pichhle)\s+(?:the\s+)?(?:song|track|gaana|gaane)(?:\s+karo|\s+bajao|\s+chalao|\s+play\s+karo)?|"
    r"(?:song|track|gaana)\s+(?:previous|prev|pichla|pichhla)|"
    r"previous\s+song|"
    r"prev\s+song|"
    r"pichla\s+gaana(?:\s+bajao|\s+chalao|\s+karo)?|"
    r"pichhla\s+gaana(?:\s+bajao|\s+chalao|\s+karo)?|"
    r"previous|"
    r"prev"
    r")$",
    re.IGNORECASE
)

PAUSE_MUSIC_REGEX = re.compile(
    r"^(?:"
    r"(?:pause|ruko)\s+(?:the\s+)?(?:music|playback|song|track|gaana)|"
    r"(?:music|playback|song|track|gaana)\s+(?:ko\s+)?(?:pause|ruko)(?:\s+karo)?|"
    r"pause\s+music|"
    r"pause|"
    r"gaana\s+pause"
    r")$",
    re.IGNORECASE
)

RESUME_MUSIC_REGEX = re.compile(
    r"^(?:"
    r"(?:resume|unpause)\s+(?:the\s+)?(?:music|playback|song|track|gaana)|"
    r"(?:music|playback|song|track)\s+(?:ko\s+)?(?:resume|unpause)(?:\s+karo)?|"
    r"gaana\s+(?:ko\s+)?(?:resume|unpause)(?:\s+karo)?|"
    r"resume\s+music|"
    r"resume|"
    r"unpause|"
    r"continue\s+playing|"
    r"continue|"
    r"play\s+again|"
    r"gaana\s+resume"
    r")$",
    re.IGNORECASE
)

AMBIGUOUS_SONG_TOKENS = {
    "",
    "something",
    "anything",
    "any",
    "any song",
    "random",
    "kuch",
    "kuchh",
    "kuch bhi",
    "koi",
    "koi bhi",
    "koi gaana",
    "koi bhi gaana",
    "song",
    "songs",
    "gaana",
    "gaane",
    "music",
    "track",
    "tracks",
}

FORBIDDEN_APP_NAMES = {
    "karo",
    "khol",
    "kholo",
    "khol do",
    "chalao",
    "please",
    "open",
    "start",
    "launch",
    "kar",
    "do",
    "ko",
}

class CommandRouter:

    def __init__(
        self,
        gateway_client: Optional[CoeGatewayClient] = None,
        validator: Optional[IntentValidator] = None,
    ):
        self.gateway_client: Optional[CoeGatewayClient] = gateway_client
        self.validator: IntentValidator = validator or IntentValidator()

    def is_exit_intent(self, text: str) -> bool:
        """Determines if text matches one of the approved deterministic exit phrases."""
        if not text or not isinstance(text, str):
            return False
        return bool(EXIT_COMMAND_REGEX.match(text.strip()))

    def is_standalone_exit(self, text: str) -> bool:
        """Backward-compatible alias for is_exit_intent."""
        return self.is_exit_intent(text)

    def route(
        self,
        raw_text: str,
        state: SessionState,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> CommandIntent:
        """
        Routes the raw speech text according to the current session state.
        Preserves deterministic command priority and falls back to CoE Gateway
        only when in ACTIVE_SESSION or WAITING_FOR_ACTIVATION (with wake prefix)
        and local action matching returns UNKNOWN.
        """
        normalized = normalize_text(raw_text)
        if not normalized:
            return CommandIntent(IntentType.IGNORED, raw_text=raw_text)

        if state == SessionState.SHUTDOWN:
            if self.is_exit_intent(raw_text) or self.is_exit_intent(normalized):
                return CommandIntent(IntentType.EXIT, raw_text=raw_text)
            return CommandIntent(IntentType.IGNORED, raw_text=raw_text)

        # =====================================================================
        # STATE 1: WAITING_FOR_ACTIVATION
        # =====================================================================
        if state == SessionState.WAITING_FOR_ACTIVATION:
            has_prefix, remainder = strip_wake_prefix(raw_text)

            # Must start with "Light"
            if not has_prefix:
                return CommandIntent(IntentType.IGNORED, raw_text=raw_text)

            clean_remainder = remainder.strip()
            # Do not send empty, malformed or wake-word-only input to gateway
            if not clean_remainder:
                return CommandIntent(IntentType.IGNORED, raw_text=raw_text)

            # In WAITING_FOR_ACTIVATION, all exit phrases (prefixed or unprefixed) are ignored
            if self.is_exit_intent(raw_text) or self.is_exit_intent(clean_remainder) or clean_remainder in APPROVED_EXIT_COMMANDS:
                return CommandIntent(IntentType.IGNORED, raw_text=raw_text)

            # 1. Match against deterministic local action commands first (preserves local command priority)
            action_intent = self._match_action(clean_remainder, raw_text)
            if action_intent.intent_type != IntentType.UNKNOWN:
                action_intent.should_activate_session = True
                return action_intent

            # 2. If local action is UNKNOWN, fall back to gateway with remainder
            gateway_intent = self._fallback_to_gateway(clean_remainder, raw_text, history=history)
            if gateway_intent.intent_type != IntentType.UNKNOWN:
                gateway_intent.should_activate_session = True
                return gateway_intent

            return CommandIntent(IntentType.UNKNOWN, raw_text=raw_text, should_activate_session=False)

        # =====================================================================
        # STATE 2A: AWAITING_CONTACT_SELECTION (Modal sub-state for WhatsApp disambiguation)
        # =====================================================================
        elif state == SessionState.AWAITING_CONTACT_SELECTION:
            # Standalone exit command takes top priority
            if self.is_exit_intent(normalized) or self.is_exit_intent(raw_text):
                return CommandIntent(IntentType.EXIT, raw_text=raw_text)

            has_prefix, remainder = strip_wake_prefix(raw_text)
            candidate = remainder if has_prefix else normalized
            candidate = candidate.strip().strip(".!?,")

            # Gateway is 100% bypassed in contact selection state
            if NEGATIVE_REGEX.match(candidate):
                return CommandIntent(IntentType.CONFIRM_NO, raw_text=raw_text)

            return self._match_contact_selection(candidate, raw_text)

        # =====================================================================
        # STATE 2B: AWAITING_CONFIRMATION (Modal sub-state for WhatsApp)
        # =====================================================================
        elif state == SessionState.AWAITING_CONFIRMATION:
            # Standalone exit command takes top priority to allow graceful interruption
            if self.is_exit_intent(normalized) or self.is_exit_intent(raw_text):
                return CommandIntent(IntentType.EXIT, raw_text=raw_text)

            has_prefix, remainder = strip_wake_prefix(raw_text)
            candidate = remainder if has_prefix else normalized
            candidate = candidate.strip().strip(".!?,")

            # Gateway is 100% bypassed in confirmation state
            if AFFIRMATIVE_REGEX.match(candidate):
                return CommandIntent(IntentType.CONFIRM_YES, raw_text=raw_text)
            elif NEGATIVE_REGEX.match(candidate):
                return CommandIntent(IntentType.CONFIRM_NO, raw_text=raw_text)
            else:
                return CommandIntent(IntentType.UNKNOWN, raw_text=raw_text)

        # =====================================================================
        # STATE 3: ACTIVE_SESSION
        # =====================================================================
        elif state == SessionState.ACTIVE_SESSION:
            # Check standalone exit first (deterministic priority 1)
            if self.is_exit_intent(normalized) or self.is_exit_intent(raw_text):
                return CommandIntent(IntentType.EXIT, raw_text=raw_text)

            # In active session, clean prefix if redundantly provided
            has_prefix, remainder = strip_wake_prefix(raw_text)
            command_text = remainder if has_prefix else normalized

            if self.is_exit_intent(command_text):
                return CommandIntent(IntentType.EXIT, raw_text=raw_text)

            action_intent = self._match_action(command_text, raw_text)
            if action_intent.intent_type != IntentType.UNKNOWN:
                return action_intent

            # Gateway fallback ONLY when deterministic matching returns UNKNOWN
            return self._fallback_to_gateway(command_text, raw_text, history=history)

        return CommandIntent(IntentType.IGNORED, raw_text=raw_text)

    def _match_action(self, text: str, raw_text: str) -> CommandIntent:
        """Matches a normalized command string against the supported action intents."""
        if not text:
            return CommandIntent(IntentType.UNKNOWN, raw_text=raw_text)

        # Strip common polite conversational lead-in adverbs for command matching
        polite_cleaned = re.sub(
            r"^\s*(?:please\s+|kripya\s+|zara\s+)",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip()
        text = polite_cleaned if polite_cleaned else text

        # 1. Identity Queries
        if IDENTITY_REGEX.match(text):
            return CommandIntent(IntentType.IDENTITY, raw_text=raw_text)

        # 2. YouTube Commands
        # Examples:
        #   "open youtube" -> query="" (opens homepage)
        #   "open youtube search python tutorial"
        #   "youtube python full course"
        #   "youtube arijit singh songs"
        #   "youtube light ai demo"
        #   "search machine learning on youtube"
        #   "play machine learning on youtube"
        #   "youtube search machine learning"
        #   "youtube play arijit singh"
        #   "youtube par arijit singh play karo"
        if (
            re.match(r"^(?:open|kholo|start|launch)\s+youtube(?:\s+(?:open\s+karo|open\s+kar\s+do|khol\s+do|kholo|chalao|karo|please))?$", text)
            or re.match(r"^youtube(?:\s+ko)?\s+(?:kholo|khol\s+do|open(?:\s+karo)?|chalao)(?:\s+please)?$", text)
        ):
            return CommandIntent(IntentType.SEARCH_YOUTUBE, payload={"query": ""}, raw_text=raw_text)

        m_yt_open_search = re.match(r"^(?:open|kholo)\s+youtube\s+search\s+(.+)$", text)
        if m_yt_open_search:
            query = m_yt_open_search.group(1).strip()
            if query:
                return CommandIntent(IntentType.SEARCH_YOUTUBE, payload={"query": query}, raw_text=raw_text)

        m_yt = (
            re.match(r"^(?:search|play)\s+(.+?)\s+on\s+youtube$", text) or
            re.match(r"^youtube\s+(?:search|play)\s+(.+)$", text) or
            re.match(r"^youtube\s+par\s+(.+?)(?:\s+(?:search|play)\s*(?:karo)?)?$", text) or
            re.match(r"^(?:search|play)\s+youtube\s+(?:for\s+)?(.+)$", text) or
            re.match(r"^youtube\s+(.+)$", text)
        )
        if m_yt:
            query = (m_yt.group(1) or "").strip()
            if query:
                return CommandIntent(IntentType.SEARCH_YOUTUBE, payload={"query": query}, raw_text=raw_text)

        # 3. WhatsApp Commands
        # A. Open WhatsApp Web directly: "open whatsapp", "open whatsapp web", "kholo whatsapp"
        if (
            re.match(r"^(?:open|kholo|start|launch)\s+whatsapp(?:\s+web)?(?:\s+(?:open\s+karo|khol\s+do|kholo|karo|please))?$", text)
            or re.match(r"^whatsapp(?:\s+web)?(?:\s+ko)?\s+(?:kholo|khol\s+do|open(?:\s+karo)?)(?:\s+please)?$", text)
            or re.match(r"^whatsapp\s+web$", text)
        ):
            return CommandIntent(IntentType.OPEN_APP, payload={"app_name": "whatsapp"}, raw_text=raw_text)

        # B. Messaging commands:
        #   "message Anand"
        #   "message Anand that I will be late"
        #   "send message to Anand"
        #   "send message to Anand that hello"
        #   "send a whatsapp message to Rahul"
        #   "whatsapp Anand"
        #   "Anand ko whatsapp message bhejo"
        m_wa_msg = re.match(r"^message\s+([a-z]+)(?:\s+(?:that|ki)\s+(.+))?$", text)
        m_wa_send = re.match(r"^(?:send\s+(?:a\s+)?)?(?:whatsapp\s+)?message\s+to\s+([a-z]+)(?:\s+(?:that|ki)\s+(.+))?$", text)
        m_wa_direct = re.match(r"^whatsapp\s+([a-z]+)(?:\s+(?:message|that|ki)\s+(.+))?$", text)
        m_wa_hindi = re.match(r"^([a-z]+)\s+ko\s+(?:whatsapp\s+)?(?:par\s+)?(?:message\s+)?bhejo(?:\s+(?:ki|that)\s+(.+))?$", text)

        m_wa = m_wa_msg or m_wa_send or m_wa_direct or m_wa_hindi
        if m_wa:
            contact = m_wa.group(1).strip()
            if contact != "web":  # avoid collision with 'whatsapp web'
                msg = m_wa.group(2).strip() if len(m_wa.groups()) >= 2 and m_wa.group(2) else ""
                return CommandIntent(IntentType.WHATSAPP_START, payload={"contact": contact, "initial_message": msg}, raw_text=raw_text)

        # 4. Music Playback Commands (Phase 8.2 & D4.2)
        if STOP_PLAYLIST_REGEX.match(text):
            return CommandIntent(IntentType.STOP_PLAYLIST, raw_text=raw_text)

        if SHUFFLE_PLAYLIST_REGEX.match(text):
            return CommandIntent(IntentType.SHUFFLE_PLAYLIST, raw_text=raw_text)

        if NEXT_SONG_REGEX.match(text):
            return CommandIntent(IntentType.NEXT_SONG, raw_text=raw_text)

        if PREVIOUS_SONG_REGEX.match(text):
            return CommandIntent(IntentType.PREVIOUS_SONG, raw_text=raw_text)

        if PAUSE_MUSIC_REGEX.match(text):
            return CommandIntent(IntentType.PAUSE_MUSIC, raw_text=raw_text)

        if RESUME_MUSIC_REGEX.match(text):
            return CommandIntent(IntentType.RESUME_MUSIC, raw_text=raw_text)

        if STOP_MUSIC_REGEX.match(text):
            return CommandIntent(IntentType.STOP_MUSIC, raw_text=raw_text)

        # B. Playlist Requests
        m_pl_empty = (
            re.match(r"^(?:play|start|kholo|chalao|sunao|open)\s+(?:the\s+)?playlist$", text) or
            re.match(r"^playlist(?:\s*(?:ko\s*)?(?:play\s+karo|chalao|sunao|play|start|kholo))?$", text)
        )
        if m_pl_empty:
            return CommandIntent(
                IntentType.PLAY_PLAYLIST,
                payload={"playlist_name": "", "error": "empty_playlist", "is_valid": False},
                raw_text=raw_text,
            )

        m_pl_1 = re.match(r"^(?:play|start|kholo|chalao|sunao|open)\s+(?:the\s+)?([a-z0-9_-]+)\s+playlist$", text)
        m_pl_2 = re.match(r"^([a-z0-9_-]+)\s+playlist(?:\s*(?:ko\s*)?(?:play\s+karo|chalao|sunao|play|start|kholo))?$", text)
        m_pl = m_pl_1 or m_pl_2
        if m_pl:
            raw_pl_name = m_pl.group(1).strip().lower()
            matched_pl_key = None
            for k in DEFAULT_PLAYLISTS:
                if k.lower() == raw_pl_name:
                    matched_pl_key = k
                    break

            if matched_pl_key:
                return CommandIntent(
                    IntentType.PLAY_PLAYLIST,
                    payload={"playlist_name": matched_pl_key, "is_valid": True},
                    raw_text=raw_text,
                )
            else:
                return CommandIntent(
                    IntentType.PLAY_PLAYLIST,
                    payload={"playlist_name": raw_pl_name, "error": "unknown_playlist", "is_valid": False},
                    raw_text=raw_text,
                )

        # C. Empty or Ambiguous Song Queries
        m_song_empty = (
            re.match(r"^(?:play|chalao|sunao)\s+(?:a\s+|the\s+)?(?:song|gaana|gaane|track|music)$", text) or
            re.match(r"^(?:song|gaana|gaane|track|music)\s*(?:ko\s*)?(?:play\s+karo|chalao|sunao|play)$", text) or
            re.match(r"^(?:play|play\s+karo|chalao|sunao)$", text)
        )
        if m_song_empty:
            return CommandIntent(
                IntentType.PLAY_SONG,
                payload={"query": "", "error": "empty_query", "is_valid": False},
                raw_text=raw_text,
            )

        # D. Single Song Playback Requests
        m_song_suffix = re.match(r"^(.+?)\s+(?:song|gaana|track)\s*(?:ko\s*)?(?:play\s+karo|chalao|bajaao|sunao|play)$", text)
        m_song_prefix = re.match(r"^(?:play|chalao|bajaao|sunao)\s+(?:the\s+)?(?:song|gaana|track)\s+(.+)$", text)
        m_song_play_karo_prefix = re.match(r"^(?:play\s+karo|karo\s+play|chalao|bajaao|sunao)\s+(?:the\s+)?(?:song\s+|gaana\s+|track\s+)?(.+)$", text)
        m_song_can_you = re.match(r"^(?:can|could)\s+you\s+(?:please\s+)?(?:play|chalao|sunao)\s+(?:(?:the\s+)?(?:song|gaana|track)\s+(.+)|(.+?)\s+(?:song|gaana|track))[.?]?$", text)
        m_song_play_suffix = re.match(r"^play\s+(.+?)\s+(?:song|gaana|track)$", text)
        m_song_direct_hindi = re.match(r"^(.+?)\s*(?:ko\s*)?(?:play\s+karo|chalao|bajaao|sunao)$", text)
        m_song_play_direct = re.match(r"^play\s+(.+)$", text)

        if m_song_can_you:
            song_query = (m_song_can_you.group(1) or m_song_can_you.group(2) or "").strip()
            if song_query.lower() in AMBIGUOUS_SONG_TOKENS:
                return CommandIntent(
                    IntentType.PLAY_SONG,
                    payload={"query": "", "error": "ambiguous_query", "is_valid": False},
                    raw_text=raw_text,
                )
            return CommandIntent(
                IntentType.PLAY_SONG,
                payload={"query": song_query, "is_valid": True},
                raw_text=raw_text,
            )

        m_song = m_song_suffix or m_song_prefix or m_song_play_karo_prefix or m_song_play_suffix or m_song_direct_hindi or m_song_play_direct
        if m_song:
            song_query = m_song.group(1).strip()
            if song_query.lower() in AMBIGUOUS_SONG_TOKENS:
                return CommandIntent(
                    IntentType.PLAY_SONG,
                    payload={"query": "", "error": "ambiguous_query", "is_valid": False},
                    raw_text=raw_text,
                )
            return CommandIntent(
                IntentType.PLAY_SONG,
                payload={"query": song_query, "is_valid": True},
                raw_text=raw_text,
            )

        # 5. Google Search Commands
        # Examples:
        #   "search latest AI"
        #   "search for latest AI"
        #   "search python tutorials on google"
        #   "google search machine learning"
        #   "google machine learning"
        #   "google par machine learning search karo"
        m_google = (
            re.match(r"^(?:search\s+for|search)\s+(.+?)\s+on\s+google$", text) or
            re.match(r"^google\s+search\s+(.+)$", text) or
            re.match(r"^search\s+google\s+(?:for\s+)?(.+)$", text) or
            re.match(r"^google\s+par\s+(.+?)\s*(?:search\s+karo|kholo)?$", text) or
            re.match(r"^google\s+(.+)$", text) or
            re.match(r"^search\s+(?:for\s+)?(.+)$", text)
        )
        if m_google:
            query = (m_google.group(1) or "").strip()
            if query:
                return CommandIntent(IntentType.SEARCH_GOOGLE, payload={"query": query}, raw_text=raw_text)

        # 5. Application Launching Commands
        # Examples: "open brave", "open chrome", "brave kholo", "open notepad karo", "launch vs code"
        m_app_prefix = re.match(
            r"^(?:open|kholo|start|launch)\s+([a-z0-9\s]+?)(?:\s+(?:open\s+karo|open\s+kar\s+do|khol\s+do|kholo|chalao|karo|please))?$",
            text,
        )
        m_app_suffix = re.match(
            r"^([a-z0-9\s]+?)(?:\s+ko)?\s+(?:kholo|khol\s+do|open(?:\s+karo)?|chalao)(?:\s+please)?$",
            text,
        )
        m_app = m_app_prefix or m_app_suffix
        if m_app:
            app_name = m_app.group(1).strip()
            if app_name and app_name.lower() not in FORBIDDEN_APP_NAMES:
                return CommandIntent(IntentType.OPEN_APP, payload={"app_name": app_name}, raw_text=raw_text)

        return CommandIntent(IntentType.UNKNOWN, raw_text=raw_text)

    def _fallback_to_gateway(
        self,
        text: str,
        raw_text: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> CommandIntent:
        """
        Invokes the CoE AI Gateway client on unresolved speech,
        and enforces local schema validation on the response.
        """
        if self.gateway_client is None:
            return CommandIntent(IntentType.UNKNOWN, raw_text=raw_text)

        if not self.gateway_client.is_configured:
            logger.debug("CoE AI Gateway is not configured. Fallback skipped.")
            return CommandIntent(
                IntentType.UNKNOWN,
                payload={"error_status": GatewayStatus.NOT_CONFIGURED.name},
                raw_text=raw_text,
            )

        try:
            if history:
                resp: GatewayResponse = self.gateway_client.complete(text, history=history)
            else:
                resp: GatewayResponse = self.gateway_client.complete(text)
        except TypeError:
            # Fallback for legacy mocks or external clients lacking history parameter
            resp = self.gateway_client.complete(text)

        if not resp.is_success:
            logger.warning(f"Gateway fallback failed with status: {resp.status.name}")
            return CommandIntent(
                IntentType.UNKNOWN,
                payload={
                    "error_status": resp.status.name,
                    "error_message": resp.error_message,
                },
                raw_text=raw_text,
            )

        # Enforce local validation as the final authority
        val_result: ValidationResult = self.validator.validate(resp.raw_content)
        if not val_result.is_valid:
            logger.warning(f"Gateway output rejected by local validator: {val_result.error_message}")
            return CommandIntent(
                IntentType.UNKNOWN,
                payload={
                    "error_status": GatewayStatus.INVALID_RESPONSE.name,
                    "validation_error": val_result.error_message,
                },
                raw_text=raw_text,
            )

        intent_type = self._map_validated_intent(val_result.intent)
        payload = dict(val_result.payload)
        if val_result.needs_clarification and val_result.clarification_prompt:
            payload["clarification_prompt"] = val_result.clarification_prompt
        if val_result.voice_response:
            payload["voice_response"] = val_result.voice_response

        logger.info(f"Gateway intent accepted and validated: {intent_type.name}")
        return CommandIntent(intent_type, payload=payload, raw_text=raw_text)

    def _map_validated_intent(self, intent_str: str) -> IntentType:
        """Maps validated intent string to CommandRouter IntentType enum."""
        mapping = {
            "OPEN_APP": IntentType.OPEN_APP,
            "OPEN_WEBSITE": IntentType.OPEN_WEBSITE,
            "SEARCH_GOOGLE": IntentType.SEARCH_GOOGLE,
            "SEARCH_YOUTUBE": IntentType.SEARCH_YOUTUBE,
            "WHATSAPP_START": IntentType.WHATSAPP_START,
            "IDENTITY": IntentType.IDENTITY,
            "CLARIFICATION": IntentType.CLARIFICATION,
            "CONVERSATION": IntentType.CONVERSATION,
        }
        return mapping.get(intent_str, IntentType.UNKNOWN)

    def _match_contact_selection(self, text: str, raw_text: str) -> CommandIntent:
        """Matches contact selection input deterministically without gateway."""
        if not text:
            return CommandIntent(IntentType.UNKNOWN, raw_text=raw_text)

        cleaned = re.sub(r"^(?:number|option)\s+", "", text).strip()
        cleaned = re.sub(r"\s+wala$", "", cleaned).strip()

        if cleaned in ORDINAL_MAP:
            return CommandIntent(
                IntentType.CONTACT_SELECT,
                payload={"index": ORDINAL_MAP[cleaned], "selection": text},
                raw_text=raw_text,
            )

        # Otherwise treat as candidate name / text selection
        return CommandIntent(
            IntentType.CONTACT_SELECT,
            payload={"selection": text},
            raw_text=raw_text,
        )
