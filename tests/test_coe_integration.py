"""
Integration tests for CoE AI Gateway client, local intent validator,
and LightAssistant orchestrator in Light AI V1.0 (Phase 4).

Strict testing constraints:
- 100% mocked; zero real gateway or network requests.
- Zero real API keys or credentials.
- All external actions mocked to verify zero execution on failures.
- Tests all 30 requirements specified in Section 9 of Phase 4 specification.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from core.assistant import LightAssistant
from core.router import CommandRouter, IntentType, CommandIntent
from core.state_machine import SessionState, StateMachine
from core.intent_validator import IntentValidator, ValidationResult
from core.coe_gateway import CoeGatewayClient, GatewayResponse, GatewayStatus
from config.settings import FIXED_IDENTITY_RESPONSE


@pytest.fixture
def mock_gateway():
    """Mock CoE Gateway client with is_configured=True by default."""
    client = MagicMock(spec=CoeGatewayClient)
    client.is_configured = True
    return client


@pytest.fixture
def mock_assistant(mock_gateway):
    """Initializes LightAssistant with mocked speech, launcher, and gateway client."""
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
# 1. DETERMINISTIC ROUTING PRIORITY (Tests 1 - 6)
# =============================================================================

def test_deterministic_app_command_does_not_call_gateway(mock_assistant, mock_gateway):
    """Test 1: Existing deterministic app command does not call gateway."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_assistant.app_launcher.launch.return_value = (True, "Notepad open kar rahi hoon.")

    res = mock_assistant.process_utterance("open Notepad")

    assert res is True
    mock_gateway.complete.assert_not_called()
    mock_assistant.app_launcher.launch.assert_called_once_with("notepad")
    mock_assistant.tts.speak.assert_called_once_with("Notepad open kar rahi hoon.")


def test_deterministic_browser_command_does_not_call_gateway(mock_assistant, mock_gateway):
    """Test 2: Existing deterministic browser command does not call gateway."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_assistant.app_launcher.launch.return_value = (True, "Google Chrome open kar rahi hoon.")

    res = mock_assistant.process_utterance("open Chrome")

    assert res is True
    mock_gateway.complete.assert_not_called()
    mock_assistant.app_launcher.launch.assert_called_once_with("chrome")


def test_deterministic_search_command_does_not_call_gateway(mock_assistant, mock_gateway):
    """Test 3: Existing deterministic search command does not call gateway."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)

    with patch("core.assistant.search_google", return_value=(True, "Search ok")) as mock_google:
        res1 = mock_assistant.process_utterance("search quantum computing on google")
        assert res1 is True
        mock_gateway.complete.assert_not_called()
        mock_google.assert_called_once_with("quantum computing")

    with patch("core.assistant.search_youtube", return_value=(True, "YouTube ok")) as mock_yt:
        res2 = mock_assistant.process_utterance("youtube python tutorial")
        assert res2 is True
        mock_gateway.complete.assert_not_called()
        mock_yt.assert_called_once_with("python tutorial")


def test_exit_command_does_not_call_gateway(mock_assistant, mock_gateway):
    """Test 4: Exit command does not call gateway and initiates local shutdown."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)

    with patch("core.assistant.graceful_shutdown") as mock_shutdown:
        res = mock_assistant.process_utterance("stop")

        assert res is False
        assert mock_assistant.state_machine.current_state == SessionState.SHUTDOWN
        mock_gateway.complete.assert_not_called()
        mock_shutdown.assert_called_once()


def test_deterministic_whatsapp_flow_does_not_call_gateway(mock_assistant, mock_gateway):
    """Test 5: Existing WhatsApp deterministic flow does not call gateway."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)

    with patch("core.assistant.resolve_contact_phone", return_value=("919893371769", None)):
        res = mock_assistant.process_utterance("message Anand that I will be late")

        assert res is True
        assert mock_assistant.state_machine.current_state == SessionState.AWAITING_CONFIRMATION
        mock_gateway.complete.assert_not_called()
        assert mock_assistant.pending_whatsapp == {
            "phone": "919893371769",
            "message": "i will be late",
            "contact": "anand",
        }


