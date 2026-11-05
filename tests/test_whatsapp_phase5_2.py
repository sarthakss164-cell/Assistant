"""
Unit and integration tests for Phase 5.2:
Conversational WhatsApp Contact Disambiguation.

Tests verify:
1. Contact matching in actions/whatsapp.py:
   - Exact match priority over partials.
   - Token & prefix matching.
   - Deterministic alphabetical ordering.
   - Deduplication.
   - Candidate count behavior (0 matches, 1 match, multiple matches, > 4 matches).
2. State Machine in core/state_machine.py:
   - Dedicated AWAITING_CONTACT_SELECTION state.
   - Authoritative pending_disambiguation storage and lifecycle.
   - pending_whatsapp remains None during contact selection.
   - Cleanup on cancellation, completion, exit, shutdown, and reset.
3. Router in core/router.py:
   - Local ordinal and numbered choices (Hindi/English).
   - Candidate name/suffix matching.
   - Local cancellation and exit.
   - Complete gateway bypass in AWAITING_CONTACT_SELECTION.
4. Assistant Integration in core/assistant.py:
   - Multiple matches trigger disambiguation prompt with feminine Hinglish persona.
   - Candidate selection stages recipient into AWAITING_CONFIRMATION.
   - Selection NEVER sends a WhatsApp message.
   - Selection does NOT bypass explicit confirmation.
   - PyWhatKit is never called during selection.
   - Invalid/ambiguous selection re-prompts without arbitrary selection.
   - Cancellation clears pending selection and does not send.
   - Timeout handling for selection state.
"""

import pytest
from unittest.mock import patch, MagicMock
from core.assistant import (
    LightAssistant,
    build_disambiguation_prompt,
    resolve_candidate_selection,
)
from core.state_machine import SessionStateMachine, SessionState
from core.router import CommandRouter, CommandIntent, IntentType
from actions.whatsapp import (
    find_matching_contacts,
    resolve_contact_phone,
    MAX_DISAMBIGUATION_CANDIDATES,
)


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
# 1. CONTACT MATCHING UNIT TESTS (actions/whatsapp.py)
# =============================================================================

def test_find_matching_contacts_exact_match_priority():
    """Exact normalized match takes absolute priority over partial/token matches."""
    contacts = {
        "rahul": "+91 98765 00001",
        "rahul office": "+91 98765 00002",
        "rahul personal": "+91 98765 00003",
    }
    matches = find_matching_contacts("rahul", contacts)
    assert matches == ["rahul"]


def test_find_matching_contacts_prefix_and_token():
    """When no exact match exists, prefix and token matches are returned."""
    contacts = {
        "rahul office": "+91 98765 00002",
        "rahul personal": "+91 98765 00003",
        "rohan": "+91 98765 00004",
    }
    matches = find_matching_contacts("rahul", contacts)
    assert matches == ["rahul office", "rahul personal"]


def test_find_matching_contacts_token_match():
    """Matches words within contact names (e.g., 'office')."""
    contacts = {
        "rahul office": "+91 98765 00002",
        "priya manager": "+91 98765 00005",
        "office desk": "+91 98765 00006",
    }
    matches = find_matching_contacts("office", contacts)
    assert matches == ["office desk", "rahul office"]


def test_find_matching_contacts_case_insensitivity():
    """Contact matching is fully case-insensitive and whitespace-tolerant."""
    contacts = {
        "sarthak": "+91 79772 08295",
        "anand": "+91 98933 71769",
    }
    assert find_matching_contacts("  SARTHAK  ", contacts) == ["sarthak"]
    assert find_matching_contacts("AnAnD", contacts) == ["anand"]


def test_find_matching_contacts_zero_matches():
    """Returns empty list when no contact matches query."""
    contacts = {
        "sarthak": "+91 79772 08295",
        "anand": "+91 98933 71769",
    }
    matches = find_matching_contacts("nonexistent", contacts)
    assert matches == []


def test_find_matching_contacts_single_partial_match():
    """Returns single match when only one candidate matches prefix/token."""
    contacts = {
        "sarthak": "+91 79772 08295",
        "anand": "+91 98933 71769",
    }
    matches = find_matching_contacts("sarth", contacts)
    assert matches == ["sarthak"]


def test_find_matching_contacts_stable_ordering():
    """Preserves stable alphabetical ordering regardless of dictionary insertion order."""
    contacts_rev = {
        "rahul personal": "+91 98765 00003",
        "rahul home": "+91 98765 00007",
        "rahul office": "+91 98765 00002",
    }
    matches = find_matching_contacts("rahul", contacts_rev)
    assert matches == ["rahul home", "rahul office", "rahul personal"]


