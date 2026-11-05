"""
Unit and integration tests for Multi-Prompt Parser and Queue Admission in LIGHT AI V1.0.
Verifies boundary detection, lookahead splitting, preservation of internal clauses/commas,
leading wake-word handling, atomic all-or-nothing queue admission, WhatsApp confirmation
isolation within compound utterances, thread safety, and backward compatibility.
All tests use mocks; no real hardware, live microphone, or external network calls are initiated.
"""

import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import speech_recognition as sr

from core.prompt_parser import split_multi_prompt
from core.assistant import LightAssistant
from core.state_machine import SessionState
from core.router import IntentType, CommandIntent, CommandRouter
from core.coe_gateway import GatewayResponse, GatewayStatus


class TestMultiPromptParser(unittest.TestCase):
    """Unit tests for split_multi_prompt function in core/prompt_parser.py."""

    def test_1_mixed_commands_and_questions_in_one_utterance(self):
        """Mixed commands and questions are cleanly split in original sequence."""
        text = "Light, open Chrome, what is Artificial Intelligence, open YouTube, who are you, open WhatsApp."
        segments = split_multi_prompt(text)
        expected = [
            "open Chrome",
            "what is Artificial Intelligence",
            "open YouTube",
            "who are you",
            "open WhatsApp",
        ]
        self.assertEqual(segments, expected)

    def test_2_strict_segment_order_preserved(self):
        """Original order of segments is strictly preserved."""
        text = "open Chrome and what is AI and open YouTube and who are you"
        segments = split_multi_prompt(text)
        self.assertEqual(len(segments), 4)
        self.assertTrue(segments[0].lower().startswith("open chrome"))
        self.assertTrue(segments[1].lower().startswith("what is ai"))
        self.assertTrue(segments[2].lower().startswith("open youtube"))
        self.assertTrue(segments[3].lower().startswith("who are you"))

    def test_3_internal_commas_and_conjunctions_in_questions_preserved(self):
        """Questions with internal lists, commas, or 'and' must not be fragmented."""
        # Case A: List of items inside question
        q1 = "What is the difference between supervised, unsupervised, and reinforcement learning?"
        segments1 = split_multi_prompt(q1)
        self.assertEqual(len(segments1), 1)
        self.assertEqual(segments1[0], q1)

        # Case B: Compound question clause
        q2 = "What is the speed of light, and how is it measured?"
        segments2 = split_multi_prompt(q2)
        self.assertEqual(len(segments2), 1)
        self.assertEqual(segments2[0], q2)

        # Case C: Hindi question with internal comma
        q3 = "Kripya batayein, artificial intelligence kya hai aur yeh kaise kaam karta hai?"
        segments3 = split_multi_prompt(q3)
        self.assertEqual(len(segments3), 1)
        self.assertEqual(segments3[0], q3)

    def test_4_leading_wake_word_removal_and_preservation_of_light_elsewhere(self):
        """Leading wake word is stripped, but occurrences of 'light' inside text are preserved."""
        # Case A: Leading wake word before question containing 'light'
        text1 = "Light, what is the speed of light?"
        segments1 = split_multi_prompt(text1)
        self.assertEqual(len(segments1), 1)
        self.assertEqual(segments1[0], "what is the speed of light?")

        # Case B: Leading wake word before command
        text2 = "Light open Chrome"
        segments2 = split_multi_prompt(text2)
        self.assertEqual(segments2, ["open Chrome"])

        # Case C: Wake word in Devanagari or lowercase
        text3 = "लाइट, open Notepad"
        segments3 = split_multi_prompt(text3)
        self.assertEqual(segments3, ["open Notepad"])

        # Case D: Text without wake word containing 'light' remains untouched
        text4 = "tell me about light waves"
        segments4 = split_multi_prompt(text4)
        self.assertEqual(segments4, ["tell me about light waves"])

    def test_5_single_prompt_backward_compatibility(self):
        """A normal single-prompt utterance returns a 1-item list with intact text."""
        prompts = [
            "open Chrome",
            "what is AI?",
            "who are you",
            "play zaalima song",
            "message Anand that I will be late",
            "exit",
        ]
        for p in prompts:
            with self.subTest(prompt=p):
                res = split_multi_prompt(p)
                self.assertEqual(len(res), 1)
                self.assertEqual(res[0], p)

    def test_6_hinglish_and_conjunction_lookahead_boundaries(self):
        """Splits at Hinglish conjunctions (aur, phir) only when followed by command/question starters."""
        text = "Light open Chrome aur YouTube kholo phir batao AI kya hai"
        segments = split_multi_prompt(text)
        self.assertEqual(len(segments), 3)
        self.assertEqual(segments[0], "open Chrome")
        self.assertEqual(segments[1], "open YouTube")
        self.assertEqual(segments[2], "batao AI kya hai")

    def test_6b_plain_speech_recognition_transcription_boundaries(self):
        """
        Regression tests for real speech recognition transcriptions without punctuation:
        - Words are separated only by single spaces
        - Commands and questions must be cleanly split at grammar boundaries
        """
        # Case A: open Chrome who are you
        t1 = "light open Chrome who are you"
        s1 = split_multi_prompt(t1)
        self.assertEqual(s1, ["open Chrome", "who are you"])

        # Case B: open Brave what is artificial intelligence who are you open YouTube
        t2 = "light open Brave what is artificial intelligence who are you open YouTube"
        s2 = split_multi_prompt(t2)
        self.assertEqual(
            s2,
            [
                "open Brave",
                "what is artificial intelligence",
                "who are you",
                "open YouTube",
            ],
        )

        # Case C: open Chrome what is AI open YouTube
        t3 = "light open Chrome what is AI open YouTube"
        s3 = split_multi_prompt(t3)
        self.assertEqual(s3, ["open Chrome", "what is AI", "open YouTube"])

        # Case D: Question followed by Action command
        t4 = "Light what is AI open YouTube"
        s4 = split_multi_prompt(t4)
        self.assertEqual(s4, ["what is AI", "open YouTube"])

    def test_6c_plain_speech_recognition_false_split_prevention(self):
        """
        Ensures questions containing words like 'open', 'how to', or dangling prepositions
        are NOT falsely fragmented into incomplete phrases or unintended action launches.
        """
        # Case A: 'how to open a bank account' -> 'a bank account' is not an app, 'how to' is dangling
        q1 = "how to open a bank account"
        self.assertEqual(split_multi_prompt(q1), [q1])

        # Case B: 'tell me how to open Chrome' -> 'tell me how to' ends with dangling 'to'
        q2 = "tell me how to open Chrome"
        self.assertEqual(split_multi_prompt(q2), [q2])

        # Case C: 'explain what is artificial intelligence' -> complete single query
        q3 = "explain what is artificial intelligence"
        self.assertEqual(split_multi_prompt(q3), [q3])