def test_unknown_command_invokes_gateway_exactly_once(mock_assistant, mock_gateway):
    """Test 6: Unknown command invokes gateway fallback exactly once."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_assistant.app_launcher.launch.return_value = (True, "VS Code open kar rahi hoon.")

    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content=json.dumps({"intent": "OPEN_APP", "app_name": "vscode"}),
    )

    res = mock_assistant.process_utterance("could you please launch vs code for me")

    assert res is True
    mock_gateway.complete.assert_called_once_with("could you please launch vs code for me")
    mock_assistant.app_launcher.launch.assert_called_once_with("vscode")


# =============================================================================
# 2. GATEWAY RESPONSE & VALIDATOR ENFORCEMENT (Tests 7 - 19)
# =============================================================================

def test_gateway_response_passes_through_validator(mock_assistant, mock_gateway):
    """Test 7: Successful valid response passes through validator."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    raw_json = json.dumps({"intent": "OPEN_APP", "app_name": "notepad"})
    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content=raw_json,
    )

    with patch.object(mock_assistant.router.validator, "validate", wraps=mock_assistant.router.validator.validate) as spy_validate:
        mock_assistant.process_utterance("kripya mera notepad shuru karein")
        spy_validate.assert_called_once_with(raw_json)


def test_validated_intent_enters_existing_dispatch_contract(mock_assistant, mock_gateway):
    """Test 8: Validated intent enters existing dispatch contract (e.g. OPEN_WEBSITE)."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content=json.dumps({"intent": "OPEN_WEBSITE", "website": "youtube", "browser": "chrome"}),
    )

    with patch("core.assistant.open_youtube", return_value=(True, "YouTube open kar rahi hoon.")) as mock_yt:
        mock_assistant.process_utterance("take me to the youtube site on chrome")
        mock_yt.assert_called_once_with(query="", browser_key="chrome")
        mock_assistant.tts.speak.assert_called_with("YouTube open kar rahi hoon.")


def test_malformed_json_produces_safe_fallback(mock_assistant, mock_gateway):
    """Test 9: Malformed JSON produces safe fallback with zero action calls."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content="This is plain text with {broken json",
    )

    res = mock_assistant.process_utterance("do something invalid")

    assert res is True
    mock_assistant.app_launcher.launch.assert_not_called()
    mock_assistant.tts.speak.assert_called_with("Maaf kijiye, mujhe yeh command samajh nahi aayi.")


def test_empty_gateway_response_produces_safe_fallback(mock_assistant, mock_gateway):
    """Test 10: Empty response produces safe fallback with zero action calls."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.EMPTY_RESPONSE,
        raw_content=None,
    )

    res = mock_assistant.process_utterance("unrecognized input")

    assert res is True
    mock_assistant.app_launcher.launch.assert_not_called()
    mock_assistant.tts.speak.assert_called_with("Maaf kijiye, mujhe yeh command samajh nahi aayi.")


def test_invalid_schema_produces_safe_fallback(mock_assistant, mock_gateway):
    """Test 11: Invalid schema (unexpected key) produces safe fallback with zero action calls."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content=json.dumps({"intent": "OPEN_APP", "app_name": "notepad", "unauthorized_key": "hacked"}),
    )

    res = mock_assistant.process_utterance("could you please run notepad with exploit")

    assert res is True
    mock_assistant.app_launcher.launch.assert_not_called()
    mock_assistant.tts.speak.assert_called_with("Maaf kijiye, mujhe yeh command samajh nahi aayi.")


def test_unsupported_intent_produces_safe_fallback(mock_assistant, mock_gateway):
    """Test 12: Unsupported intent produces safe fallback with zero action calls."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content=json.dumps({"intent": "DELETE_SYSTEM_FILES", "app_name": "notepad"}),
    )

    res = mock_assistant.process_utterance("delete everything")

    assert res is True
    mock_assistant.app_launcher.launch.assert_not_called()
    mock_assistant.tts.speak.assert_called_with("Maaf kijiye, mujhe yeh command samajh nahi aayi.")


def test_unknown_intent_produces_zero_action_calls(mock_assistant, mock_gateway):
    """Test 13: UNKNOWN intent from gateway produces zero action calls."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content=json.dumps({"intent": "UNKNOWN"}),
    )

    res = mock_assistant.process_utterance("gibberish blablabla")

    assert res is True
    mock_assistant.app_launcher.launch.assert_not_called()
    mock_assistant.tts.speak.assert_called_with("Maaf kijiye, mujhe yeh command samajh nahi aayi.")