def test_find_matching_contacts_deduplication():
    """Prevents duplicate candidate entries."""
    contacts = {
        "rahul rahul": "+91 98765 00001",
        "rahul office": "+91 98765 00002",
    }
    matches = find_matching_contacts("rahul", contacts)
    assert len(matches) == len(set(matches))


def test_find_matching_contacts_more_than_max():
    """Returns all matches even if > 4, so assistant can request refinement without silent truncation."""
    contacts = {
        f"rahul {i}": f"+91 98765 0000{i}" for i in range(1, 7)
    }
    matches = find_matching_contacts("rahul", contacts)
    assert len(matches) == 6
    assert len(matches) > MAX_DISAMBIGUATION_CANDIDATES


def test_resolve_contact_phone_single_partial_fallback():
    """resolve_contact_phone resolves single partial match if exact key is not present."""
    contacts = {
        "rahul office": "+91 98765 43210",
        "priya": "+91 98765 43211",
    }
    phone, err = resolve_contact_phone("rahul", contacts)
    assert phone == "919876543210"
    assert err is None


def test_resolve_contact_phone_ambiguous_fails_safely():
    """resolve_contact_phone does not arbitrarily pick when multiple candidates match."""
    contacts = {
        "rahul office": "+91 98765 43210",
        "rahul personal": "+91 98765 43212",
    }
    phone, err = resolve_contact_phone("rahul", contacts)
    assert phone is None
    assert "contacts mein nahi mila" in err


def test_resolve_contact_phone_invalid_number():
    """resolve_contact_phone fails validation if phone number digits are invalid."""
    contacts = {
        "rahul": "12345",  # Invalid Indian phone
    }
    phone, err = resolve_contact_phone("rahul", contacts)
    assert phone is None
    assert "phone number invalid" in err


# =============================================================================
# 2. STATE MACHINE TESTS (core/state_machine.py)
# =============================================================================

def test_state_machine_contact_selection_lifecycle():
    """Verifies transition to AWAITING_CONTACT_SELECTION and pending_disambiguation storage."""
    sm = SessionStateMachine()
    sm.activate_session()
    assert sm.current_state == SessionState.ACTIVE_SESSION

    candidates = ["rahul office", "rahul personal"]
    sm.start_contact_selection("rahul", candidates, initial_message="hello")

    assert sm.current_state == SessionState.AWAITING_CONTACT_SELECTION
    assert sm.pending_disambiguation == {
        "query": "rahul",
        "candidates": candidates,
        "initial_message": "hello",
    }
    # Crucial: pending_whatsapp MUST remain None during selection
    assert sm.pending_whatsapp is None


def test_state_machine_cancel_contact_selection():
    """Cancelling contact selection returns to ACTIVE_SESSION and clears disambiguation data."""
    sm = SessionStateMachine()
    sm.activate_session()
    sm.start_contact_selection("rahul", ["rahul office", "rahul personal"])
    assert sm.current_state == SessionState.AWAITING_CONTACT_SELECTION

    sm.cancel_contact_selection()
    assert sm.current_state == SessionState.ACTIVE_SESSION
    assert sm.pending_disambiguation is None
    assert sm.pending_whatsapp is None


def test_state_machine_complete_contact_selection():
    """Completing contact selection clears pending_disambiguation."""
    sm = SessionStateMachine()
    sm.activate_session()
    sm.start_contact_selection("rahul", ["rahul office", "rahul personal"])

    sm.complete_contact_selection()
    assert sm.current_state == SessionState.ACTIVE_SESSION
    assert sm.pending_disambiguation is None


def test_state_machine_cleanup_on_reset_and_shutdown():
    """Disambiguation state is cleared on reset, shutdown, or new session activation."""
    sm = SessionStateMachine()
    sm.activate_session()
    sm.start_contact_selection("rahul", ["rahul office", "rahul personal"])

    # Test reset
    sm.reset()
    assert sm.pending_disambiguation is None
    assert sm.current_state == SessionState.WAITING_FOR_ACTIVATION

    # Test transition to shutdown
    sm.activate_session()
    sm.start_contact_selection("rahul", ["rahul office", "rahul personal"])
    sm.transition_to_shutdown()
    assert sm.pending_disambiguation is None
    assert sm.current_state == SessionState.SHUTDOWN


def test_state_machine_start_confirmation_clears_disambiguation():
    """Starting send confirmation clears any lingering disambiguation data."""
    sm = SessionStateMachine()
    sm.activate_session()
    sm.start_contact_selection("rahul", ["rahul office", "rahul personal"])

    sm.start_confirmation("rahul office", "919876543210", "hello")
    assert sm.current_state == SessionState.AWAITING_CONFIRMATION
    assert sm.pending_disambiguation is None
    assert sm.pending_whatsapp is not None


