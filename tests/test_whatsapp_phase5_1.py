"""
Unit and integration tests for Phase 5.1:
State Synchronization & WhatsApp Send-Status Handling.

Tests verify:
1. Pending WhatsApp state has one authoritative owner in SessionStateMachine.
2. Property delegation between LightAssistant and SessionStateMachine.
3. Pending state is cleared on cancellation, completion, exit, and timeout.
4. Pending state cannot be reused across requests.
5. PyWhatKit contract handling (success, explicit failure, exceptions, uncertain outcomes).
6. No automatic retry on uncertain or failed outcomes.
7. No false delivery claims.
8. Sending strictly gated behind explicit confirmation.
9. Gateway bypass during confirmation.
"""

import pytest
from unittest.mock import patch, MagicMock
from core.assistant import LightAssistant
from core.state_machine import SessionStateMachine, SessionState
from core.router import CommandRouter, CommandIntent, IntentType
from actions.whatsapp import send_whatsapp_message_via_pywhatkit


@pytest.fixture
def mock_assistant():
    listener = MagicMock()
    stt = MagicMock()
    tts = MagicMock()
    launcher = MagicMock()

    assistant = LightAssistant(
        listener=listener,
        stt=stt,
        tts=tts,
        app_launcher=launcher,
    )
    return assistant


# =============================================================================
# 1. STATE SYNCHRONIZATION AND OWNER AUTHORITY TESTS
# =============================================================================

def test_authoritative_pending_state_sync(mock_assistant):
    """Test 1: Assistant pending_whatsapp property delegates directly to StateMachine."""
    # Initially None
    assert mock_assistant.pending_whatsapp is None
    assert mock_assistant.state_machine.pending_whatsapp is None

    # Setting on assistant updates state machine
    mock_assistant.pending_whatsapp = {
        "contact": "anand",
        "phone": "919893371769",
        "message": "hello anand",
    }
    assert mock_assistant.state_machine.pending_whatsapp == {
        "contact": "anand",
        "phone": "919893371769",
        "message": "hello anand",
    }
    assert mock_assistant.pending_whatsapp["contact"] == "anand"

    # Setting on state machine updates assistant
    mock_assistant.state_machine.start_confirmation("rahul", "919876543210", "on my way")
    assert mock_assistant.pending_whatsapp == {
        "contact": "rahul",
        "phone": "919876543210",
        "message": "on my way",
    }

    # Setting None clears both
    mock_assistant.pending_whatsapp = None
    assert mock_assistant.pending_whatsapp is None
    assert mock_assistant.state_machine.pending_whatsapp is None


def test_pending_state_cleared_after_cancellation(mock_assistant):
    """Test 2: Negative confirmation clears pending state on both assistant and state machine."""
    mock_assistant.state_machine.start_confirmation("anand", "919893371769", "test message")
    assert mock_assistant.state_machine.is_awaiting_confirmation
    assert mock_assistant.pending_whatsapp is not None

    res = mock_assistant.process_utterance("nahi")
    assert res is True
    assert mock_assistant.state_machine.current_state == SessionState.ACTIVE_SESSION
    assert mock_assistant.pending_whatsapp is None
    assert mock_assistant.state_machine.pending_whatsapp is None
    mock_assistant.tts.speak.assert_called_with("WhatsApp message cancel kar diya gaya hai.")


def test_pending_state_cleared_after_successful_completion(mock_assistant):
    """Test 3: Affirmative confirmation and successful send clears pending state."""
    mock_assistant.state_machine.start_confirmation("anand", "919893371769", "test message")

    with patch("core.assistant.send_whatsapp_message_via_pywhatkit", return_value=(True, "Success status")) as mock_send:
        res = mock_assistant.process_utterance("haan")
        assert res is True
        mock_send.assert_called_once_with("919893371769", "test message", "anand")
        assert mock_assistant.state_machine.current_state == SessionState.ACTIVE_SESSION
        assert mock_assistant.pending_whatsapp is None
        assert mock_assistant.state_machine.pending_whatsapp is None