def test_clarification_produces_zero_action_calls(mock_assistant, mock_gateway):
    """Test 14: CLARIFICATION produces zero action calls and speaks prompt."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content=json.dumps({
            "intent": "CLARIFICATION",
            "needs_clarification": True,
            "clarification_prompt": "Kya aap Google par search karna chahte hain?",
        }),
    )

    res = mock_assistant.process_utterance("i want to search something")

    assert res is True
    mock_assistant.app_launcher.launch.assert_not_called()
    mock_assistant.tts.speak.assert_called_with("Kya aap Google par search karna chahte hain?")


def test_gateway_timeout_produces_zero_action_calls(mock_assistant, mock_gateway):
    """Test 15: Gateway timeout produces zero action calls and speaks timeout notice."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.TIMEOUT,
        error_message="Request timed out after 10.0 seconds.",
    )

    res = mock_assistant.process_utterance("complex natural language request")

    assert res is True
    mock_assistant.app_launcher.launch.assert_not_called()
    mock_assistant.tts.speak.assert_called_with("AI gateway ka response time out ho gaya.")


def test_connection_error_produces_zero_action_calls(mock_assistant, mock_gateway):
    """Test 16: Connection error produces zero action calls and speaks connectivity notice."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.CONNECTION_FAILURE,
        error_message="Connection refused.",
    )

    res = mock_assistant.process_utterance("some command while offline")

    assert res is True
    mock_assistant.app_launcher.launch.assert_not_called()
    mock_assistant.tts.speak.assert_called_with("Internet ya gateway connectivity mein dikkat hai.")


def test_authentication_failure_produces_zero_action_calls(mock_assistant, mock_gateway):
    """Test 17: Authentication failure produces zero action calls and speaks auth notice."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.AUTHENTICATION_FAILURE,
        error_message="HTTP 401 Unauthorized.",
    )

    res = mock_assistant.process_utterance("some command with bad api key")

    assert res is True
    mock_assistant.app_launcher.launch.assert_not_called()
    mock_assistant.tts.speak.assert_called_with("AI gateway authentication fail ho gaya.")


def test_rate_limit_produces_zero_action_calls(mock_assistant, mock_gateway):
    """Test 18: Rate limit produces zero action calls and speaks busy notice."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.RATE_LIMIT,
        error_message="HTTP 429 Rate limited.",
    )

    res = mock_assistant.process_utterance("rapid repeated command")

    assert res is True
    mock_assistant.app_launcher.launch.assert_not_called()
    mock_assistant.tts.speak.assert_called_with("Gateway busy hai, kripya thodi der baad koshish karein.")


def test_api_error_produces_zero_action_calls(mock_assistant, mock_gateway):
    """Test 19: API error produces zero action calls and speaks fallback notice."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.API_ERROR,
        error_message="HTTP 500 Server error.",
    )

    res = mock_assistant.process_utterance("some command causing 500")

    assert res is True
    mock_assistant.app_launcher.launch.assert_not_called()
    mock_assistant.tts.speak.assert_called_with("Maaf kijiye, mujhe yeh command samajh nahi aayi.")


# =============================================================================
# 3. WHATSAPP SAFETY (Tests 20 - 25)
# =============================================================================

