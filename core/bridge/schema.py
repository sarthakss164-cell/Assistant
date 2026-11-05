"""
Versioned message schema and validation for LIGHT AI local WebSocket bridge.
Defines JSON message structures, permitted message types, and input validation.
"""

from enum import Enum
import json
import time
import uuid
from typing import Any, Dict, Optional, Tuple

SCHEMA_VERSION = "1.0"

# Maximum allowable inbound payload size (64 KB) to protect against memory exhaustion
MAX_INBOUND_MESSAGE_SIZE = 65536

# Maximum allowable text length in conversation events
MAX_TEXT_PAYLOAD_LENGTH = 2000

# Inbound message types permitted from desktop clients in Phase D1-D4.3.
# General command execution, shell commands, or arbitrary code are strictly prohibited.
ALLOWED_INBOUND_TYPES = {"ping", "status", "music_control", "playlist_control", "mic_control", "text_command"}

# Strictly allowlisted actions for music_control messages
ALLOWED_MUSIC_ACTIONS = {
    "play",
    "pause",
    "resume",
    "toggle_play",
    "stop",
    "next",
    "previous",
    "volume",
    "mute",
    "seek",
}

# Strictly allowlisted actions for playlist_control messages (Phase D4.2)
ALLOWED_PLAYLIST_ACTIONS = {
    "start",
    "select_song",
    "next",
    "previous",
    "toggle_shuffle",
    "stop",
    "get_snapshot",
}

# Strictly allowlisted actions for mic_control messages (Phase D4.2)
ALLOWED_MIC_ACTIONS = {
    "set_active",
    "toggle",
}


class BridgeMessageType(str, Enum):
    """Supported bridge message types."""
    TELEMETRY = "telemetry"
    STATUS = "status"
    PING = "ping"
    PONG = "pong"
    ERROR = "error"
    USER_UTTERANCE = "user_utterance"
    ASSISTANT_SPOKEN = "assistant_spoken"
    VOICE_STATE = "voice_state"
    MUSIC_STATE = "music_state"
    MUSIC_CONTROL = "music_control"
    PLAYLIST_STATE = "playlist_state"
    PLAYLIST_CONTROL = "playlist_control"
    MIC_STATE = "mic_state"
    MIC_CONTROL = "mic_control"
    TEXT_COMMAND = "text_command"
    TEXT_COMMAND_ACK = "text_command_ack"
    AI_CORE_STATE = "ai_core_state"


def create_message(
    msg_type: BridgeMessageType | str,
    payload: Dict[str, Any],
    schema_version: str = SCHEMA_VERSION,
    event_id: Optional[str] = None,
    correlation_id: Optional[Any] = None,
    timestamp: Optional[float] = None,
) -> str:
    """
    Constructs a serialized, versioned JSON message adhering to the bridge schema.
    """
    msg: Dict[str, Any] = {
        "schema_version": schema_version,
        "type": msg_type.value if isinstance(msg_type, BridgeMessageType) else str(msg_type),
        "timestamp": timestamp or time.time(),
        "payload": payload,
    }
    if event_id is not None:
        msg["event_id"] = str(event_id)
    if correlation_id is not None:
        msg["correlation_id"] = correlation_id
    return json.dumps(msg)


def create_telemetry_message(payload: Dict[str, Any]) -> str:
    """Constructs a serialized telemetry broadcast message."""
    return create_message(BridgeMessageType.TELEMETRY, payload)


def create_status_message(status: str, details: Optional[Dict[str, Any]] = None) -> str:
    """Constructs a serialized status message."""
    payload = {"status": status}
    if details:
        payload["details"] = details
    return create_message(BridgeMessageType.STATUS, payload)


def create_error_message(error_code: str, message: str) -> str:
    """Constructs a serialized error response message."""
    return create_message(
        BridgeMessageType.ERROR,
        {"code": error_code, "message": message},
    )