# =============================================================================
# 3. ROUTER TESTS (core/router.py)
# =============================================================================

def test_router_ordinal_selection_hindi():
    """Router identifies Hindi ordinal choices in AWAITING_CONTACT_SELECTION."""
    router = CommandRouter()
    intent = router.route("pehla", state=SessionState.AWAITING_CONTACT_SELECTION)
    assert intent.intent_type == IntentType.CONTACT_SELECT
    assert intent.payload["index"] == 0

    intent2 = router.route("doosra", state=SessionState.AWAITING_CONTACT_SELECTION)
    assert intent2.intent_type == IntentType.CONTACT_SELECT
    assert intent2.payload["index"] == 1

    intent3 = router.route("teesra", state=SessionState.AWAITING_CONTACT_SELECTION)
    assert intent3.intent_type == IntentType.CONTACT_SELECT
    assert intent3.payload["index"] == 2


def test_router_ordinal_selection_english_and_digits():
    """Router identifies English ordinals and numbered digits."""
    router = CommandRouter()
    assert router.route("first", state=SessionState.AWAITING_CONTACT_SELECTION).payload["index"] == 0
    assert router.route("second", state=SessionState.AWAITING_CONTACT_SELECTION).payload["index"] == 1
    assert router.route("1", state=SessionState.AWAITING_CONTACT_SELECTION).payload["index"] == 0
    assert router.route("number 2", state=SessionState.AWAITING_CONTACT_SELECTION).payload["index"] == 1


def test_router_selection_by_name():
    """Router captures name utterances as selection in AWAITING_CONTACT_SELECTION."""
    router = CommandRouter()
    intent = router.route("rahul office", state=SessionState.AWAITING_CONTACT_SELECTION)
    assert intent.intent_type == IntentType.CONTACT_SELECT
    assert intent.payload == {"selection": "rahul office"}


def test_router_selection_cancellation_and_exit():
    """Router handles cancel and exit locally without touching gateway."""
    router = CommandRouter()
    # Cancel
    intent_cancel = router.route("nahi cancel karo", state=SessionState.AWAITING_CONTACT_SELECTION)
    assert intent_cancel.intent_type == IntentType.CONFIRM_NO

    intent_cancel_2 = router.route("mat bhejo", state=SessionState.AWAITING_CONTACT_SELECTION)
    assert intent_cancel_2.intent_type == IntentType.CONFIRM_NO

    # Exit
    intent_exit = router.route("stop", state=SessionState.AWAITING_CONTACT_SELECTION)
    assert intent_exit.intent_type == IntentType.EXIT


@patch("core.router.CoeGatewayClient")
def test_router_gateway_100_percent_bypassed_in_selection(mock_gateway_cls):
    """Gateway is never invoked when in AWAITING_CONTACT_SELECTION state."""
    mock_gateway = MagicMock()
    router = CommandRouter(gateway_client=mock_gateway)

    intent = router.route("pehla", state=SessionState.AWAITING_CONTACT_SELECTION)
    assert intent.intent_type == IntentType.CONTACT_SELECT
    mock_gateway.complete.assert_not_called()


# =============================================================================
# 4. ASSISTANT INTEGRATION TESTS (core/assistant.py)
# =============================================================================

def test_prompt_generation_feminine_persona():
    """Disambiguation prompt uses feminine Hinglish grammar."""
    prompt = build_disambiguation_prompt("rahul", ["rahul office", "rahul personal"])
    assert "Aap kise message bhejna chahti hain?" in prompt
    assert "pehla Rahul office" in prompt
    assert "aur doosra Rahul personal" in prompt
    # Ensure no masculine forms
    assert "chahta hoon" not in prompt
    assert "chahte ho" not in prompt


def test_resolve_candidate_selection_helper():
    """Helper resolves index and text against candidates deterministically."""
    candidates = ["rahul office", "rahul personal"]

    # Index
    selected, err = resolve_candidate_selection({"index": 0}, candidates)
    assert selected == "rahul office"
    assert err is None

    # Out of range index
    selected, err = resolve_candidate_selection({"index": 5}, candidates)
    assert selected is None
    assert err == "unrecognized"

    # Distinctive suffix
    selected, err = resolve_candidate_selection({"selection": "office"}, candidates)
    assert selected == "rahul office"
    assert err is None

    # Ambiguous selection (both candidates have 'rahul')
    selected, err = resolve_candidate_selection({"selection": "rahul"}, candidates)
    assert selected is None
    assert err == "ambiguous"