def test_gateway_cannot_send_whatsapp_directly(mock_assistant, mock_gateway):
    """Test 20: Gateway cannot send a WhatsApp message directly."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content=json.dumps({
            "intent": "WHATSAPP_START",
            "contact": "anand",
            "initial_message": "hello",
        }),
    )

    with patch("core.assistant.resolve_contact_phone", return_value=("919893371769", None)), \
         patch("core.assistant.send_whatsapp_message_via_pywhatkit") as mock_send:
        res = mock_assistant.process_utterance("bhai anand ko hello bol do")

        assert res is True
        mock_send.assert_not_called()
        assert mock_assistant.state_machine.current_state == SessionState.AWAITING_CONFIRMATION
        assert mock_assistant.pending_whatsapp is not None


def test_missing_contact_cannot_stage_message(mock_assistant, mock_gateway):
    """Test 21: Missing or unresolved contact cannot stage a WhatsApp message."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)

    # Case A: Model outputs WHATSAPP_START with unknown contact
    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content=json.dumps({
            "intent": "WHATSAPP_START",
            "contact": "nonexistent_person_123",
            "initial_message": "urgent work",
        }),
    )

    with patch("core.assistant.resolve_contact_phone", return_value=(None, "Contact nahi mila.")):
        res = mock_assistant.process_utterance("send message to nonexistent person")

        assert res is True
        assert mock_assistant.state_machine.current_state == SessionState.ACTIVE_SESSION
        assert mock_assistant.pending_whatsapp is None
        mock_assistant.tts.speak.assert_called_with("Maaf kijiye, 'nonexistent_person_123' contacts mein nahi mila.")


def test_valid_whatsapp_proposal_enters_staging_flow_only(mock_assistant, mock_gateway):
    """Test 22: Valid WhatsApp proposal enters staging flow and awaits user confirmation."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content=json.dumps({
            "intent": "WHATSAPP_START",
            "contact": "anand",
            "initial_message": "project ready",
        }),
    )

    with patch("core.assistant.resolve_contact_phone", return_value=("919893371769", None)), \
         patch("core.assistant.send_whatsapp_message_via_pywhatkit") as mock_send:
        res = mock_assistant.process_utterance("let anand know that project ready")

        assert res is True
        mock_send.assert_not_called()
        assert mock_assistant.state_machine.current_state == SessionState.AWAITING_CONFIRMATION
        assert mock_assistant.pending_whatsapp == {
            "phone": "919893371769",
            "message": "project ready",
            "contact": "anand",
        }
        mock_assistant.tts.speak.assert_called_with("Kya aap Anand ko 'project ready' bhejna chahte hain?")


def test_no_gateway_call_while_awaiting_confirmation(mock_assistant, mock_gateway):
    """Test 23: Gateway is 100% bypassed while awaiting WhatsApp confirmation."""
    mock_assistant.state_machine.start_confirmation("anand", "919893371769", "hello")
    mock_gateway.complete.reset_mock()

    # Utterances while awaiting confirmation must never reach gateway
    mock_assistant.process_utterance("maybe send it later")
    mock_assistant.process_utterance("who are you")
    mock_assistant.process_utterance("open chrome")

    mock_gateway.complete.assert_not_called()


def test_gateway_output_cannot_confirm_pending_message(mock_assistant, mock_gateway):
    """Test 24: Gateway output cannot confirm or send a pending WhatsApp message."""
    mock_assistant.state_machine.start_confirmation("anand", "919893371769", "hello")
    mock_gateway.complete.reset_mock()

    with patch("core.assistant.send_whatsapp_message_via_pywhatkit") as mock_send:
        # User says unconfirmed phrase
        mock_assistant.process_utterance("sure do it maybe")

        # Confirmation did NOT happen
        mock_send.assert_not_called()
        assert mock_assistant.state_machine.current_state == SessionState.AWAITING_CONFIRMATION
        mock_gateway.complete.assert_not_called()


def test_existing_deterministic_confirmation_remains_unchanged(mock_assistant, mock_gateway):
    """Test 25: Existing deterministic affirmative confirmation works without gateway."""
    mock_assistant.state_machine.start_confirmation("anand", "919893371769", "hello")
    mock_assistant.pending_whatsapp = {
        "phone": "919893371769",
        "message": "hello",
        "contact": "anand",
    }
    mock_gateway.complete.reset_mock()

    with patch("core.assistant.send_whatsapp_message_via_pywhatkit", return_value=(True, "Sent")) as mock_send:
        res = mock_assistant.process_utterance("haan")

        assert res is True
        mock_gateway.complete.assert_not_called()
        mock_send.assert_called_once_with("919893371769", "hello", "anand")
        assert mock_assistant.state_machine.current_state == SessionState.ACTIVE_SESSION
        assert mock_assistant.pending_whatsapp is None


# =============================================================================
# 4. LIFECYCLE AND REGRESSION (Tests 26 - 30)
# =============================================================================

def test_gateway_cannot_activate_assistant(mock_assistant, mock_gateway):
    """Test 26: Unprefixed or wake-word-only speech before activation does not call gateway and cannot activate assistant."""
    assert mock_assistant.state_machine.current_state == SessionState.WAITING_FOR_ACTIVATION

    # Unprefixed speech before activation must not call gateway or activate
    res1 = mock_assistant.process_utterance("teleport me home")
    assert res1 is True
    mock_gateway.complete.assert_not_called()
    assert mock_assistant.state_machine.current_state == SessionState.WAITING_FOR_ACTIVATION

    # Wake-word-only input must not call gateway or activate
    res2 = mock_assistant.process_utterance("Light")
    assert res2 is True
    mock_gateway.complete.assert_not_called()
    assert mock_assistant.state_machine.current_state == SessionState.WAITING_FOR_ACTIVATION


def test_gateway_cannot_execute_after_session_exit(mock_assistant, mock_gateway):
    """Test 27: Gateway cannot execute after session has shut down."""
    mock_assistant.state_machine.transition_to_shutdown()
    assert mock_assistant.state_machine.current_state == SessionState.SHUTDOWN

    res = mock_assistant.process_utterance("Light, open notepad")

    assert res is True
    mock_gateway.complete.assert_not_called()
    mock_assistant.app_launcher.launch.assert_not_called()


def test_identity_response_unchanged(mock_assistant, mock_gateway):
    """Test 28: Existing identity response is unchanged and spoken accurately."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)

    # 1. Deterministic identity
    mock_assistant.process_utterance("who are you")
    mock_assistant.tts.speak.assert_called_with(FIXED_IDENTITY_RESPONSE)
    assert FIXED_IDENTITY_RESPONSE == "Main Light AI hoon, jise mere Boss ne banaya hai."
    mock_gateway.complete.assert_not_called()

    # 2. Gateway-resolved identity
    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content=json.dumps({"intent": "IDENTITY"}),
    )
    mock_assistant.process_utterance("tell me who created you my friend")
    mock_assistant.tts.speak.assert_called_with(FIXED_IDENTITY_RESPONSE)


