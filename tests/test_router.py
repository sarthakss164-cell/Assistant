"""
Unit tests for the command router and intent detection in Light AI V1.0.
"""

import unittest
from core.router import CommandRouter, IntentType
from core.state_machine import SessionStateMachine, SessionState

class TestCommandRouter(unittest.TestCase):

    def setUp(self):
        self.sm = SessionStateMachine()
        self.router = CommandRouter()

    def test_waiting_state_ignores_unprefixed_command(self):
        # In WAITING_FOR_ACTIVATION, unprefixed commands are ignored
        intent = self.router.route("open chrome", self.sm.current_state)
        self.assertEqual(intent.intent_type, IntentType.IGNORED)

    def test_waiting_state_ignores_exit_commands(self):
        # Unprefixed exit commands in WAITING_FOR_ACTIVATION must NOT shut down
        intent1 = self.router.route("exit", self.sm.current_state)
        self.assertEqual(intent1.intent_type, IntentType.IGNORED)

        intent2 = self.router.route("stop", self.sm.current_state)
        self.assertEqual(intent2.intent_type, IntentType.IGNORED)

        # Prefixed exit commands in WAITING_FOR_ACTIVATION must also NOT shut down
        intent3 = self.router.route("Light, exit", self.sm.current_state)
        self.assertEqual(intent3.intent_type, IntentType.IGNORED)

        intent4 = self.router.route("Light, stop", self.sm.current_state)
        self.assertEqual(intent4.intent_type, IntentType.IGNORED)

    def test_waiting_state_valid_command_activates(self):
        # Valid prefixed command triggers activation
        intent = self.router.route("Light, open Chrome", self.sm.current_state)
        self.assertEqual(intent.intent_type, IntentType.OPEN_APP)
        self.assertEqual(intent.payload.get("app_name"), "chrome")
        self.assertTrue(intent.should_activate_session)

    def test_waiting_state_unknown_prefixed_command(self):
        # Unknown prefixed command does NOT activate
        intent = self.router.route("Light, fly me to Mars", self.sm.current_state)
        self.assertEqual(intent.intent_type, IntentType.UNKNOWN)
        self.assertFalse(intent.should_activate_session)

    def test_active_session_unprefixed_commands(self):
        self.sm.activate_session()

        # App Launching
        intent1 = self.router.route("open Notepad", self.sm.current_state)
        self.assertEqual(intent1.intent_type, IntentType.OPEN_APP)
        self.assertEqual(intent1.payload.get("app_name"), "notepad")

        # Identity
        intent2 = self.router.route("who are you", self.sm.current_state)
        self.assertEqual(intent2.intent_type, IntentType.IDENTITY)

        # Google Search
        intent3 = self.router.route("search Python tutorials on Google", self.sm.current_state)
        self.assertEqual(intent3.intent_type, IntentType.SEARCH_GOOGLE)
        self.assertEqual(intent3.payload.get("query"), "python tutorials")

        # YouTube Search
        intent4 = self.router.route("play machine learning on YouTube", self.sm.current_state)
        self.assertEqual(intent4.intent_type, IntentType.SEARCH_YOUTUBE)
        self.assertEqual(intent4.payload.get("query"), "machine learning")

        # WhatsApp Start
        intent5 = self.router.route("send a WhatsApp message to Rahul", self.sm.current_state)
        self.assertEqual(intent5.intent_type, IntentType.WHATSAPP_START)
        self.assertEqual(intent5.payload.get("contact"), "rahul")

    def test_active_session_redundant_prefix(self):
        self.sm.activate_session()
        intent = self.router.route("Light, open Chrome", self.sm.current_state)
        self.assertEqual(intent.intent_type, IntentType.OPEN_APP)
        self.assertEqual(intent.payload.get("app_name"), "chrome")

    def test_identity_command_variations_active_session(self):
        """Verifies all approved identity speech recognition variations in active session."""
        self.sm.activate_session()
        variations = [
            "who are you",
            "who r you",
            "who are u",
            "who r u",
            "hu r u",
            "who are you?",
            "hu r u!",
            "WHO R YOU",
            "tum kaun ho",
            "aap kaun hai",
        ]
        for v in variations:
            intent = self.router.route(v, self.sm.current_state)
            self.assertEqual(
                intent.intent_type,
                IntentType.IDENTITY,
                f"Variation '{v}' failed to route to IDENTITY"
            )

    def test_identity_command_variations_activation_state(self):
        """Verifies identity variations with and without wake prefix before activation."""
        # Unprefixed before activation must be IGNORED
        for v in ["who are you", "who r you", "who are u", "who r u", "hu r u"]:
            intent = self.router.route(v, self.sm.current_state)
            self.assertEqual(intent.intent_type, IntentType.IGNORED)

        # Prefixed before activation must trigger IDENTITY and should_activate_session
        for v in ["who are you", "who r you", "who are u", "who r u", "hu r u"]:
            intent = self.router.route(f"Light, {v}", self.sm.current_state)
            self.assertEqual(intent.intent_type, IntentType.IDENTITY)
            self.assertTrue(intent.should_activate_session)

    def test_identity_unknown_commands_not_matched(self):
        """Verifies that non-identity phrases are not matched by IDENTITY_REGEX."""
        self.sm.activate_session()
        non_identity = [
            "how are you",
            "who are they",
            "where are you",
            "what are you",
            "who is this",
        ]
        for q in non_identity:
            intent = self.router.route(q, self.sm.current_state)
            self.assertEqual(
                intent.intent_type,
                IntentType.UNKNOWN,
                f"Phrase '{q}' should not match IDENTITY"
            )

    def test_explicit_user_requested_commands_in_active_session(self):
        """
        Explicit regression test for the commands specified by user:
        - Light, open Brave
        - Light, open Chrome
        - open YouTube
        - YouTube Python full course
        - YouTube Arijit Singh songs
        - YouTube light AI demo
        - open YouTube search Python tutorial
        - search latest AI
        - open WhatsApp
        - open WhatsApp Web
        - message Anand
        - send message to Anand
        """
        self.sm.activate_session()

        # Brave & Chrome commands
        intent_brave = self.router.route("Light, open Brave", self.sm.current_state)
        self.assertEqual(intent_brave.intent_type, IntentType.OPEN_APP)
        self.assertEqual(intent_brave.payload.get("app_name"), "brave")

        intent_chrome = self.router.route("Light, open Chrome", self.sm.current_state)
        self.assertEqual(intent_chrome.intent_type, IntentType.OPEN_APP)
        self.assertEqual(intent_chrome.payload.get("app_name"), "chrome")

        # YouTube commands
        intent_yt_open = self.router.route("open YouTube", self.sm.current_state)
        self.assertEqual(intent_yt_open.intent_type, IntentType.SEARCH_YOUTUBE)
        self.assertEqual(intent_yt_open.payload.get("query"), "")

        intent_yt_course = self.router.route("YouTube Python full course", self.sm.current_state)
        self.assertEqual(intent_yt_course.intent_type, IntentType.SEARCH_YOUTUBE)
        self.assertEqual(intent_yt_course.payload.get("query"), "python full course")

        intent_yt_songs = self.router.route("YouTube Arijit Singh songs", self.sm.current_state)
        self.assertEqual(intent_yt_songs.intent_type, IntentType.SEARCH_YOUTUBE)
        self.assertEqual(intent_yt_songs.payload.get("query"), "arijit singh songs")

        intent_yt_demo = self.router.route("YouTube light AI demo", self.sm.current_state)
        self.assertEqual(intent_yt_demo.intent_type, IntentType.SEARCH_YOUTUBE)
        self.assertEqual(intent_yt_demo.payload.get("query"), "light ai demo")

        intent_yt_search_cmd = self.router.route("open YouTube search Python tutorial", self.sm.current_state)
        self.assertEqual(intent_yt_search_cmd.intent_type, IntentType.SEARCH_YOUTUBE)
        self.assertEqual(intent_yt_search_cmd.payload.get("query"), "python tutorial")

        # Google Search commands
        intent_search = self.router.route("search latest AI", self.sm.current_state)
        self.assertEqual(intent_search.intent_type, IntentType.SEARCH_GOOGLE)
        self.assertEqual(intent_search.payload.get("query"), "latest ai")

        intent_search_for = self.router.route("search for quantum computing", self.sm.current_state)
        self.assertEqual(intent_search_for.intent_type, IntentType.SEARCH_GOOGLE)
        self.assertEqual(intent_search_for.payload.get("query"), "quantum computing")

        # WhatsApp Web open commands
        intent_wa = self.router.route("open WhatsApp", self.sm.current_state)
        self.assertEqual(intent_wa.intent_type, IntentType.OPEN_APP)
        self.assertEqual(intent_wa.payload.get("app_name"), "whatsapp")

        intent_wa_web = self.router.route("open WhatsApp Web", self.sm.current_state)
        self.assertEqual(intent_wa_web.intent_type, IntentType.OPEN_APP)
        self.assertEqual(intent_wa_web.payload.get("app_name"), "whatsapp")

        # WhatsApp message commands
        intent_msg_anand = self.router.route("message Anand", self.sm.current_state)
        self.assertEqual(intent_msg_anand.intent_type, IntentType.WHATSAPP_START)
        self.assertEqual(intent_msg_anand.payload.get("contact"), "anand")
        self.assertEqual(intent_msg_anand.payload.get("initial_message"), "")

        intent_send_msg_anand = self.router.route("send message to Anand", self.sm.current_state)
        self.assertEqual(intent_send_msg_anand.intent_type, IntentType.WHATSAPP_START)
        self.assertEqual(intent_send_msg_anand.payload.get("contact"), "anand")
        self.assertEqual(intent_send_msg_anand.payload.get("initial_message"), "")

        intent_msg_late = self.router.route("message Anand that I will be late", self.sm.current_state)
        self.assertEqual(intent_msg_late.intent_type, IntentType.WHATSAPP_START)
        self.assertEqual(intent_msg_late.payload.get("contact"), "anand")
        self.assertEqual(intent_msg_late.payload.get("initial_message"), "i will be late")

    def test_explicit_user_requested_commands_activation(self):
        """Verifies that user requested commands with 'Light' prefix activate from WAITING_FOR_ACTIVATION."""
        # 'Light, open Brave' activates
        intent1 = self.router.route("Light, open Brave", self.sm.current_state)
        self.assertEqual(intent1.intent_type, IntentType.OPEN_APP)
        self.assertEqual(intent1.payload.get("app_name"), "brave")
        self.assertTrue(intent1.should_activate_session)

        # 'Light, open Chrome' activates
        intent2 = self.router.route("Light, open Chrome", self.sm.current_state)
        self.assertEqual(intent2.intent_type, IntentType.OPEN_APP)
        self.assertEqual(intent2.payload.get("app_name"), "chrome")
        self.assertTrue(intent2.should_activate_session)

        # 'Light, YouTube Python full course' activates
        intent3 = self.router.route("Light, YouTube Python full course", self.sm.current_state)
        self.assertEqual(intent3.intent_type, IntentType.SEARCH_YOUTUBE)
        self.assertEqual(intent3.payload.get("query"), "python full course")
        self.assertTrue(intent3.should_activate_session)

        # 'Light, search latest AI' activates
        intent4 = self.router.route("Light, search latest AI", self.sm.current_state)
        self.assertEqual(intent4.intent_type, IntentType.SEARCH_GOOGLE)
        self.assertEqual(intent4.payload.get("query"), "latest ai")
        self.assertTrue(intent4.should_activate_session)

        # 'Light, message Anand' activates
        intent5 = self.router.route("Light, message Anand", self.sm.current_state)
        self.assertEqual(intent5.intent_type, IntentType.WHATSAPP_START)
        self.assertEqual(intent5.payload.get("contact"), "anand")
        self.assertTrue(intent5.should_activate_session)

        # 'Light, open Edge' activates
        intent6 = self.router.route("Light, open Edge", self.sm.current_state)
        self.assertEqual(intent6.intent_type, IntentType.OPEN_APP)
        self.assertEqual(intent6.payload.get("app_name"), "edge")
        self.assertTrue(intent6.should_activate_session)

    def test_confirmation_normalization_in_awaiting_state(self):
        """
        Verifies exact confirmation normalization in AWAITING_CONFIRMATION state:
        Affirmative: haan, han, haa, yes, yeah
        Negative: nahi, nahin, na, no, nope
        Unknown: arbitrary inputs do not confirm
        """
        state = SessionState.AWAITING_CONFIRMATION

        # Affirmative aliases
        for affirmative in ["haan", "han", "haa", "yes", "yeah", "ha", "yep", "han.", "yes!", "haan bhejo", "han bhejo"]:
            intent = self.router.route(affirmative, state)
            self.assertEqual(
                intent.intent_type,
                IntentType.CONFIRM_YES,
                f"Affirmative alias '{affirmative}' was not recognized as CONFIRM_YES"
            )

        # Negative aliases
        for negative in ["nahi", "nahin", "na", "no", "nope", "nahi.", "no!", "cancel", "cancel karo", "nahi cancel", "nahin cancel"]:
            intent = self.router.route(negative, state)
            self.assertEqual(
                intent.intent_type,
                IntentType.CONFIRM_NO,
                f"Negative alias '{negative}' was not recognized as CONFIRM_NO"
            )

        # Unknown / ambiguous confirmation
        for ambiguous in ["maybe", "okay", "sure", "tell me more", "what", "send it maybe"]:
            intent = self.router.route(ambiguous, state)
            self.assertEqual(
                intent.intent_type,
                IntentType.UNKNOWN,
                f"Ambiguous phrase '{ambiguous}' should be UNKNOWN in confirmation state"
            )

        # Standalone exit interrupts confirmation state
        for exit_cmd in ["exit", "stop", "terminate", "good bye"]:
            intent = self.router.route(exit_cmd, state)
            self.assertEqual(intent.intent_type, IntentType.EXIT)


if __name__ == "__main__":
    unittest.main()
