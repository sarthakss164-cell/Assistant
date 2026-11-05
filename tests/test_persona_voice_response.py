"""
Unit and integration tests for Phase 4.1: Persona & Voice Response Integration in Light AI V1.0.

Verifies:
1. Persona:
   - Gateway system prompt contains original V3.0 female persona rules.
   - Gateway prompt requires natural everyday Indian Hinglish and proper feminine Hindi grammar.
   - Gateway prompt includes creator context (Sarthak Sir).
   - Gateway prompt does not restore legacy unrestricted direct function calling.
2. Spoken Response (voice_response):
   - Valid voice_response is sanitized and extracted.
   - Model-generated voice_response reaches existing TTS path when action succeeds.
   - Missing, empty, or invalid type voice_response safely falls back to local deterministic messages.
   - Voice response cannot override action failures or safety error notices.
   - Voice response cannot make an invalid intent executable.
3. WhatsApp Safety:
   - Valid WhatsApp proposal with voice_response enters staging only.
   - Voice response cannot confirm or send WhatsApp messages.
   - Missing contact triggers local clarification safely.
4. Regression:
   - Deterministic commands do not call gateway.
   - Fixed identity response is unchanged.
   - Gateway errors produce safe local notices.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from core.coe_gateway import DEFAULT_SYSTEM_PROMPT, CoeGatewayClient, GatewayResponse, GatewayStatus
from core.intent_validator import IntentValidator, ValidationResult, MAX_VOICE_RESPONSE_LENGTH
from core.router import CommandRouter, IntentType, CommandIntent
from core.assistant import LightAssistant
from core.state_machine import SessionState
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
# 1. PERSONA INTEGRATION TESTS
# =============================================================================

def test_gateway_prompt_includes_female_persona_instructions():
    """Verifies that gateway system prompt explicitly defines Light AI as a FEMALE assistant."""
    assert "FEMALE desktop assistant" in DEFAULT_SYSTEM_PROMPT
    assert "ALWAYS speak as a FEMALE" in DEFAULT_SYSTEM_PROMPT


def test_gateway_prompt_includes_indian_hinglish_and_feminine_grammar():
    """Verifies that system prompt requires natural Indian Hinglish and feminine verb endings."""
    assert "natural, everyday Indian Hinglish" in DEFAULT_SYSTEM_PROMPT
    assert '"karungi"' in DEFAULT_SYSTEM_PROMPT
    assert '"bol rahi hu"' in DEFAULT_SYSTEM_PROMPT
    assert '"khol rahi hu"' in DEFAULT_SYSTEM_PROMPT
    assert '"kar sakti hu"' in DEFAULT_SYSTEM_PROMPT
    assert '"aayi hu"' in DEFAULT_SYSTEM_PROMPT

    # Prohibits masculine verb forms
    assert '"karunga"' in DEFAULT_SYSTEM_PROMPT
    assert '"bol raha hu"' in DEFAULT_SYSTEM_PROMPT
    assert '"khol raha hu"' in DEFAULT_SYSTEM_PROMPT
    assert '"kar sakta hu"' in DEFAULT_SYSTEM_PROMPT


def test_gateway_prompt_includes_creator_context():
    """Verifies that gateway system prompt attributes creation to Sarthak Sir."""
    assert "created by Sarthak Sir" in DEFAULT_SYSTEM_PROMPT


def test_gateway_prompt_does_not_restore_legacy_function_calling():
    """Verifies that gateway prompt does NOT restore legacy direct tool calling or functions."""
    assert "AVAILABLE FUNCTIONS:" not in DEFAULT_SYSTEM_PROMPT
    assert "send_whatsapp_message(" not in DEFAULT_SYSTEM_PROMPT
    assert "tool_call" not in DEFAULT_SYSTEM_PROMPT
    # Enforces structured intent schema
    assert '"intent":' in DEFAULT_SYSTEM_PROMPT
    assert '"voice_response":' in DEFAULT_SYSTEM_PROMPT


# =============================================================================
# 2. SPOKEN RESPONSE (voice_response) VALIDATION & DISPATCH TESTS
# =============================================================================

def test_valid_voice_response_extracted_and_validated(validator):
    """Verifies that a valid voice_response is extracted and sanitized."""
    res = validator.validate({
        "intent": "OPEN_APP",
        "app_name": "notepad",
        "voice_response": "Ji sir, main abhi Notepad open kar rahi hu.",
    })
    assert res.is_valid is True
    assert res.voice_response == "Ji sir, main abhi Notepad open kar rahi hu."


def test_voice_response_reaches_tts_path(mock_assistant, mock_gateway):
    """Verifies that model-generated voice_response reaches TTS on action success."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_assistant.app_launcher.launch.return_value = (True, "Notepad open kar rahi hoon.")

    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content=json.dumps({
            "intent": "OPEN_APP",
            "app_name": "notepad",
            "voice_response": "Ji sir, main abhi Notepad open kar rahi hu.",
        }),
    )

    res = mock_assistant.process_utterance("could you please open notepad for me")

    assert res is True
    mock_assistant.app_launcher.launch.assert_called_once_with("notepad")
    mock_assistant.tts.speak.assert_called_once_with("Ji sir, main abhi Notepad open kar rahi hu.")


