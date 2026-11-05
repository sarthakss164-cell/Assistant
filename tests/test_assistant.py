"""
Integration tests for LightAssistant orchestrator.
Covers state transitions, wake-prefix activation, separate browser routing (Chrome, Brave, Edge),
exit command behaviors across states, feminine Hindi responses, and WhatsApp multi-turn confirmation (including 'han').
"""

import pytest
from unittest.mock import MagicMock, patch

from core.assistant import LightAssistant
from core.state_machine import SessionState
from core.router import IntentType
from config.settings import FIXED_IDENTITY_RESPONSE


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


def test_startup_in_waiting_for_activation(mock_assistant):
    """Verifies that assistant starts in WAITING_FOR_ACTIVATION state."""
    assert mock_assistant.state_machine.current_state == SessionState.WAITING_FOR_ACTIVATION


def test_unprefixed_command_ignored_in_waiting_state(mock_assistant):
    """Verifies that unprefixed commands are ignored before activation."""
    res = mock_assistant.process_utterance("open chrome")
    assert res is True
    assert mock_assistant.state_machine.current_state == SessionState.WAITING_FOR_ACTIVATION
    mock_assistant.tts.speak.assert_not_called()


def test_exit_command_ignored_before_activation(mock_assistant):
    """Verifies that exit commands (prefixed and unprefixed) are ignored before activation."""
    # Unprefixed exit
    res1 = mock_assistant.process_utterance("exit")
    assert res1 is True
    assert mock_assistant.state_machine.current_state == SessionState.WAITING_FOR_ACTIVATION

    # Prefixed exit before activation
    res2 = mock_assistant.process_utterance("light, stop")
    assert res2 is True
    assert mock_assistant.state_machine.current_state == SessionState.WAITING_FOR_ACTIVATION
    mock_assistant.tts.speak.assert_not_called()


def test_valid_prefixed_command_activates_session(mock_assistant):
    """Verifies that first valid prefixed command activates the session."""
    mock_assistant.app_launcher.launch.return_value = (True, "Google Chrome open kar rahi hoon.")

    res = mock_assistant.process_utterance("Light, open Chrome")
    assert res is True
    assert mock_assistant.state_machine.current_state == SessionState.ACTIVE_SESSION
    mock_assistant.app_launcher.launch.assert_called_once_with("chrome")
    mock_assistant.tts.speak.assert_called_once_with("Google Chrome open kar rahi hoon.")


def test_subsequent_commands_work_without_prefix(mock_assistant):
    """Verifies that once activated, commands do not require the 'Light' prefix."""
    # Step 1: Activate
    mock_assistant.process_utterance("Light, who are you?")
    assert mock_assistant.state_machine.current_state == SessionState.ACTIVE_SESSION
    mock_assistant.tts.speak.assert_called_with(FIXED_IDENTITY_RESPONSE)

    # Step 2: Unprefixed search command with feminine Hindi
    with patch("core.assistant.search_google", return_value=(True, "Google par 'python' search kar rahi hoon.")) as mock_google:
        mock_assistant.process_utterance("search python on google")
        mock_google.assert_called_once_with("python")
        mock_assistant.tts.speak.assert_called_with("Google par 'python' search kar rahi hoon.")


def test_identity_phonetic_variations_integration(mock_assistant):
    """Verifies that phonetic variations (hu r u, who r u, etc.) activate and speak approved identity."""
    # Step 1: Activation with 'Light, hu r u'
    res = mock_assistant.process_utterance("Light, hu r u")
    assert res is True
    assert mock_assistant.state_machine.current_state == SessionState.ACTIVE_SESSION
    mock_assistant.tts.speak.assert_called_with(FIXED_IDENTITY_RESPONSE)

    # Step 2: Unprefixed 'who r u' in active session
    res2 = mock_assistant.process_utterance("who r u")
    assert res2 is True
    mock_assistant.tts.speak.assert_called_with(FIXED_IDENTITY_RESPONSE)

    # Step 3: Unprefixed 'who are u' in active session
    res3 = mock_assistant.process_utterance("who are u")
    assert res3 is True
    mock_assistant.tts.speak.assert_called_with(FIXED_IDENTITY_RESPONSE)


@patch("core.assistant.graceful_shutdown")
def test_exit_command_in_active_session(mock_shutdown, mock_assistant):
    """Verifies that an approved exit command in ACTIVE_SESSION initiates shutdown."""
    # Activate
    mock_assistant.process_utterance("Light, who are you?")
    assert mock_assistant.state_machine.current_state == SessionState.ACTIVE_SESSION

    # Trigger exit
    res = mock_assistant.process_utterance("terminate")
    assert res is False
    assert mock_assistant.state_machine.current_state == SessionState.SHUTDOWN
    mock_shutdown.assert_called_once()


