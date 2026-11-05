"""
Unit tests specifically validating the strict 4-command exit set,
standalone matching, substring immunity, and state-specific behavior.
"""

import unittest
from core.router import CommandRouter, IntentType
from core.state_machine import SessionStateMachine, SessionState

class TestExitCommands(unittest.TestCase):

    def setUp(self):
        self.sm = SessionStateMachine()
        self.router = CommandRouter()

    def test_four_approved_exit_commands_in_active_session(self):
        self.sm.activate_session()

        for phrase in ["exit", "stop", "terminate", "good bye"]:
            with self.subTest(phrase=phrase):
                intent = self.router.route(phrase, self.sm.current_state)
                self.assertEqual(intent.intent_type, IntentType.EXIT)

    def test_exit_command_case_and_punctuation_variations(self):
        self.sm.activate_session()

        variations = [
            "Exit", "EXIT", "exit.", "exit!",
            "STOP", "Stop.", "stop!",
            "Terminate", "TERMINATE.",
            "Good Bye", "GOOD BYE!", "good bye."
        ]
        for phrase in variations:
            with self.subTest(phrase=phrase):
                intent = self.router.route(phrase, self.sm.current_state)
                self.assertEqual(intent.intent_type, IntentType.EXIT)

    def test_goodbye_is_recognized_as_exit(self):
        # 'goodbye' (single word or with Light) is an approved exit command in Phase 7
        self.sm.activate_session()
        intent = self.router.route("goodbye", self.sm.current_state)
        self.assertEqual(intent.intent_type, IntentType.EXIT)

        intent2 = self.router.route("goodbye Light", self.sm.current_state)
        self.assertEqual(intent2.intent_type, IntentType.EXIT)

    def test_exit_substring_immunity_in_search_queries(self):
        self.sm.activate_session()

        # Phrases containing 'stop' inside search queries must remain search queries
        intent1 = self.router.route("search how to stop procrastinating on YouTube", self.sm.current_state)
        self.assertEqual(intent1.intent_type, IntentType.SEARCH_YOUTUBE)
        self.assertIn("stop", intent1.payload.get("query", ""))

        intent2 = self.router.route("search how to stop a car on Google", self.sm.current_state)
        self.assertEqual(intent2.intent_type, IntentType.SEARCH_GOOGLE)
        self.assertIn("stop", intent2.payload.get("query", ""))

        intent3 = self.router.route("google search terminate process command", self.sm.current_state)
        self.assertEqual(intent3.intent_type, IntentType.SEARCH_GOOGLE)
        self.assertIn("terminate", intent3.payload.get("query", ""))

    def test_exit_in_awaiting_confirmation_state(self):
        # In AWAITING_CONFIRMATION, an approved exit command triggers EXIT
        self.sm.activate_session()
        self.sm.start_confirmation("rahul", "919893371769", "hello")
        self.assertEqual(self.sm.current_state, SessionState.AWAITING_CONFIRMATION)

        intent = self.router.route("stop", self.sm.current_state)
        self.assertEqual(intent.intent_type, IntentType.EXIT)

        intent2 = self.router.route("exit.", self.sm.current_state)
        self.assertEqual(intent2.intent_type, IntentType.EXIT)

    def test_exit_words_in_waiting_for_activation_ignored(self):
        # In WAITING_FOR_ACTIVATION, exit words do NOT shut down the app
        for cmd in ["exit", "stop", "terminate", "good bye", "Light, exit", "Light, stop"]:
            with self.subTest(cmd=cmd):
                intent = self.router.route(cmd, SessionState.WAITING_FOR_ACTIVATION)
                self.assertNotEqual(intent.intent_type, IntentType.EXIT)
                self.assertEqual(intent.intent_type, IntentType.IGNORED)

if __name__ == "__main__":
    unittest.main()
