"""
Unit tests for session state machine in Light AI V1.0.
"""

import unittest
from core.state_machine import SessionStateMachine, SessionState

class TestStateMachine(unittest.TestCase):

    def setUp(self):
        self.sm = SessionStateMachine()

    def test_initial_state_is_waiting_for_activation(self):
        self.assertEqual(self.sm.current_state, SessionState.WAITING_FOR_ACTIVATION)
        self.assertTrue(self.sm.is_waiting_for_activation)
        self.assertFalse(self.sm.is_active_session)
        self.assertFalse(self.sm.is_awaiting_confirmation)

    def test_activate_session_transitions_to_active(self):
        self.sm.activate_session()
        self.assertEqual(self.sm.current_state, SessionState.ACTIVE_SESSION)
        self.assertTrue(self.sm.is_active_session)
        self.assertFalse(self.sm.is_waiting_for_activation)

    def test_whatsapp_confirmation_substate(self):
        self.sm.activate_session()
        self.sm.start_confirmation(contact="rahul", phone="919893371769", message="hello")
        self.assertEqual(self.sm.current_state, SessionState.AWAITING_CONFIRMATION)
        self.assertTrue(self.sm.is_awaiting_confirmation)
        self.assertIsNotNone(self.sm.pending_whatsapp)
        self.assertEqual(self.sm.pending_whatsapp["contact"], "rahul")

        # Cancel confirmation returns to ACTIVE_SESSION
        self.sm.cancel_confirmation()
        self.assertEqual(self.sm.current_state, SessionState.ACTIVE_SESSION)
        self.assertIsNone(self.sm.pending_whatsapp)

    def test_whatsapp_confirm_and_complete(self):
        self.sm.activate_session()
        self.sm.start_confirmation(contact="rahul", phone="919893371769", message="hello")
        self.sm.confirm_and_complete()
        self.assertEqual(self.sm.current_state, SessionState.ACTIVE_SESSION)
        self.assertIsNone(self.sm.pending_whatsapp)

    def test_reset_returns_to_waiting_for_activation(self):
        self.sm.activate_session()
        self.assertEqual(self.sm.current_state, SessionState.ACTIVE_SESSION)
        self.sm.reset()
        self.assertEqual(self.sm.current_state, SessionState.WAITING_FOR_ACTIVATION)
        self.assertTrue(self.sm.is_waiting_for_activation)

if __name__ == "__main__":
    unittest.main()