def test_pending_state_cleared_after_send_failure(mock_assistant):
    """Test 4: Failed send also clears pending state so stale data cannot linger."""
    mock_assistant.state_machine.start_confirmation("anand", "919893371769", "test message")

    with patch("core.assistant.send_whatsapp_message_via_pywhatkit", return_value=(False, "Failed send")):
        res = mock_assistant.process_utterance("bhejo")
        assert res is True
        assert mock_assistant.state_machine.current_state == SessionState.ACTIVE_SESSION
        assert mock_assistant.pending_whatsapp is None
        assert mock_assistant.state_machine.pending_whatsapp is None


def test_pending_state_not_reused_on_subsequent_request(mock_assistant):
    """Test 5: Once cleared, subsequent commands cannot reuse old pending message data."""
    mock_assistant.state_machine.start_confirmation("anand", "919893371769", "hello")
    mock_assistant.state_machine.cancel_confirmation()

    # Now in active session with no pending message
    assert mock_assistant.pending_whatsapp is None

    # An affirmative utterance in active session does not trigger a WhatsApp send
    with patch("core.assistant.send_whatsapp_message_via_pywhatkit") as mock_send:
        mock_assistant.process_utterance("haan")
        mock_send.assert_not_called()
        assert mock_assistant.pending_whatsapp is None


# =============================================================================
# 2. PYWHATKIT SEND-RESULT CONTRACT HANDLING TESTS
# =============================================================================

def test_pywhatkit_success_contract_handling(mock_assistant):
    """Test 6: Successful PyWhatKit initiation speaks status honestly without claiming delivery."""
    mock_assistant.state_machine.start_confirmation("rahul", "919876543210", "meeting at 4")

    honest_msg = "Rahul ke liye WhatsApp Web par message process shuru kar rahi hoon. Kripya ensure karein ki WhatsApp Web logged in hai."
    with patch("core.assistant.send_whatsapp_message_via_pywhatkit", return_value=(True, honest_msg)) as mock_send:
        res = mock_assistant.process_utterance("haan bhejo")
        assert res is True
        mock_send.assert_called_once_with("919876543210", "meeting at 4", "rahul")
        # Final spoken message matches the honest status
        mock_assistant.tts.speak.assert_called_with(honest_msg)
        # Ensure no false delivery claim
        assert "delivered" not in honest_msg.lower()
        assert "pahunch gaya" not in honest_msg.lower()


def test_pywhatkit_explicit_failure_handling(mock_assistant):
    """Test 7: Explicit failure from PyWhatKit reports failure honestly and does not retry."""
    mock_assistant.state_machine.start_confirmation("rahul", "919876543210", "meeting at 4")

    fail_msg = "WhatsApp message bhejne mein dikkat aayi: Connection timeout. Kripya check karein ki WhatsApp Web authenticated hai."
    with patch("core.assistant.send_whatsapp_message_via_pywhatkit", return_value=(False, fail_msg)) as mock_send:
        res = mock_assistant.process_utterance("yes send")
        assert res is True
        mock_send.assert_called_once()  # Strictly NO retry
        mock_assistant.tts.speak.assert_called_with(fail_msg)
        assert mock_assistant.state_machine.current_state == SessionState.ACTIVE_SESSION
        assert mock_assistant.pending_whatsapp is None


def test_pywhatkit_exception_handling(mock_assistant):
    """Test 8: Unexpected exception during PyWhatKit send is caught safely without crashing."""
    mock_assistant.state_machine.start_confirmation("anand", "919893371769", "hello")

    with patch("core.assistant.send_whatsapp_message_via_pywhatkit", side_effect=RuntimeError("PyAutoGUI window focus error")) as mock_send:
        res = mock_assistant.process_utterance("haan")
        assert res is True
        mock_send.assert_called_once()
        # TTS spoke an error message explaining the failure
        last_call_arg = mock_assistant.tts.speak.call_args[0][0]
        assert "dikkat aayi" in last_call_arg
        assert "PyAutoGUI" in last_call_arg
        assert mock_assistant.state_machine.current_state == SessionState.ACTIVE_SESSION
        assert mock_assistant.pending_whatsapp is None