class TestMultiPromptAssistantIntegration(unittest.TestCase):
    """Integration tests for Multi-Prompt enqueueing and atomic admission in LightAssistant."""

    def setUp(self):
        self.mock_launcher = MagicMock()
        self.mock_launcher.launch.return_value = (True, "Launched")
        self.mock_tts = MagicMock()
        self.mock_tts.speak.return_value = True
        self.mock_gateway = MagicMock()
        self.mock_gateway.complete.return_value = GatewayResponse(
            status=GatewayStatus.SUCCESS,
            raw_content='{"intent": "CONVERSATION", "voice_response": "AI is artificial intelligence."}',
        )

        self.assistant = LightAssistant(
            app_launcher=self.mock_launcher,
            tts=self.mock_tts,
            gateway_client=self.mock_gateway,
        )

    def tearDown(self):
        if hasattr(self, "assistant"):
            self.assistant._shutdown_internal(farewell_message="")

    def test_7_atomic_all_or_nothing_queue_admission(self):
        """If a compound utterance cannot fit entirely in the queue, none of its segments are enqueued."""
        # Hold worker on blocking task
        worker_started = threading.Event()
        worker_blocker = threading.Event()

        def blocking_action(*args, **kwargs):
            worker_started.set()
            worker_blocker.wait(timeout=2.0)
            return True, "Done"

        self.mock_launcher.launch.side_effect = blocking_action
        self.assistant.state_machine.activate_session()

        # Enqueue item 1 (worker will pick up and block)
        self.assistant.enqueue_utterance("open Chrome")
        self.assertTrue(worker_started.wait(timeout=2.0))

        # Enqueue 8 more items -> queue size = 8 (total capacity = 10)
        for i in range(8):
            ok = self.assistant.enqueue_utterance(f"who are you? {i}")
            self.assertTrue(ok)

        self.assertEqual(self.assistant.queue_depth, 8)

        # Free slots = 10 - 8 = 2 slots remaining.
        # Now submit a compound utterance with 3 segments:
        compound = "open Notepad, what is AI, open Brave"
        ok_compound = self.assistant.enqueue_utterance(compound)

        # All-or-nothing: It requires 3 slots, but only 2 are available -> REJECT ALL
        self.assertFalse(ok_compound)

        # Queue depth must still be exactly 8 (no partial admission or overwriting)
        self.assertEqual(self.assistant.queue_depth, 8)

        # Spoken warning triggered
        spoken_calls = [c[0][0] for c in self.mock_tts.speak.call_args_list]
        self.assertTrue(any("queue full" in s.lower() for s in spoken_calls))

        # Now submit a compound utterance with 2 segments -> fits exactly!
        ok_fits = self.assistant.enqueue_utterance("open Notepad, who are you")
        self.assertTrue(ok_fits)
        self.assertEqual(self.assistant.queue_depth, 10)

        # Cleanup
        worker_blocker.set()
        self.assertTrue(self.assistant.wait_for_queue_idle(timeout=5.0))

    def test_8_whatsapp_confirmation_cannot_be_satisfied_from_same_compound_utterance(self):
        """A confirmation token ('haan') in the same compound utterance cannot authorize a staged message."""
        self.assistant.state_machine.activate_session()

        with patch("core.assistant.find_matching_contacts", return_value=["anand"]), \
             patch("core.assistant.resolve_contact_phone", return_value=("919876543210", None)), \
             patch("core.assistant.stage_whatsapp_message", return_value=True), \
             patch("core.assistant.send_whatsapp_message_via_pywhatkit", return_value=(True, "Sent")) as mock_send:

            # User speaks compound utterance: stage message AND says 'haan' in the same breath
            compound = "message Anand that I will be late, haan"
            self.assistant.enqueue_utterance(compound)

            # Wait for processing
            self.assertTrue(self.assistant.wait_for_queue_idle(timeout=5.0))

            # The message must NOT have been sent! State machine must be AWAITING_CONFIRMATION!
            mock_send.assert_not_called()
            self.assertEqual(self.assistant.state_machine.current_state, SessionState.AWAITING_CONFIRMATION)

            # A subsequent, separate utterance with 'haan' is required to confirm
            self.assistant.enqueue_utterance("haan")
            self.assertTrue(self.assistant.wait_for_queue_idle(timeout=5.0))

            # Now send must be called!
            mock_send.assert_called_once()
            self.assertEqual(self.assistant.state_machine.current_state, SessionState.ACTIVE_SESSION)

    def test_9_music_mode_ptt_multi_prompt_wake_word_enforcement(self):
        """PTT capture requires 'Light' wake word and safely enqueues multiple segments."""
        mock_stt = MagicMock()
        mock_audio = MagicMock(spec=sr.AudioData)
        self.assistant.stt = mock_stt

        # 1. PTT compound speech WITHOUT 'Light' is rejected
        mock_stt.transcribe.return_value = (True, "open Chrome, what is AI")
        self.assistant._process_ptt_audio(mock_audio)
        self.assertEqual(self.assistant.queue_depth, 0)

        # 2. PTT compound speech WITH 'Light' is accepted and split into queue
        mock_stt.transcribe.return_value = (True, "Light, open Chrome, what is AI")
        self.assistant._process_ptt_audio(mock_audio)
        self.assertTrue(self.assistant.wait_for_queue_idle(timeout=5.0))

        # Both actions/responses must have been executed
        self.mock_launcher.launch.assert_called_once_with("chrome")
        spoken_calls = [c[0][0] for c in self.mock_tts.speak.call_args_list]
        self.assertTrue(any("artificial intelligence" in s.lower() for s in spoken_calls))

    def test_10_unknown_or_ambiguous_segments_safe_handling(self):
        """Unknown segments inside multi-prompt do not trigger unintended actions and do not block others."""
        self.assistant.state_machine.activate_session()

        # req1 is open Chrome, req2 is unknown gibberish, req3 is who are you
        self.mock_gateway.complete.return_value = GatewayResponse(
            status=GatewayStatus.SUCCESS,
            raw_content='{"intent": "UNKNOWN", "voice_response": null}',
        )

        compound = "Light, open Chrome, asdkjasdklj random gibberish, who are you"
        ok = self.assistant.enqueue_utterance(compound)
        self.assertTrue(ok)

        self.assertTrue(self.assistant.wait_for_queue_idle(timeout=5.0))

        # Chrome was launched
        self.mock_launcher.launch.assert_called_once_with("chrome")

        # Identity response was spoken
        spoken = [c[0][0] for c in self.mock_tts.speak.call_args_list]
        self.assertTrue(any("light ai hoon" in s.lower() or "boss" in s.lower() for s in spoken))

    def test_11_thread_safe_concurrent_admissions(self):
        """Multiple threads submitting compound utterances concurrently respect atomic capacity limit."""
        self.assistant.state_machine.activate_session()

        # Fast mock to hold queue briefly
        barrier = threading.Barrier(4)
        results = []

        def submit(text):
            barrier.wait()
            res = self.assistant.enqueue_utterance(text)
            results.append(res)

        threads = [
            threading.Thread(target=submit, args=(f"open Chrome, what is AI {i}",))
            for i in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Total enqueued should never exceed queue capacity of 10
        self.assertLessEqual(self.assistant.queue_depth, 10)
        self.assertTrue(self.assistant.wait_for_queue_idle(timeout=5.0))

    def test_12_plain_speech_recognition_two_part_utterance_execution(self):
        """
        Regression Test: 'light open Chrome who are you'
        Verifies end-to-end runtime path from transcription to queue and execution:
        - Segments cleanly into 'open Chrome' and 'who are you'
        - 'chrome' is launched (never 'chrome who are you')
        - Identity query is processed and answered
        - Session transitions from WAITING_FOR_ACTIVATION to ACTIVE_SESSION
        """
        self.assertEqual(self.assistant.state_machine.current_state, SessionState.WAITING_FOR_ACTIVATION)

        utterance = "light open Chrome who are you"
        ok = self.assistant.enqueue_utterance(utterance)
        self.assertTrue(ok)

        # Wait for all requests in queue to finish processing
        self.assertTrue(self.assistant.wait_for_queue_idle(timeout=5.0))

        # 1. Verify app launcher was called with EXACTLY 'chrome'
        self.mock_launcher.launch.assert_called_once_with("chrome")

        # 2. Verify launcher was NEVER called with a combined string
        for call_args in self.mock_launcher.launch.call_args_list:
            app_arg = call_args[0][0]
            self.assertNotIn("who are you", app_arg.lower())

        # 3. Verify identity response was spoken
        spoken_calls = [c[0][0] for c in self.mock_tts.speak.call_args_list]
        self.assertTrue(any("light ai hoon" in s.lower() or "boss" in s.lower() for s in spoken_calls))

        # 4. Verify session state is now ACTIVE_SESSION
        self.assertEqual(self.assistant.state_machine.current_state, SessionState.ACTIVE_SESSION)

    def test_13_plain_speech_recognition_four_part_compound_utterance_execution(self):
        """
        Regression Test: 'light open Brave what is artificial intelligence who are you open YouTube'
        Verifies:
        - Segments into 4 distinct items:
          1. open Brave
          2. what is artificial intelligence
          3. who are you
          4. open YouTube
        - Exact execution sequence preserved
        - No combined string passed to app launcher
        - Gateway called for conversational question
        - YouTube opened
        """
        self.assertEqual(self.assistant.state_machine.current_state, SessionState.WAITING_FOR_ACTIVATION)

        with patch("core.assistant.search_youtube", return_value=(True, "Opened")) as mock_search_yt:
            utterance = "light open Brave what is artificial intelligence who are you open YouTube"
            ok = self.assistant.enqueue_utterance(utterance)
            self.assertTrue(ok)

            self.assertTrue(self.assistant.wait_for_queue_idle(timeout=5.0))

            # 1. Brave launched with exact name
            self.mock_launcher.launch.assert_called_once_with("brave")

            # 2. No combined strings passed to launcher
            for call_args in self.mock_launcher.launch.call_args_list:
                app_arg = call_args[0][0]
                self.assertNotIn("what is", app_arg.lower())
                self.assertNotIn("youtube", app_arg.lower())

            # 3. Gateway called for the conversational question
            self.mock_gateway.complete.assert_called_once()
            gateway_query = self.mock_gateway.complete.call_args[0][0]
            self.assertIn("artificial intelligence", gateway_query.lower())

            # 4. Identity response spoken
            spoken_calls = [c[0][0] for c in self.mock_tts.speak.call_args_list]
            self.assertTrue(any("light ai hoon" in s.lower() or "boss" in s.lower() for s in spoken_calls))

            # 5. YouTube opened with empty query
            mock_search_yt.assert_called_once_with("")

            # 6. Session state is ACTIVE_SESSION
            self.assertEqual(self.assistant.state_machine.current_state, SessionState.ACTIVE_SESSION)

    def test_14_plain_speech_recognition_three_part_compound_utterance_execution(self):
        """
        Regression Test: 'light open Chrome what is AI open YouTube'
        Verifies:
        - Segments into:
          1. open Chrome
          2. what is AI
          3. open YouTube
        - Exact sequence executed in FIFO order
        """
        self.assertEqual(self.assistant.state_machine.current_state, SessionState.WAITING_FOR_ACTIVATION)

        with patch("core.assistant.search_youtube", return_value=(True, "Opened")) as mock_search_yt:
            utterance = "light open Chrome what is AI open YouTube"
            ok = self.assistant.enqueue_utterance(utterance)
            self.assertTrue(ok)

            self.assertTrue(self.assistant.wait_for_queue_idle(timeout=5.0))

            # Chrome launched
            self.mock_launcher.launch.assert_called_once_with("chrome")

            # Gateway queried for AI
            self.mock_gateway.complete.assert_called_once()
            gateway_query = self.mock_gateway.complete.call_args[0][0]
            self.assertIn("ai", gateway_query.lower())

            # YouTube opened
            mock_search_yt.assert_called_once_with("")

    def test_15_hindi_command_suffixes_segmentation(self):
        """
        Verifies parser correctly handles Hindi/Hinglish suffixes without false splits:
        - 'open YouTube open karo' -> ['open YouTube']
        - 'Light YouTube open karo' -> ['open YouTube']
        - 'Light open YouTube karo' -> ['open YouTube']
        - 'Light Brave kholo who are you' -> ['open Brave', 'who are you']
        - 'Light open YouTube what is AI who are you' -> ['open YouTube', 'what is AI', 'who are you']
        - 'how do I open a bank account?' -> ['how do I open a bank account?']
        """
        # Case A: open YouTube open karo
        res_a = split_multi_prompt("open YouTube open karo")
        self.assertEqual(res_a, ["open YouTube"])

        # Case B: Light YouTube open karo
        res_b = split_multi_prompt("Light YouTube open karo")
        self.assertEqual(res_b, ["open YouTube"])

        # Case C: Light open YouTube karo
        res_c = split_multi_prompt("Light open YouTube karo")
        self.assertEqual(res_c, ["open YouTube"])

        # Case D: Light Brave kholo who are you
        res_d = split_multi_prompt("Light Brave kholo who are you")
        self.assertEqual(res_d, ["open Brave", "who are you"])

        # Case E: Light open YouTube what is AI who are you
        res_e = split_multi_prompt("Light open YouTube what is AI who are you")
        self.assertEqual(res_e, ["open YouTube", "what is AI", "who are you"])

        # Case F: Conversational question containing 'open' must not split
        res_f = split_multi_prompt("how do I open a bank account?")
        self.assertEqual(res_f, ["how do I open a bank account?"])

    def test_16_router_hindi_commands_and_no_bogus_launch_app_karo(self):
        """
        Verifies router routing for Hindi commands:
        - 'youtube open karo' routes to SEARCH_YOUTUBE with query=""
        - 'open youtube open karo' routes to SEARCH_YOUTUBE with query=""
        - 'open karo' does NOT generate launch_app_karo; returns UNKNOWN
        - 'brave kholo' routes to OPEN_APP with app_name="brave"
        - 'open brave karo' routes to OPEN_APP with app_name="brave"
        """
        router = CommandRouter()

        # 1. YouTube open karo -> SEARCH_YOUTUBE, query=""
        intent_yt1 = router._match_action("youtube open karo", "youtube open karo")
        self.assertEqual(intent_yt1.intent_type, IntentType.SEARCH_YOUTUBE)
        self.assertEqual(intent_yt1.payload.get("query"), "")

        # 2. open youtube open karo -> SEARCH_YOUTUBE, query=""
        intent_yt2 = router._match_action("open youtube open karo", "open youtube open karo")
        self.assertEqual(intent_yt2.intent_type, IntentType.SEARCH_YOUTUBE)
        self.assertEqual(intent_yt2.payload.get("query"), "")

        # 3. youtube kholo -> SEARCH_YOUTUBE, query=""
        intent_yt3 = router._match_action("youtube kholo", "youtube kholo")
        self.assertEqual(intent_yt3.intent_type, IntentType.SEARCH_YOUTUBE)
        self.assertEqual(intent_yt3.payload.get("query"), "")

        # 4. open karo -> must NEVER return OPEN_APP with app_name="karo"
        intent_karo = router._match_action("open karo", "open karo")
        self.assertNotEqual(intent_karo.intent_type, IntentType.OPEN_APP)
        self.assertEqual(intent_karo.intent_type, IntentType.UNKNOWN)

        # 5. brave kholo -> OPEN_APP, app_name="brave"
        intent_brave1 = router._match_action("brave kholo", "brave kholo")
        self.assertEqual(intent_brave1.intent_type, IntentType.OPEN_APP)
        self.assertEqual(intent_brave1.payload.get("app_name"), "brave")

        # 6. open brave karo -> OPEN_APP, app_name="brave"
        intent_brave2 = router._match_action("open brave karo", "open brave karo")
        self.assertEqual(intent_brave2.intent_type, IntentType.OPEN_APP)
        self.assertEqual(intent_brave2.payload.get("app_name"), "brave")

    def test_17_mixed_hindi_commands_and_questions_fifo_execution(self):
        """
        Regression Test: 'Light Brave kholo who are you'
        Verifies:
        - Split into:
          1. open Brave
          2. who are you
        - Executed in strict FIFO order
        - Brave is launched, identity question is answered
        - No 'karo' or unauthorized action is invoked
        """
        self.assertEqual(self.assistant.state_machine.current_state, SessionState.WAITING_FOR_ACTIVATION)

        utterance = "Light Brave kholo who are you"
        ok = self.assistant.enqueue_utterance(utterance)
        self.assertTrue(ok)

        self.assertTrue(self.assistant.wait_for_queue_idle(timeout=5.0))

        # 1. Brave launched exactly once
        self.mock_launcher.launch.assert_called_once_with("brave")

        # 2. No bogus 'karo' launch
        for call_args in self.mock_launcher.launch.call_args_list:
            app_arg = call_args[0][0]
            self.assertNotEqual(app_arg.lower(), "karo")

        # 3. Spoken identity response
        spoken_calls = [c[0][0] for c in self.mock_tts.speak.call_args_list]
        self.assertTrue(any("light ai hoon" in s.lower() or "boss" in s.lower() for s in spoken_calls))

        # 4. Final state check: queue empty, current_request is None
        self.assertEqual(self.assistant.queue_depth, 0)
        self.assertEqual(self.assistant.get_pending_snapshot(), [])
        self.assertIsNone(self.assistant.get_current_request())

    def test_18_split_multiple_independent_questions_punctuated_and_stt(self):
        """
        Verifies splitting of multiple independent questions in both punctuated and plain STT output:
        - 'how can I open a bank account what is AI' -> ['how can I open a bank account', 'what is AI']
        - 'How can I open a bank account, what is AI?' -> ['how can I open a bank account', 'what is AI?']
        - 'what is machine learning who are you' -> ['what is machine learning', 'who are you']
        - 'Light, what is machine learning, who are you?' -> ['what is machine learning', 'who are you?']
        - 'Light, open Chrome, how can I open a bank account, what is AI?' -> ['open Chrome', 'how can I open a bank account', 'what is AI?']
        - 'Light open YouTube who are you what is AI' -> ['open YouTube', 'who are you', 'what is AI']
        """
        # Case A: Plain STT two questions without punctuation
        s1 = split_multi_prompt("how can I open a bank account what is AI")
        self.assertEqual(s1, ["how can I open a bank account", "what is AI"])

        # Case B: Two questions with comma punctuation
        s2 = split_multi_prompt("Light, how can I open a bank account, what is AI?")
        self.assertEqual(s2, ["how can I open a bank account", "what is AI?"])

        # Case C: Question followed by identity question without punctuation
        s3 = split_multi_prompt("what is machine learning who are you")
        self.assertEqual(s3, ["what is machine learning", "who are you"])

        # Case D: Question followed by identity question with punctuation
        s4 = split_multi_prompt("Light, what is machine learning, who are you?")
        self.assertEqual(s4, ["what is machine learning", "who are you?"])

        # Case E: Three mixed segments with punctuation
        s5 = split_multi_prompt("Light, open Chrome, how can I open a bank account, what is AI?")
        self.assertEqual(s5, ["open Chrome", "how can I open a bank account", "what is AI?"])

        # Case F: Three mixed segments without punctuation (plain STT)
        s6 = split_multi_prompt("Light open YouTube who are you what is AI")
        self.assertEqual(s6, ["open YouTube", "who are you", "what is AI"])

    def test_19_nested_and_subordinate_questions_remain_unified(self):
        """
        Verifies that embedded clauses, subordinate questions, and introductory lead-ins
        remain a single question and are NOT falsely fragmented:
        - 'Can you tell me what AI is?'
        - 'Tell me how to open Chrome.'
        - 'What is AI and how does it work?'
        - 'What is the speed of light, and how is it measured?'
        """
        # Case A: Embedded clause 'what AI is' after 'Can you tell me'
        q1 = "Can you tell me what AI is?"
        self.assertEqual(split_multi_prompt(q1), [q1])

        # Case B: Lead-in 'Tell me how to open Chrome'
        q2 = "Tell me how to open Chrome."
        self.assertEqual(split_multi_prompt(q2), ["Tell me how to open Chrome"])

        # Case C: Subordinate question continuation 'and how does it work?'
        q3 = "What is AI and how does it work?"
        self.assertEqual(split_multi_prompt(q3), [q3])

        # Case D: Subordinate continuation with comma 'and how is it measured?'
        q4 = "What is the speed of light, and how is it measured?"
        self.assertEqual(split_multi_prompt(q4), [q4])

        # Case E: Single question with internal list
        q5 = "What is the difference between supervised, unsupervised, and reinforcement learning?"
        self.assertEqual(split_multi_prompt(q5), [q5])

    def test_20_mixed_utterance_independent_questions_fifo_execution(self):
        """
        Integration Test: 'Light, open Chrome, how can I open a bank account, what is AI'
        Verifies:
        - Decomposed into 3 sequential requests:
          1. Light, open Chrome
          2. how can I open a bank account
          3. what is AI
        - FIFO execution order:
          - Chrome launched first
          - First gateway call for 'how can I open a bank account'
          - Second gateway call for 'what is AI'
        - Queue depth becomes 0 and current_request is None after completion.
        """
        self.assertEqual(self.assistant.state_machine.current_state, SessionState.WAITING_FOR_ACTIVATION)

        gateway_calls = []

        def mock_gateway_complete(query):
            gateway_calls.append(query)
            return GatewayResponse(
                status=GatewayStatus.SUCCESS,
                raw_content=f'{{"intent": "CONVERSATION", "voice_response": "Answer for {query}"}}',
            )

        self.mock_gateway.complete.side_effect = mock_gateway_complete

        utterance = "Light, open Chrome, how can I open a bank account, what is AI"
        ok = self.assistant.enqueue_utterance(utterance)
        self.assertTrue(ok)

        self.assertTrue(self.assistant.wait_for_queue_idle(timeout=5.0))

        # 1. Chrome was launched
        self.mock_launcher.launch.assert_called_once_with("chrome")

        # 2. Gateway was queried twice in exact FIFO order
        self.assertEqual(len(gateway_calls), 2)
        self.assertIn("bank account", gateway_calls[0].lower())
        self.assertIn("ai", gateway_calls[1].lower())

        # 3. Final state check: empty queue and current_request is None
        self.assertEqual(self.assistant.queue_depth, 0)
        self.assertEqual(self.assistant.get_pending_snapshot(), [])
        self.assertIsNone(self.assistant.get_current_request())