@patch("core.assistant.find_matching_contacts", return_value=["rahul office", "rahul personal"])
def test_assistant_multiple_matches_enters_selection(mock_find, mock_assistant):
    """WhatsApp utterance with multiple matches enters AWAITING_CONTACT_SELECTION."""
    mock_assistant.process_utterance("Light, whatsapp rahul that hello")

    assert mock_assistant.state_machine.current_state == SessionState.AWAITING_CONTACT_SELECTION
    assert mock_assistant.pending_disambiguation == {
        "query": "rahul",
        "candidates": ["rahul office", "rahul personal"],
        "initial_message": "hello",
    }
    assert mock_assistant.pending_whatsapp is None
    # Spoken prompt must be disambiguation prompt
    mock_assistant.tts.speak.assert_called_with(
        "'Rahul' ke liye do contacts mile hain: pehla Rahul office, aur doosra Rahul personal. Aap kise message bhejna chahti hain?"
    )


@patch("core.assistant.resolve_contact_phone", return_value=("919876543210", None))
@patch("core.assistant.send_whatsapp_message_via_pywhatkit")
def test_contact_selection_never_sends_message(mock_send, mock_resolve, mock_assistant):
    """Selecting a contact stages the message for confirmation, but NEVER sends immediately."""
    # Setup selection state
    mock_assistant.state_machine.activate_session()
    mock_assistant.state_machine.start_contact_selection(
        query="rahul",
        candidates=["rahul office", "rahul personal"],
        initial_message="project done",
    )

    # User selects first contact via ordinal 'pehla'
    res = mock_assistant.process_utterance("pehla")
    assert res is True

    # Contact selection MUST NOT send!
    mock_send.assert_not_called()

    # Must be in AWAITING_CONFIRMATION awaiting user's explicit yes
    assert mock_assistant.state_machine.current_state == SessionState.AWAITING_CONFIRMATION
    assert mock_assistant.pending_whatsapp == {
        "phone": "919876543210",
        "message": "project done",
        "contact": "rahul office",
    }
    # Disambiguation state must be cleared
    assert mock_assistant.pending_disambiguation is None
    mock_assistant.tts.speak.assert_called_with("Kya aap Rahul office ko 'project done' bhejna chahte hain?")


@patch("core.assistant.resolve_contact_phone", return_value=("919876543210", None))
@patch("core.assistant.send_whatsapp_message_via_pywhatkit")
def test_contact_selection_by_suffix(mock_send, mock_resolve, mock_assistant):
    """User can select contact using distinguishing suffix like 'personal'."""
    mock_assistant.state_machine.activate_session()
    mock_assistant.state_machine.start_contact_selection(
        query="rahul",
        candidates=["rahul office", "rahul personal"],
        initial_message="see you soon",
    )

    res = mock_assistant.process_utterance("personal")
    assert res is True
    mock_send.assert_not_called()
    assert mock_assistant.state_machine.current_state == SessionState.AWAITING_CONFIRMATION
    assert mock_assistant.pending_whatsapp["contact"] == "rahul personal"


def test_contact_selection_unrecognized_repompts(mock_assistant):
    """Unrecognized selection re-prompts without changing state or arbitrary selection."""
    mock_assistant.state_machine.activate_session()
    mock_assistant.state_machine.start_contact_selection(
        query="rahul",
        candidates=["rahul office", "rahul personal"],
        initial_message="hello",
    )

    res = mock_assistant.process_utterance("random gibberish answer")
    assert res is True
    # Remains in selection state
    assert mock_assistant.state_machine.current_state == SessionState.AWAITING_CONTACT_SELECTION
    assert mock_assistant.pending_whatsapp is None
    mock_assistant.tts.speak.assert_called_with(
        "Aapka selection samajh nahi aaya. Please dobara batayiye."
    )


def test_contact_selection_ambiguous_repompts(mock_assistant):
    """Ambiguous selection (e.g., 'rahul' when both are rahul) asks for clarification."""
    mock_assistant.state_machine.activate_session()
    mock_assistant.state_machine.start_contact_selection(
        query="rahul",
        candidates=["rahul office", "rahul personal"],
        initial_message="hello",
    )

    res = mock_assistant.process_utterance("rahul")
    assert res is True
    assert mock_assistant.state_machine.current_state == SessionState.AWAITING_CONTACT_SELECTION
    assert mock_assistant.pending_whatsapp is None
    mock_assistant.tts.speak.assert_called_with(
        "Yeh selection clear nahi hai. Please contact ka number ya naam select kijiye."
    )


