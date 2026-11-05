"""
Unit and integration tests for Phase 6:
V3.0 Reference-Based Conversational Q&A in Light AI V1.0.

Verifies:
1. Browser Null Normalization:
   - JSON primitive null is accepted as None.
   - String "null" (trimmed/lowercase) normalized to None.
   - String "none" (trimmed/lowercase) normalized to None.
   - Actual unsupported browser names ("safari", "firefox") remain strictly rejected.
2. CONVERSATION Intent Validation:
   - Valid CONVERSATION intent with non-empty voice_response passes validation.
   - Missing or null voice_response is rejected.
   - Empty or whitespace voice_response is rejected.
   - Contradictory action fields (app_name, website, browser, query, contact, initial_message) are rejected.
   - Sanitization and 250-character length bounding are enforced.
3. Router Mapping:
   - Gateway output with CONVERSATION maps to IntentType.CONVERSATION.
   - Preserves voice_response in CommandIntent.payload.
   - Deterministic local commands still take priority over gateway Q&A.
4. Assistant Dispatch & Action Isolation:
   - Assistant speaks valid conversational response via mocked TTS.
   - Zero external actions are executed (no app launch, no browser, no search, no WhatsApp).
   - Conversational intent cannot launch apps or open websites.
   - Conversational intent cannot invoke search handlers.
   - Conversational intent cannot send WhatsApp messages.
   - WhatsApp confirmation state bypasses gateway and cannot be overridden by CONVERSATION.
5. Error and Robustness:
   - Gateway errors fall back to safe error notices.
   - Malformed gateway JSON falls back safely.
   - Fixed identity response remains untouched.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from core.intent_validator import IntentValidator, ValidationResult, MAX_VOICE_RESPONSE_LENGTH
from core.router import CommandRouter, IntentType, CommandIntent
from core.assistant import LightAssistant
from core.state_machine import SessionState
from core.coe_gateway import CoeGatewayClient, GatewayResponse, GatewayStatus
from config.settings import FIXED_IDENTITY_RESPONSE


@pytest.fixture
def validator():
    return IntentValidator()


@pytest.fixture
def mock_gateway():
    client = MagicMock(spec=CoeGatewayClient)
    client.is_configured = True
    return client


@pytest.fixture
def mock_assistant(mock_gateway):
    listener = MagicMock()
    stt = MagicMock()
    tts = MagicMock()
    launcher = MagicMock()
    launcher.launch.return_value = (True, "App open kar rahi hoon.")

    assistant = LightAssistant(
        listener=listener,
        stt=stt,
        tts=tts,
        app_launcher=launcher,
        gateway_client=mock_gateway,
    )
    return assistant


# =============================================================================
# 1. BROWSER NULL NORMALIZATION TESTS
# =============================================================================

def test_browser_json_null_accepted_as_none(validator):
    """JSON literal null for browser evaluates to None and passes validation."""
    res = validator.validate({
        "intent": "OPEN_WEBSITE",
        "website": "youtube",
        "browser": None,
    })
    assert res.is_valid is True
    assert res.payload["browser"] is None


def test_browser_string_null_normalized_to_none(validator):
    """String 'null' for browser is normalized to None and passes validation."""
    for null_str in ["null", "NULL", "  null  "]:
        res = validator.validate({
            "intent": "OPEN_WEBSITE",
            "website": "youtube",
            "browser": null_str,
        })
        assert res.is_valid is True
        assert res.payload["browser"] is None


def test_browser_string_none_normalized_to_none(validator):
    """String 'none' for browser is normalized to None and passes validation."""
    for none_str in ["none", "NONE", "  None  "]:
        res = validator.validate({
            "intent": "OPEN_WEBSITE",
            "website": "google",
            "browser": none_str,
        })
        assert res.is_valid is True
        assert res.payload["browser"] is None


def test_browser_unsupported_actual_browser_remains_rejected(validator):
    """Unsupported actual browser names remain strictly rejected."""
    for bad_browser in ["safari", "firefox", "opera", "tor", "internet explorer"]:
        res = validator.validate({
            "intent": "OPEN_WEBSITE",
            "website": "youtube",
            "browser": bad_browser,
        })
        assert res.is_valid is False
        assert "Unsupported browser" in res.error_message


def test_browser_valid_allowlisted_browsers_accepted(validator):
    """Allowlisted browsers (brave, chrome, edge) continue to validate cleanly."""
    for browser in ["brave", "chrome", "edge"]:
        res = validator.validate({
            "intent": "OPEN_WEBSITE",
            "website": "youtube",
            "browser": browser,
        })
        assert res.is_valid is True
        assert res.payload["browser"] == browser


# =============================================================================
# 2. CONVERSATION INTENT VALIDATION TESTS
# =============================================================================

def test_valid_conversation_intent(validator):
    """Valid CONVERSATION intent with voice_response passes validation."""
    res = validator.validate({
        "intent": "CONVERSATION",
        "voice_response": "Artificial intelligence ek technology hai jo computers ko smart banati hai.",
    })
    assert res.is_valid is True
    assert res.intent == "CONVERSATION"
    assert res.payload == {}
    assert res.voice_response == "Artificial intelligence ek technology hai jo computers ko smart banati hai."


def test_conversation_missing_voice_response_rejected(validator):
    """CONVERSATION without voice_response must be rejected."""
    res = validator.validate({
        "intent": "CONVERSATION",
    })
    assert res.is_valid is False
    assert "requires a non-empty 'voice_response'" in res.error_message


def test_conversation_empty_voice_response_rejected(validator):
    """CONVERSATION with empty or whitespace-only voice_response must be rejected."""
    for empty_val in ["", "   ", "\t\n"]:
        res = validator.validate({
            "intent": "CONVERSATION",
            "voice_response": empty_val,
        })
        assert res.is_valid is False
        assert "requires a non-empty 'voice_response'" in res.error_message


def test_conversation_contradictory_action_fields_rejected(validator):
    """CONVERSATION containing any executable action field must be rejected."""
    action_fields = [
        {"app_name": "notepad"},
        {"website": "youtube"},
        {"browser": "chrome"},
        {"query": "machine learning"},
        {"contact": "rahul"},
        {"initial_message": "hello"},
    ]
    for field_dict in action_fields:
        payload = {
            "intent": "CONVERSATION",
            "voice_response": "Valid answer.",
            **field_dict,
        }
        res = validator.validate(payload)
        assert res.is_valid is False
        assert "Contradictory action fields in 'CONVERSATION' intent." in res.error_message


def test_conversation_null_action_fields_accepted(validator):
    """CONVERSATION where action fields are literal null or string 'null' must pass."""
    payload = {
        "intent": "CONVERSATION",
        "app_name": None,
        "website": None,
        "browser": "null",  # normalized to None
        "query": None,
        "contact": None,
        "initial_message": None,
        "voice_response": "Machine learning AI ka ek hissa hai.",
    }
    res = validator.validate(payload)
    assert res.is_valid is True
    assert res.intent == "CONVERSATION"
    assert res.voice_response == "Machine learning AI ka ek hissa hai."


def test_conversation_voice_response_sanitization(validator):
    """voice_response in CONVERSATION is sanitized and length-bounded."""
    dangerous = "AI is cool!\x00\x1f <script>alert('xss')</script> " + ("knowledge " * 50)
    res = validator.validate({
        "intent": "CONVERSATION",
        "voice_response": dangerous,
    })
    assert res.is_valid is True
    assert "<script>" not in res.voice_response
    assert "\x00" not in res.voice_response
    assert len(res.voice_response) <= MAX_VOICE_RESPONSE_LENGTH


# =============================================================================
# 3. ROUTER MAPPING TESTS
# =============================================================================

def test_router_maps_conversation_intent(mock_gateway):
    """Router correctly maps validated CONVERSATION from gateway to IntentType.CONVERSATION."""
    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content=json.dumps({
            "intent": "CONVERSATION",
            "voice_response": "AI computers ko sikhne ki shamta deta hai.",
        }),
    )

    router = CommandRouter(gateway_client=mock_gateway)
    intent = router.route("explain artificial intelligence in simple words", SessionState.ACTIVE_SESSION)

    assert intent.intent_type == IntentType.CONVERSATION
    assert intent.payload["voice_response"] == "AI computers ko sikhne ki shamta deta hai."


def test_deterministic_commands_take_priority_over_conversation(mock_gateway):
    """Deterministic local commands (app launch, search, identity) do NOT call gateway."""
    router = CommandRouter(gateway_client=mock_gateway)

    # 1. Identity
    intent_id = router.route("who are you", SessionState.ACTIVE_SESSION)
    assert intent_id.intent_type == IntentType.IDENTITY
    mock_gateway.complete.assert_not_called()

    # 2. App Launch
    intent_app = router.route("open notepad", SessionState.ACTIVE_SESSION)
    assert intent_app.intent_type == IntentType.OPEN_APP
    mock_gateway.complete.assert_not_called()

    # 3. Google Search
    intent_search = router.route("search python on google", SessionState.ACTIVE_SESSION)
    assert intent_search.intent_type == IntentType.SEARCH_GOOGLE
    mock_gateway.complete.assert_not_called()


# =============================================================================
# 4. ASSISTANT DISPATCH & ZERO ACTION EXECUTION TESTS
# =============================================================================

def test_assistant_speaks_conversational_response(mock_assistant, mock_gateway):
    """Assistant speaks model-generated voice_response through TTS on CONVERSATION intent."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    answer = "AI yaani Artificial Intelligence ek aisi technology hai jisse machines insaan ki tarah soch sakti hain."

    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content=json.dumps({
            "intent": "CONVERSATION",
            "voice_response": answer,
        }),
    )

    res = mock_assistant.process_utterance("explain artificial intelligence in simple words")

    assert res is True
    # Spoken through existing TTS
    mock_assistant.tts.speak.assert_called_once_with(answer)

    # ZERO action calls executed
    mock_assistant.app_launcher.launch.assert_not_called()