def test_pywhatkit_uncertain_outcome_no_retry(mock_assistant):
    """Test 9: Uncertain or ambiguous outcome reports status could not be confirmed, no retry."""
    mock_assistant.state_machine.start_confirmation("anand", "919893371769", "hello")

    # Ambiguous non-boolean return
    with patch("core.assistant.send_whatsapp_message_via_pywhatkit", return_value=(None, "Uncertain status")) as mock_send:
        res = mock_assistant.process_utterance("haan")
        assert res is True
        mock_send.assert_called_once()  # Strictly 1 call, zero retry
        mock_assistant.tts.speak.assert_called_with("Anand ke WhatsApp message ka status confirm nahi ho paya.")
        assert mock_assistant.pending_whatsapp is None

    # Malformed non-tuple return
    mock_assistant.state_machine.start_confirmation("anand", "919893371769", "hello")
    with patch("core.assistant.send_whatsapp_message_via_pywhatkit", return_value="unexpected string") as mock_send:
        res = mock_assistant.process_utterance("yes")
        assert res is True
        mock_send.assert_called_once()
        mock_assistant.tts.speak.assert_called_with("Anand ke WhatsApp message ka status confirm nahi ho paya.")
        assert mock_assistant.pending_whatsapp is None


# =============================================================================
# 3. SAFETY AND GATEWAY ISOLATION TESTS
# =============================================================================

def test_send_strictly_gated_behind_explicit_confirmation(mock_assistant):
    """Test 10: PyWhatKit is never invoked before affirmative confirmation."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)

    with patch("core.assistant.resolve_contact_phone", return_value=("919893371769", None)), \
         patch("core.assistant.send_whatsapp_message_via_pywhatkit") as mock_send:

        # Step 1: User requests WhatsApp message
        mock_assistant.process_utterance("message anand that reaching soon")
        assert mock_assistant.state_machine.is_awaiting_confirmation
        mock_send.assert_not_called()

        # Step 2: User says something ambiguous / unrelated
        mock_assistant.process_utterance("maybe later")
        mock_send.assert_not_called()
        assert mock_assistant.state_machine.is_awaiting_confirmation

        # Step 3: Explicit confirmation triggers exactly one send
        mock_assistant.process_utterance("haan")
        mock_send.assert_called_once_with("919893371769", "reaching soon", "anand")
        assert mock_assistant.state_machine.is_active_session


def test_gateway_model_cannot_confirm_or_send(mock_assistant):
    """Test 11: In AWAITING_CONFIRMATION, gateway client is bypassed; model cannot confirm."""
    mock_assistant.state_machine.start_confirmation("anand", "919893371769", "secret msg")

    # Mock gateway client that would attempt to confirm
    mock_gateway = MagicMock()
    mock_assistant.router.gateway_client = mock_gateway

    with patch("core.assistant.send_whatsapp_message_via_pywhatkit") as mock_send:
        # User says phrase that does not match affirmative regex
        mock_assistant.process_utterance("I think so please send it")

        # Gateway was not called
        mock_gateway.complete.assert_not_called()
        # Message was not sent
        mock_send.assert_not_called()
        # Still in confirmation sub-state
        assert mock_assistant.state_machine.is_awaiting_confirmation
        assert mock_assistant.pending_whatsapp is not None


def test_exit_command_during_confirmation_clears_pending_state(mock_assistant):
    """Test 12: Exit command during confirmation cleanly shuts down and cancels staging."""
    mock_assistant.state_machine.start_confirmation("rahul", "919876543210", "hello")

    with patch("core.assistant.send_whatsapp_message_via_pywhatkit") as mock_send, \
         patch("core.assistant.graceful_shutdown"):
        res = mock_assistant.process_utterance("stop")
        assert res is False
        assert mock_assistant.state_machine.is_shutdown
        assert mock_assistant.pending_whatsapp is None
        mock_send.assert_not_called()
