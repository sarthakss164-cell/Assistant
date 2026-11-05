"""
LIGHT AI V1.0 Bridge Package.
Provides local WebSocket communication and live system telemetry.
"""

from core.bridge.schema import (
    SCHEMA_VERSION,
    ALLOWED_INBOUND_TYPES,
    ALLOWED_MUSIC_ACTIONS,
    ALLOWED_PLAYLIST_ACTIONS,
    ALLOWED_MIC_ACTIONS,
    BridgeMessageType,
    create_message,
    create_telemetry_message,
    create_status_message,
    create_error_message,
    create_user_utterance_event,
    create_assistant_spoken_event,
    create_voice_state_event,
    create_music_state_event,
    create_playlist_state_event,
    create_mic_state_event,
    create_text_command_ack_event,
    validate_incoming_message,
)
from core.bridge.telemetry import TelemetryCollector
from core.bridge.server import (
    WebSocketBridgeServer,
    DEFAULT_HOST,
    DEFAULT_PORT,
    TELEMETRY_INTERVAL_SECONDS,
)

__all__ = [
    "SCHEMA_VERSION",
    "ALLOWED_INBOUND_TYPES",
    "ALLOWED_MUSIC_ACTIONS",
    "ALLOWED_PLAYLIST_ACTIONS",
    "ALLOWED_MIC_ACTIONS",
    "BridgeMessageType",
    "create_message",
    "create_telemetry_message",
    "create_status_message",
    "create_error_message",
    "create_user_utterance_event",
    "create_assistant_spoken_event",
    "create_voice_state_event",
    "create_music_state_event",
    "create_playlist_state_event",
    "create_mic_state_event",
    "create_text_command_ack_event",
    "validate_incoming_message",
    "TelemetryCollector",
    "WebSocketBridgeServer",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "TELEMETRY_INTERVAL_SECONDS",
]