def create_user_utterance_event(
    text: str,
    correlation_id: Optional[Any] = None,
    event_id: Optional[str] = None,
    timestamp: Optional[float] = None,
) -> str:
    """
    Constructs a serialized user_utterance event for admitted user requests.
    Validates and normalizes whitespace, truncating if exceeding MAX_TEXT_PAYLOAD_LENGTH.
    """
    clean_text = (text or "").strip()
    if len(clean_text) > MAX_TEXT_PAYLOAD_LENGTH:
        clean_text = clean_text[:MAX_TEXT_PAYLOAD_LENGTH]

    evt_id = event_id or f"evt_u_{time.time():.4f}_{uuid.uuid4().hex[:6]}"
    payload = {
        "text": clean_text,
        "sender": "USER",
    }
    return create_message(
        msg_type=BridgeMessageType.USER_UTTERANCE,
        payload=payload,
        event_id=evt_id,
        correlation_id=correlation_id,
        timestamp=timestamp,
    )


def create_assistant_spoken_event(
    text: str,
    correlation_id: Optional[Any] = None,
    event_id: Optional[str] = None,
    timestamp: Optional[float] = None,
) -> str:
    """
    Constructs a serialized assistant_spoken event for actually spoken responses.
    Validates and normalizes whitespace, truncating if exceeding MAX_TEXT_PAYLOAD_LENGTH.
    """
    clean_text = (text or "").strip()
    if len(clean_text) > MAX_TEXT_PAYLOAD_LENGTH:
        clean_text = clean_text[:MAX_TEXT_PAYLOAD_LENGTH]

    evt_id = event_id or f"evt_a_{time.time():.4f}_{uuid.uuid4().hex[:6]}"
    payload = {
        "text": clean_text,
        "sender": "ASSISTANT",
    }
    return create_message(
        msg_type=BridgeMessageType.ASSISTANT_SPOKEN,
        payload=payload,
        event_id=evt_id,
        correlation_id=correlation_id,
        timestamp=timestamp,
    )


def create_voice_state_event(
    channel: str,
    state: str,
    correlation_id: Optional[Any] = None,
    detail: Optional[str] = None,
    event_id: Optional[str] = None,
    timestamp: Optional[float] = None,
) -> str:
    """
    Constructs a serialized voice_state event for microphone capture and TTS playback lifecycle.
    channel: 'user' or 'assistant'
    state: for user: 'IDLE', 'LISTENING', 'PROCESSING'
           for assistant: 'STANDBY', 'SPEAKING', 'ERROR'
    """
    clean_chan = (channel or "").strip().lower()
    clean_state = (state or "").strip().upper()
    evt_id = event_id or f"evt_vs_{time.time():.4f}_{uuid.uuid4().hex[:6]}"
    payload: Dict[str, Any] = {
        "channel": clean_chan,
        "state": clean_state,
    }
    if detail is not None:
        clean_detail = str(detail).strip()
        if len(clean_detail) > MAX_TEXT_PAYLOAD_LENGTH:
            clean_detail = clean_detail[:MAX_TEXT_PAYLOAD_LENGTH]
        payload["detail"] = clean_detail

    return create_message(
        msg_type=BridgeMessageType.VOICE_STATE,
        payload=payload,
        event_id=evt_id,
        correlation_id=correlation_id,
        timestamp=timestamp,
    )


def create_music_state_event(
    state: str,
    is_playing: bool,
    title: str = "",
    artist: str = "",
    duration_seconds: float = 0.0,
    position_seconds: float = 0.0,
    source: str = "YouTube",
    playlist: Optional[list] = None,
    last_played: Optional[str] = None,
    correlation_id: Optional[Any] = None,
    event_id: Optional[str] = None,
    timestamp: Optional[float] = None,
) -> str:
    """
    Constructs a serialized music_state event for synchronization with the dashboard.
    state: 'IDLE', 'LOADING', 'PLAYING', 'PAUSED', 'STOPPED', 'ERROR'
    """
    clean_state = (state or "IDLE").strip().upper()
    evt_id = event_id or f"evt_ms_{time.time():.4f}_{uuid.uuid4().hex[:6]}"
    payload: Dict[str, Any] = {
        "state": clean_state,
        "is_playing": bool(is_playing),
        "title": (title or "").strip()[:MAX_TEXT_PAYLOAD_LENGTH],
        "artist": (artist or "").strip()[:MAX_TEXT_PAYLOAD_LENGTH],
        "duration_seconds": float(duration_seconds or 0.0),
        "position_seconds": float(position_seconds or 0.0),
        "source": (source or "YouTube").strip(),
        "playlist": list(playlist or []),
        "last_played": (last_played or "").strip()[:MAX_TEXT_PAYLOAD_LENGTH] if last_played else None,
    }
    return create_message(
        msg_type=BridgeMessageType.MUSIC_STATE,
        payload=payload,
        event_id=evt_id,
        correlation_id=correlation_id,
        timestamp=timestamp,
    )