@patch("core.assistant.find_matching_contacts", return_value=["rahul"])
@patch("core.assistant.resolve_contact_phone", return_value=("919876543210", None))
@patch("core.assistant.send_whatsapp_message_via_pywhatkit", return_value=(True, "Rahul ke liye WhatsApp Web par message process shuru kar rahi hoon."))
def test_whatsapp_workflow_confirmation_yes(mock_send, mock_resolve, mock_find, mock_assistant):
    """Verifies WhatsApp workflow with positive confirmation and PyWhatKit invocation."""
    # Activate and start WhatsApp
    mock_assistant.process_utterance("Light, send a whatsapp message to rahul that I am on my way")
    assert mock_assistant.state_machine.current_state == SessionState.AWAITING_CONFIRMATION
    assert mock_assistant.pending_whatsapp == {
        "phone": "919876543210",
        "message": "i am on my way",
        "contact": "rahul",
    }
    mock_assistant.tts.speak.assert_called_with("Kya aap Rahul ko 'i am on my way' bhejna chahte hain?")

    # Confirm affirmatively with 'haan bhejo'
    res = mock_assistant.process_utterance("haan bhejo")
    assert res is True
    assert mock_assistant.state_machine.current_state == SessionState.ACTIVE_SESSION
    assert mock_assistant.pending_whatsapp is None
    mock_send.assert_called_once_with("919876543210", "i am on my way", "rahul")
    mock_assistant.tts.speak.assert_called_with("Rahul ke liye WhatsApp Web par message process shuru kar rahi hoon.")


@patch("core.assistant.find_matching_contacts", return_value=["rahul"])
@patch("core.assistant.resolve_contact_phone", return_value=("919876543210", None))
@patch("core.assistant.send_whatsapp_message_via_pywhatkit")
def test_whatsapp_workflow_confirmation_no(mock_send, mock_resolve, mock_find, mock_assistant):
    """Verifies WhatsApp workflow cancellation with negative confirmation."""
    # Activate and start WhatsApp
    mock_assistant.process_utterance("Light, whatsapp rahul that hello")
    assert mock_assistant.state_machine.current_state == SessionState.AWAITING_CONFIRMATION

    # Cancel
    res = mock_assistant.process_utterance("nahi cancel karo")
    assert res is True
    assert mock_assistant.state_machine.current_state == SessionState.ACTIVE_SESSION
    assert mock_assistant.pending_whatsapp is None
    mock_send.assert_not_called()
    mock_assistant.tts.speak.assert_called_with("WhatsApp message cancel kar diya gaya hai.")


@patch("core.assistant.find_matching_contacts", return_value=["rahul"])
@patch("core.assistant.resolve_contact_phone", return_value=("919876543210", None))
@patch("core.assistant.graceful_shutdown")
def test_exit_command_during_whatsapp_confirmation(mock_shutdown, mock_resolve, mock_find, mock_assistant):
    """Verifies that an exit command during confirmation cancels workflow and initiates shutdown."""
    mock_assistant.process_utterance("Light, whatsapp rahul that hello")
    assert mock_assistant.state_machine.current_state == SessionState.AWAITING_CONFIRMATION

    # Speak exit command
    res = mock_assistant.process_utterance("stop")
    assert res is False
    assert mock_assistant.state_machine.current_state == SessionState.SHUTDOWN
    assert mock_assistant.pending_whatsapp is None
    mock_shutdown.assert_called_once()


def test_command_debouncing(mock_assistant):
    """Verifies that identical consecutive commands within debounce window are ignored."""
    mock_assistant.process_utterance("Light, who are you?")
    assert mock_assistant.tts.speak.call_count == 1

    # Immediate identical command should be debounced
    mock_assistant.process_utterance("Light, who are you?")
    assert mock_assistant.tts.speak.call_count == 1


def test_e2e_separate_browser_routing_chrome_brave_edge(mock_assistant):
    """
    Verifies that 'open Chrome', 'open Brave', and 'open Edge' route independently
    without cross-redirection.
    """
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_assistant.app_launcher.launch.return_value = (True, "Open kar rahi hoon.")

    # 1. Open Chrome
    mock_assistant.process_utterance("open Chrome")
    mock_assistant.app_launcher.launch.assert_called_with("chrome")

    # 2. Open Brave
    mock_assistant.process_utterance("open Brave")
    mock_assistant.app_launcher.launch.assert_called_with("brave")

    # 3. Open Edge
    mock_assistant.process_utterance("open Edge")
    mock_assistant.app_launcher.launch.assert_called_with("edge")