def test_missing_voice_response_uses_safe_fallback(mock_assistant, mock_gateway):
    """Verifies that omitted voice_response safely falls back to local deterministic speech."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_assistant.app_launcher.launch.return_value = (True, "Notepad open kar rahi hoon.")

    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content=json.dumps({
            "intent": "OPEN_APP",
            "app_name": "notepad",
        }),
    )

    res = mock_assistant.process_utterance("could you please launch notepad")

    assert res is True
    mock_assistant.app_launcher.launch.assert_called_once_with("notepad")
    mock_assistant.tts.speak.assert_called_once_with("Notepad open kar rahi hoon.")


def test_empty_voice_response_uses_safe_fallback(mock_assistant, mock_gateway):
    """Verifies that empty or whitespace voice_response falls back to local speech."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_assistant.app_launcher.launch.return_value = (True, "VS Code open kar rahi hoon.")

    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content=json.dumps({
            "intent": "OPEN_APP",
            "app_name": "vscode",
            "voice_response": "   ",
        }),
    )

    res = mock_assistant.process_utterance("could you open vs code please")

    assert res is True
    mock_assistant.tts.speak.assert_called_once_with("VS Code open kar rahi hoon.")


def test_invalid_voice_response_type_uses_safe_fallback(validator, mock_assistant, mock_gateway):
    """Verifies that non-string voice_response (e.g. integer or array) falls back safely."""
    # Validator sets voice_response to None instead of crashing
    res = validator.validate({
        "intent": "OPEN_APP",
        "app_name": "chrome",
        "voice_response": 12345,
    })
    assert res.is_valid is True
    assert res.voice_response is None

    # Assistant falls back to local response
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_assistant.app_launcher.launch.return_value = (True, "Google Chrome open kar rahi hoon.")
    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content=json.dumps({
            "intent": "OPEN_APP",
            "app_name": "chrome",
            "voice_response": ["invalid", "list"],
        }),
    )

    mock_assistant.process_utterance("launch chrome browser please")
    mock_assistant.tts.speak.assert_called_once_with("Google Chrome open kar rahi hoon.")


def test_malformed_json_uses_safe_fallback(mock_assistant, mock_gateway):
    """Verifies that malformed JSON produces safe error notice without crashing."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content="not a json {voice_response: broken",
    )

    res = mock_assistant.process_utterance("some strange request")

    assert res is True
    mock_assistant.app_launcher.launch.assert_not_called()
    mock_assistant.tts.speak.assert_called_once_with("Maaf kijiye, mujhe yeh command samajh nahi aayi.")


def test_unauthorized_intent_fields_remain_rejected(validator):
    """Verifies that arbitrary unexpected keys are rejected even if voice_response is present."""
    res = validator.validate({
        "intent": "OPEN_APP",
        "app_name": "notepad",
        "voice_response": "Ji sir, main khol rahi hu.",
        "unauthorized_field": "exploit",
    })
    assert res.is_valid is False
    assert "Unexpected keys in input" in res.error_message


def test_invalid_intent_cannot_execute_even_if_voice_response_is_valid(mock_assistant, mock_gateway):
    """Verifies that an unsupported or malicious intent cannot execute despite a friendly voice_response."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content=json.dumps({
            "intent": "DELETE_SYSTEM_REGISTRY",
            "voice_response": "Ji sir, main abhi kar rahi hu.",
        }),
    )

    res = mock_assistant.process_utterance("please wipe the system")

    assert res is True
    mock_assistant.app_launcher.launch.assert_not_called()
    mock_assistant.tts.speak.assert_called_once_with("Maaf kijiye, mujhe yeh command samajh nahi aayi.")


def test_voice_response_cannot_choose_handler(mock_assistant, mock_gateway):
    """Verifies that voice_response text cannot trick the dispatcher into invoking handlers."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content=json.dumps({
            "intent": "SEARCH_GOOGLE",
            "query": "python tutorial",
            "voice_response": "Calling launch_app('notepad') now!",
        }),
    )

    with patch("core.assistant.search_google", return_value=(True, "Search ok")) as mock_google:
        mock_assistant.process_utterance("find python tutorial on google please")

        # Dispatches strictly according to intent enum, NOT voice_response text
        mock_google.assert_called_once_with("python tutorial")
        mock_assistant.app_launcher.launch.assert_not_called()


def test_voice_response_cannot_override_action_failure(mock_assistant, mock_gateway):
    """Verifies that if an action fails on Windows, local error notice is spoken instead of voice_response."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_assistant.app_launcher.launch.return_value = (False, "Maaf kijiye, Notepad aapke system par nahi mila.")

    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content=json.dumps({
            "intent": "OPEN_APP",
            "app_name": "notepad",
            "voice_response": "Ji sir, Notepad successfully khol diya hai!",
        }),
    )

    mock_assistant.process_utterance("could you open notepad please")

    # Must speak the local failure notice, NOT the model's false claim of success
    mock_assistant.tts.speak.assert_called_once_with("Maaf kijiye, Notepad aapke system par nahi mila.")