def create_playlist_state_event(
    playlist_data: Dict[str, Any],
    correlation_id: Optional[Any] = None,
    event_id: Optional[str] = None,
    timestamp: Optional[float] = None,
) -> str:
    """
    Constructs a serialized playlist_state event for synchronization with the dashboard.
    """
    evt_id = event_id or f"evt_pl_{time.time():.4f}_{uuid.uuid4().hex[:6]}"
    return create_message(
        msg_type=BridgeMessageType.PLAYLIST_STATE,
        payload=dict(playlist_data or {}),
        event_id=evt_id,
        correlation_id=correlation_id,
        timestamp=timestamp,
    )


def create_mic_state_event(
    is_active: bool,
    correlation_id: Optional[Any] = None,
    event_id: Optional[str] = None,
    timestamp: Optional[float] = None,
) -> str:
    """
    Constructs a serialized mic_state event for microphone ACTIVE/MUTED lifecycle synchronization.
    """
    evt_id = event_id or f"evt_mic_{time.time():.4f}_{uuid.uuid4().hex[:6]}"
    payload: Dict[str, Any] = {
        "is_active": bool(is_active),
    }
    return create_message(
        msg_type=BridgeMessageType.MIC_STATE,
        payload=payload,
        event_id=evt_id,
        correlation_id=correlation_id,
        timestamp=timestamp,
    )


def create_text_command_ack_event(
    request_id: str,
    success: bool,
    status: str,
    message: str = "",
    correlation_id: Optional[Any] = None,
    event_id: Optional[str] = None,
    timestamp: Optional[float] = None,
) -> str:
    """
    Constructs a serialized text_command_ack event in response to a text command.
    """
    evt_id = event_id or f"evt_txtack_{time.time():.4f}_{uuid.uuid4().hex[:6]}"
    payload: Dict[str, Any] = {
        "request_id": str(request_id),
        "success": bool(success),
        "status": str(status),
        "message": str(message),
    }
    return create_message(
        msg_type=BridgeMessageType.TEXT_COMMAND_ACK,
        payload=payload,
        event_id=evt_id,
        correlation_id=correlation_id or request_id,
        timestamp=timestamp,
    )


def create_ai_core_state_event(
    payload: Dict[str, Any],
    correlation_id: Optional[Any] = None,
    event_id: Optional[str] = None,
    timestamp: Optional[float] = None,
) -> str:
    """
    Constructs a serialized ai_core_state event for real-time AI runtime telemetry updates.
    """
    evt_id = event_id or f"evt_ai_{time.time():.4f}_{uuid.uuid4().hex[:6]}"
    return create_message(
        msg_type=BridgeMessageType.AI_CORE_STATE,
        payload=payload,
        event_id=evt_id,
        correlation_id=correlation_id,
        timestamp=timestamp,
    )