def test_gateway_not_configured_produces_safe_fallback(mock_assistant):
    """Test 29: Gateway client with is_configured=False skips calls and falls back safely."""
    unconfigured_client = MagicMock(spec=CoeGatewayClient)
    unconfigured_client.is_configured = False

    assistant = LightAssistant(
        listener=mock_assistant.listener,
        stt=mock_assistant.stt,
        tts=mock_assistant.tts,
        app_launcher=mock_assistant.app_launcher,
        gateway_client=unconfigured_client,
    )
    assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)

    res = assistant.process_utterance("unresolved command when gateway has no key")

    assert res is True
    unconfigured_client.complete.assert_not_called()
    assistant.tts.speak.assert_called_with("Maaf kijiye, mujhe yeh command samajh nahi aayi.")


def test_full_browser_and_search_integration_via_gateway(mock_assistant, mock_gateway):
    """Test 30: Google search and website launching with explicit browser via gateway."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)

    # Gateway returns SEARCH_GOOGLE with explicit browser
    mock_gateway.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content=json.dumps({"intent": "SEARCH_GOOGLE", "query": "deep learning", "browser": "edge"}),
    )

    with patch("core.assistant.open_google_search", return_value=(True, "Search ok")) as mock_search:
        mock_assistant.process_utterance("find deep learning on google using edge")
        mock_search.assert_called_once_with("deep learning", browser_key="edge")