@patch("core.assistant.open_url_in_browser")
@patch("core.assistant.open_youtube")
@patch("core.assistant.open_google_search")
@patch("core.assistant.search_google")
@patch("core.assistant.search_youtube")
@patch("core.assistant.send_whatsapp_message_via_pywhatkit")
def test_conversation_executes_zero_external_actions(
    mock_wa_send, mock_yt_search, mock_g_search, mock_g_open, mock_yt_open, mock_browser_open,
    mock_assistant, mock_gateway
):
    """Verifies that CONVERSATION dispatch cannot invoke any browser, search, or WhatsApp actions."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)

    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content=json.dumps({
            "intent": "CONVERSATION",
            "voice_response": "Machine learning algorithms data se patterns seekhte hain.",
        }),
    )

    res = mock_assistant.process_utterance("what is machine learning")

    assert res is True
    mock_assistant.tts.speak.assert_called_once_with(
        "Machine learning algorithms data se patterns seekhte hain."
    )

    # Assert all action handlers were NOT called
    mock_assistant.app_launcher.launch.assert_not_called()
    mock_browser_open.assert_not_called()
    mock_yt_open.assert_not_called()
    mock_g_open.assert_not_called()
    mock_g_search.assert_not_called()
    mock_yt_search.assert_not_called()
    mock_wa_send.assert_not_called()


def test_natural_youtube_request_with_browser_null(mock_assistant, mock_gateway):
    """Natural command 'I want to watch YouTube' resolves OPEN_WEBSITE even if browser is 'null'."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)

    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content=json.dumps({
            "intent": "OPEN_WEBSITE",
            "website": "youtube",
            "browser": "null",  # String 'null' from LLM
            "voice_response": "Ji sir, main YouTube open kar rahi hu.",
        }),
    )

    with patch("core.assistant.open_youtube", return_value=(True, "YouTube open ho gaya.")) as mock_yt:
        res = mock_assistant.process_utterance("I want to watch YouTube")

        assert res is True
        mock_yt.assert_called_once_with(query="", browser_key=None)
        mock_assistant.tts.speak.assert_called_once_with("Ji sir, main YouTube open kar rahi hu.")