def validate_incoming_message(raw_text: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """
    Validates an incoming message from the client.
    Rejects malformed JSON, unknown types, or prohibited commands.

    Returns:
        (is_valid: bool, parsed_dict: Optional[dict], error_reason: Optional[str])
    """
    if not raw_text or not isinstance(raw_text, str):
        return False, None, "Empty or non-string message received"

    if len(raw_text) > MAX_INBOUND_MESSAGE_SIZE:
        return False, None, f"Message exceeds maximum allowed size of {MAX_INBOUND_MESSAGE_SIZE} bytes"

    try:
        data = json.loads(raw_text)
    except Exception as e:
        return False, None, f"Invalid JSON format: {e}"

    if not isinstance(data, dict):
        return False, None, "Message root must be a JSON object"

    # Schema version check
    version = data.get("schema_version")
    if version != SCHEMA_VERSION:
        return False, None, f"Unsupported schema_version: expected '{SCHEMA_VERSION}', got '{version}'"

    msg_type = data.get("type")
    if not msg_type or not isinstance(msg_type, str):
        return False, None, "Missing or non-string 'type' field"

    clean_type = msg_type.strip().lower()
    if clean_type not in ALLOWED_INBOUND_TYPES:
        return False, None, f"Unsupported or prohibited message type: '{msg_type}'"

    payload = data.get("payload", {})
    if not isinstance(payload, dict):
        return False, None, "'payload' must be a JSON object"

    # Specific payload validation for music_control messages
    if clean_type == "music_control":
        action = payload.get("action")
        if not action or not isinstance(action, str):
            return False, None, "Missing or non-string 'action' in music_control payload"
        clean_action = action.strip().lower()
        if clean_action not in ALLOWED_MUSIC_ACTIONS:
            return False, None, f"Unsupported or prohibited music action: '{action}'"

        if clean_action == "volume":
            val = payload.get("value")
            if val is None or not isinstance(val, (int, float)) or not (0 <= val <= 100):
                return False, None, "Volume value must be a number between 0 and 100"
        elif clean_action == "seek":
            val = payload.get("value")
            if val is None or not isinstance(val, (int, float)) or val < 0:
                return False, None, "Seek position must be a non-negative number"
        elif clean_action == "mute":
            val = payload.get("value")
            if val is not None and not isinstance(val, bool):
                return False, None, "Mute value must be a boolean"

    # Specific payload validation for playlist_control messages (Phase D4.2)
    elif clean_type == "playlist_control":
        action = payload.get("action")
        if not action or not isinstance(action, str):
            return False, None, "Missing or non-string 'action' in playlist_control payload"
        clean_action = action.strip().lower()
        if clean_action not in ALLOWED_PLAYLIST_ACTIONS:
            return False, None, f"Unsupported or prohibited playlist action: '{action}'"

        if clean_action == "start":
            pl_id = payload.get("playlist_id")
            if not pl_id or not isinstance(pl_id, str):
                return False, None, "Missing or invalid 'playlist_id' for start action"
        elif clean_action == "select_song":
            has_idx = "index" in payload and isinstance(payload.get("index"), (int, float))
            has_title = "title" in payload and isinstance(payload.get("title"), str) and payload.get("title").strip()
            if not has_idx and not has_title:
                return False, None, "select_song requires either 'index' (int) or 'title' (string)"

    # Specific payload validation for mic_control messages (Phase D4.2)
    elif clean_type == "mic_control":
        action = payload.get("action")
        if not action or not isinstance(action, str):
            return False, None, "Missing or non-string 'action' in mic_control payload"
        clean_action = action.strip().lower()
        if clean_action not in ALLOWED_MIC_ACTIONS:
            return False, None, f"Unsupported or prohibited mic action: '{action}'"

        if clean_action == "set_active":
            val = payload.get("value")
            if val is None or not isinstance(val, bool):
                return False, None, "set_active requires a boolean 'value' field"

    # Specific payload validation for text_command messages (Phase D4.3)
    elif clean_type == "text_command":
        text = payload.get("text")
        if text is None or not isinstance(text, str) or not text.strip():
            return False, None, "Missing or empty 'text' in text_command payload"
        if len(text.strip()) > 500:
            return False, None, "Text command exceeds maximum length of 500 characters"
        req_id = payload.get("request_id")
        if req_id is not None and not isinstance(req_id, (str, int)):
            return False, None, "'request_id' must be a string or integer if provided"

    return True, data, None

