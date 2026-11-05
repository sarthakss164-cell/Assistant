"""
State machine module for Light AI V1.0.
Manages session lifecycle states: WAITING_FOR_ACTIVATION, ACTIVE_SESSION, AWAITING_CONFIRMATION, SHUTDOWN.
"""

from enum import Enum, auto
from typing import Optional, Dict, Any
from utils.logger import logger

class SessionState(Enum):
    WAITING_FOR_ACTIVATION = auto()
    ACTIVE_SESSION = auto()
    AWAITING_CONTACT_SELECTION = auto()
    AWAITING_CONFIRMATION = auto()
    SHUTDOWN = auto()

class SessionStateMachine:
    def __init__(self):
        self._state: SessionState = SessionState.WAITING_FOR_ACTIVATION
        self._pending_whatsapp: Optional[Dict[str, Any]] = None
        self._pending_disambiguation: Optional[Dict[str, Any]] = None

    @property
    def current_state(self) -> SessionState:
        return self._state

    @property
    def is_waiting_for_activation(self) -> bool:
        return self._state == SessionState.WAITING_FOR_ACTIVATION

    @property
    def is_active_session(self) -> bool:
        return self._state == SessionState.ACTIVE_SESSION

    @property
    def is_awaiting_contact_selection(self) -> bool:
        return self._state == SessionState.AWAITING_CONTACT_SELECTION

    @property
    def is_awaiting_confirmation(self) -> bool:
        return self._state == SessionState.AWAITING_CONFIRMATION

    @property
    def is_shutdown(self) -> bool:
        return self._state == SessionState.SHUTDOWN

    @property
    def pending_whatsapp(self) -> Optional[Dict[str, Any]]:
        return self._pending_whatsapp

    @pending_whatsapp.setter
    def pending_whatsapp(self, value: Optional[Dict[str, Any]]) -> None:
        if value is None:
            self._pending_whatsapp = None
        else:
            self._pending_whatsapp = dict(value)

    @property
    def pending_disambiguation(self) -> Optional[Dict[str, Any]]:
        return self._pending_disambiguation

    @pending_disambiguation.setter
    def pending_disambiguation(self, value: Optional[Dict[str, Any]]) -> None:
        if value is None:
            self._pending_disambiguation = None
        else:
            self._pending_disambiguation = dict(value)

    def activate_session(self):
        """Transitions from WAITING_FOR_ACTIVATION to ACTIVE_SESSION."""
        self._pending_whatsapp = None
        self._pending_disambiguation = None
        self._state = SessionState.ACTIVE_SESSION
        logger.info("[STATE] Session activated -> ACTIVE_SESSION")

    def start_contact_selection(self, query: str, candidates: list[str], initial_message: str = ""):
        """Enters AWAITING_CONTACT_SELECTION modal sub-state for WhatsApp contact disambiguation."""
        self._state = SessionState.AWAITING_CONTACT_SELECTION
        self._pending_disambiguation = {
            "query": query,
            "candidates": list(candidates),
            "initial_message": initial_message,
        }
        self._pending_whatsapp = None
        logger.info(f"[STATE] Entered AWAITING_CONTACT_SELECTION for query '{query}' ({len(candidates)} candidates)")

    def cancel_contact_selection(self):
        """Cancels contact disambiguation and returns to ACTIVE_SESSION."""
        self._pending_disambiguation = None
        self._state = SessionState.ACTIVE_SESSION
        logger.info("[STATE] Cancelled contact selection -> ACTIVE_SESSION")

    def complete_contact_selection(self) -> Optional[Dict[str, Any]]:
        """Completes contact disambiguation, returns disambiguation data, and clears pending disambiguation."""
        data = self._pending_disambiguation
        self._pending_disambiguation = None
        self._state = SessionState.ACTIVE_SESSION
        logger.info("[STATE] Completed contact selection -> ACTIVE_SESSION")
        return data

    def start_confirmation(self, contact: str, phone: str, message: str):
        """Enters AWAITING_CONFIRMATION modal sub-state for WhatsApp staging."""
        self._state = SessionState.AWAITING_CONFIRMATION
        self._pending_disambiguation = None
        self._pending_whatsapp = {
            "contact": contact,
            "phone": phone,
            "message": message
        }
        logger.info(f"[STATE] Entered AWAITING_CONFIRMATION for contact '{contact}'")

    def cancel_confirmation(self):
        """Cancels pending WhatsApp workflow and returns to ACTIVE_SESSION."""
        self._pending_whatsapp = None
        self._pending_disambiguation = None
        self._state = SessionState.ACTIVE_SESSION
        logger.info("[STATE] Cancelled WhatsApp workflow -> ACTIVE_SESSION")

    def confirm_and_complete(self):
        """Completes WhatsApp confirmation and returns to ACTIVE_SESSION."""
        self._pending_whatsapp = None
        self._pending_disambiguation = None
        self._state = SessionState.ACTIVE_SESSION
        logger.info("[STATE] Completed WhatsApp workflow -> ACTIVE_SESSION")

    def transition_to_shutdown(self):
        """Transitions state to SHUTDOWN and clears pending actions."""
        self._pending_whatsapp = None
        self._pending_disambiguation = None
        self._state = SessionState.SHUTDOWN
        logger.info("[STATE] Transitioned to SHUTDOWN")

    def transition_to(self, target_state: SessionState):
        """Transitions to the target SessionState."""
        if target_state == SessionState.ACTIVE_SESSION:
            self.activate_session()
        elif target_state == SessionState.SHUTDOWN:
            self.transition_to_shutdown()
        elif target_state == SessionState.WAITING_FOR_ACTIVATION:
            self.reset()
        else:
            self._state = target_state
            logger.info(f"[STATE] Transitioned -> {target_state.name}")

    def reset(self):
        """Resets state machine back to startup state."""
        self._pending_whatsapp = None
        self._pending_disambiguation = None
        self._state = SessionState.WAITING_FOR_ACTIVATION
        logger.info("[STATE] Reset state -> WAITING_FOR_ACTIVATION")

StateMachine = SessionStateMachine