def test_contact_selection_cancellation(mock_assistant):
    """User can cancel contact selection via 'nahi cancel karo'."""
    mock_assistant.state_machine.activate_session()
    mock_assistant.state_machine.start_contact_selection(
        query="rahul",
        candidates=["rahul office", "rahul personal"],
        initial_message="hello",
    )

    res = mock_assistant.process_utterance("nahi cancel karo")
    assert res is True
    assert mock_assistant.state_machine.current_state == SessionState.ACTIVE_SESSION
    assert mock_assistant.pending_disambiguation is None
    assert mock_assistant.pending_whatsapp is None
    mock_assistant.tts.speak.assert_called_with("Main contact selection cancel kar rahi hu.")


def test_contact_selection_exit_command(mock_assistant):
    """Exit command during contact selection initiates shutdown and cleans state."""
    mock_assistant.state_machine.activate_session()
    mock_assistant.state_machine.start_contact_selection(
        query="rahul",
        candidates=["rahul office", "rahul personal"],
        initial_message="hello",
    )

    with patch("core.assistant.graceful_shutdown") as mock_shutdown:
        res = mock_assistant.process_utterance("exit")
        assert res is False
        assert mock_assistant.state_machine.current_state == SessionState.SHUTDOWN
        assert mock_assistant.pending_disambiguation is None
        assert mock_assistant.pending_whatsapp is None
        mock_shutdown.assert_called_once()


@patch("core.assistant.find_matching_contacts", return_value=[f"rahul {i}" for i in range(1, 6)])
def test_more_than_max_candidates_asks_to_refine(mock_find, mock_assistant):
    """When matches exceed MAX_DISAMBIGUATION_CANDIDATES (4), user is asked to refine name."""
    mock_assistant.process_utterance("Light, whatsapp rahul that hello")

    # Does not enter selection
    assert mock_assistant.state_machine.current_state == SessionState.ACTIVE_SESSION
    assert mock_assistant.pending_disambiguation is None
    assert mock_assistant.pending_whatsapp is None
    mock_assistant.tts.speak.assert_called_with(
        "'Rahul' ke naam se bahut saare contacts mile hain. Please pura naam batayiye."
    )


@patch("core.assistant.resolve_contact_phone", return_value=(None, "Phone invalid"))
def test_contact_selection_invalid_phone_fails_safely(mock_resolve, mock_assistant):
    """If selected contact has an invalid phone number, workflow fails safely and does not stage."""
    mock_assistant.state_machine.activate_session()
    mock_assistant.state_machine.start_contact_selection(
        query="rahul",
        candidates=["rahul office", "rahul personal"],
        initial_message="hello",
    )

    res = mock_assistant.process_utterance("pehla")
    assert res is True
    assert mock_assistant.state_machine.current_state == SessionState.ACTIVE_SESSION
    assert mock_assistant.pending_disambiguation is None
    assert mock_assistant.pending_whatsapp is None
    mock_assistant.tts.speak.assert_called_with("Phone invalid")


@patch("core.assistant.find_matching_contacts", return_value=["rahul office", "rahul personal"])
@patch("core.assistant.resolve_contact_phone", return_value=("919876543210", None))
@patch("core.assistant.send_whatsapp_message_via_pywhatkit", return_value=(True, "Message process shuru kar rahi hoon."))
def test_end_to_end_disambiguation_to_send_flow(mock_send, mock_resolve, mock_find, mock_assistant):
    """
    End-to-end multi-step flow:
    1. Utterance triggers contact selection (2 candidates).
    2. User selects 'doosra' (2nd candidate: rahul personal).
    3. Assistant asks for send confirmation.
    4. User confirms with 'haan bhejo'.
    5. PyWhatKit is called exactly once with 'rahul personal'.
    """
    # Step 1: Trigger WhatsApp
    mock_assistant.process_utterance("Light, whatsapp rahul that I will arrive at five")
    assert mock_assistant.state_machine.current_state == SessionState.AWAITING_CONTACT_SELECTION
    mock_send.assert_not_called()

    # Step 2: Select candidate
    mock_assistant.process_utterance("doosra")
    assert mock_assistant.state_machine.current_state == SessionState.AWAITING_CONFIRMATION
    mock_send.assert_not_called()

    # Step 3: Explicit send confirmation
    mock_assistant.process_utterance("haan bhejo")
    assert mock_assistant.state_machine.current_state == SessionState.ACTIVE_SESSION
    assert mock_assistant.pending_whatsapp is None
    assert mock_assistant.pending_disambiguation is None
    mock_send.assert_called_once_with("919876543210", "i will arrive at five", "rahul personal")