# =============================================================================
# 5. WHATSAPP CONFIRMATION SAFETY & GATEWAY BYPASS
# =============================================================================

def test_whatsapp_confirmation_state_bypasses_gateway(mock_assistant, mock_gateway):
    """When awaiting WhatsApp confirmation, gateway is 100% bypassed and CONVERSATION cannot interfere."""
    mock_assistant.state_machine.start_confirmation("rahul", "919876543210", "hello")
    assert mock_assistant.state_machine.current_state == SessionState.AWAITING_CONFIRMATION

    # Utterance during confirmation is routed locally
    res = mock_assistant.process_utterance("explain what is AI")
    assert res is True

    # Gateway must NOT be called
    mock_gateway.complete.assert_not_called()
    # Staged message remains intact
    assert mock_assistant.pending_whatsapp is not None


# =============================================================================
# 6. GATEWAY ERROR HANDLING & ROBUSTNESS
# =============================================================================

def test_gateway_error_during_conversation_falls_back_safely(mock_assistant, mock_gateway):
    """Gateway failure during conversational question produces safe error notice without crashing."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.TIMEOUT,
        error_message="Gateway request timed out.",
    )

    res = mock_assistant.process_utterance("tell me a fun fact")

    assert res is True
    mock_assistant.tts.speak.assert_called_once_with("AI gateway ka response time out ho gaya.")


def test_malformed_json_during_conversation_speaks_fallback(mock_assistant, mock_gateway):
    """Malformed gateway JSON output speaks generic misunderstanding fallback safely."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content="not a json at all",
    )

    res = mock_assistant.process_utterance("tell me a fun fact")

    assert res is True
    mock_assistant.tts.speak.assert_called_once_with("Maaf kijiye, mujhe yeh command samajh nahi aayi.")


def test_fixed_identity_response_remains_unchanged(mock_assistant, mock_gateway):
    """Fixed identity response ('who are you') remains identical and does not invoke gateway."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)

    mock_assistant.process_utterance("who are you")

    mock_gateway.complete.assert_not_called()
    mock_assistant.tts.speak.assert_called_once_with(FIXED_IDENTITY_RESPONSE)