@patch("core.assistant.search_youtube", return_value=(True, "YouTube open kar rahi hoon."))
def test_e2e_youtube_open_and_search(mock_yt, mock_assistant):
    """Verifies 'open YouTube' and 'YouTube Python full course' integration in active session."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)

    # Open YouTube homepage
    res1 = mock_assistant.process_utterance("open YouTube")
    assert res1 is True
    mock_yt.assert_called_with("")

    # YouTube search query
    mock_yt.return_value = (True, "YouTube par 'python full course' search kar rahi hoon.")
    res2 = mock_assistant.process_utterance("YouTube Python full course")
    assert res2 is True
    mock_yt.assert_called_with("python full course")


@patch("core.assistant.search_google", return_value=(True, "Google par 'latest ai' search kar rahi hoon."))
def test_e2e_search_latest_ai(mock_google, mock_assistant):
    """Verifies 'search latest AI' in active session."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)

    res = mock_assistant.process_utterance("search latest AI")
    assert res is True
    mock_google.assert_called_with("latest ai")
    mock_assistant.tts.speak.assert_called_with("Google par 'latest ai' search kar rahi hoon.")


def test_e2e_open_whatsapp_and_web(mock_assistant):
    """Verifies 'open WhatsApp' and 'open WhatsApp Web' launch WhatsApp Web in active session."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)
    mock_assistant.app_launcher.launch.return_value = (True, "WhatsApp Web open kar rahi hoon.")

    res1 = mock_assistant.process_utterance("open WhatsApp")
    assert res1 is True
    mock_assistant.app_launcher.launch.assert_called_with("whatsapp")

    res2 = mock_assistant.process_utterance("open WhatsApp Web")
    assert res2 is True
    mock_assistant.app_launcher.launch.assert_called_with("whatsapp")


@patch("core.assistant.resolve_contact_phone", return_value=("919893371769", None))
@patch("core.assistant.send_whatsapp_message_via_pywhatkit", return_value=(True, "Anand ke liye WhatsApp Web par message process shuru kar rahi hoon."))
def test_e2e_message_anand_workflow_with_han_confirmation(mock_send, mock_resolve, mock_assistant):
    """
    Verifies 'message Anand' prompts for missing message, asks confirmation,
    and accepts 'han' as affirmative confirmation.
    """
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)

    # Mock listener and STT returning message text when prompted
    mock_assistant.listener.listen.return_value = b"fake_audio"
    mock_assistant.stt.transcribe.return_value = (True, "hello Anand are you free?")

    # Issue command without message
    res = mock_assistant.process_utterance("message Anand")
    assert res is True
    assert mock_assistant.state_machine.current_state == SessionState.AWAITING_CONFIRMATION
    mock_assistant.tts.speak.assert_called_with("Kya aap Anand ko 'hello Anand are you free?' bhejna chahte hain?")

    # Confirm send with 'han' (the exact user log report!)
    res_confirm = mock_assistant.process_utterance("han")
    assert res_confirm is True
    assert mock_assistant.state_machine.current_state == SessionState.ACTIVE_SESSION
    mock_send.assert_called_once_with("919893371769", "hello Anand are you free?", "anand")


@patch("core.assistant.resolve_contact_phone", return_value=("919893371769", None))
@patch("core.assistant.send_whatsapp_message_via_pywhatkit")
def test_e2e_message_anand_workflow_with_nahin_cancellation(mock_send, mock_resolve, mock_assistant):
    """Verifies that 'nahin' properly cancels WhatsApp message workflow."""
    mock_assistant.state_machine.transition_to(SessionState.ACTIVE_SESSION)

    mock_assistant.listener.listen.return_value = b"fake_audio"
    mock_assistant.stt.transcribe.return_value = (True, "meeting postponed")

    res = mock_assistant.process_utterance("message Anand")
    assert res is True
    assert mock_assistant.state_machine.current_state == SessionState.AWAITING_CONFIRMATION

    # Cancel with 'nahin'
    res_cancel = mock_assistant.process_utterance("nahin")
    assert res_cancel is True
    assert mock_assistant.state_machine.current_state == SessionState.ACTIVE_SESSION
    assert mock_assistant.pending_whatsapp is None
    mock_send.assert_not_called()
    mock_assistant.tts.speak.assert_called_with("WhatsApp message cancel kar diya gaya hai.")