def test_voice_response_sanitization_bounds_length_and_strips_control_chars(validator):
    """Verifies that voice_response is length-bounded and stripped of dangerous characters."""
    dangerous_input = "Hello\x00\x1f <script>alert('xss')</script> `cmd` $PATH \\ " + ("word " * 100)
    cleaned = validator.sanitize_voice_response(dangerous_input)

    assert "\x00" not in cleaned
    assert "\x1f" not in cleaned
    assert "<" not in cleaned
    assert ">" not in cleaned
    assert "`" not in cleaned
    assert "$" not in cleaned
    assert "\\" not in cleaned
    assert len(cleaned) <= MAX_VOICE_RESPONSE_LENGTH


# =============================================================================
# 3. WHATSAPP SAFETY WITH SPOKEN RESPONSE
# =============================================================================

def test_whatsapp_voice_response_cannot_send_or_bypass_confirmation(mock_assistant, mock_gateway):
    """Verifies that WhatsApp proposal enters staging and speaks confirmation prompt, not sending."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content=json.dumps({
            "intent": "WHATSAPP_START",
            "contact": "anand",
            "initial_message": "meeting at 5",
            "voice_response": "Ji sir, main Anand ko message bhej chuki hu.",
        }),
    )

    with patch("core.assistant.resolve_contact_phone", return_value=("919893371769", None)), \
         patch("core.assistant.send_whatsapp_message_via_pywhatkit") as mock_send:

        res = mock_assistant.process_utterance("could you text anand that meeting at 5")

        assert res is True
        mock_send.assert_not_called()
        assert mock_assistant.state_machine.current_state == SessionState.AWAITING_CONFIRMATION
        assert mock_assistant.pending_whatsapp is not None
        # Confirmation prompt must be spoken to gate the action
        mock_assistant.tts.speak.assert_called_once_with("Kya aap Anand ko 'meeting at 5' bhejna chahte hain?")


def test_whatsapp_missing_contact_remains_safe(mock_assistant, mock_gateway):
    """Verifies that missing contact triggers local clarification and does not stage."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content=json.dumps({
            "intent": "WHATSAPP_START",
            "contact": None,
            "voice_response": "WhatsApp message bhej rahi hu.",
        }),
    )

    res = mock_assistant.process_utterance("send whatsapp message please")

    assert res is True
    assert mock_assistant.state_machine.current_state == SessionState.ACTIVE_SESSION
    assert mock_assistant.pending_whatsapp is None
    # Converted safely to clarification prompt
    mock_assistant.tts.speak.assert_called_once_with("Kise WhatsApp message bhejna hai?")


# =============================================================================
# 4. REGRESSION VERIFICATION
# =============================================================================

def test_deterministic_command_does_not_call_gateway_regression(mock_assistant, mock_gateway):
    """Verifies that deterministic commands continue to execute locally with 0 gateway calls."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_assistant.app_launcher.launch.return_value = (True, "Google Chrome open kar rahi hoon.")

    res = mock_assistant.process_utterance("open Chrome")

    assert res is True
    mock_gateway.complete.assert_not_called()
    mock_assistant.tts.speak.assert_called_once_with("Google Chrome open kar rahi hoon.")


def test_identity_response_remains_unchanged_regression(mock_assistant, mock_gateway):
    """Verifies that identity query continues to speak the exact approved fixed identity."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)

    mock_assistant.process_utterance("who are you")

    mock_gateway.complete.assert_not_called()
    mock_assistant.tts.speak.assert_called_once_with(FIXED_IDENTITY_RESPONSE)
    assert FIXED_IDENTITY_RESPONSE == "Main Light AI hoon, jise mere Boss ne banaya hai."


def test_gateway_error_remains_safe_regression(mock_assistant, mock_gateway):
    """Verifies that gateway timeout speaks local timeout notice with zero actions."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.TIMEOUT,
        error_message="Gateway timeout",
    )

    res = mock_assistant.process_utterance("complex natural language command")

    assert res is True
    mock_assistant.app_launcher.launch.assert_not_called()
    mock_assistant.tts.speak.assert_called_once_with("AI gateway ka response time out ho gaya.")
