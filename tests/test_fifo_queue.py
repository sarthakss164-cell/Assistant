"""
Unit and integration tests for Phase 8 FINAL: FIFO Multi-Prompt Conversation Queue for LIGHT AI.
Verifies strict sequential FIFO ordering, non-overtaking conversation responses,
slow action barriers, error recovery, queue-full non-destructive rejection,
session state preservation (including wake-word follow-ups and music PTT),
and deadlock-free graceful shutdown.
All tests use mocks; no real hardware, live microphone, or network calls are initiated.
"""

import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import speech_recognition as sr

from core.assistant import LightAssistant, RequestItem
from core.state_machine import SessionState
from core.router import IntentType, CommandIntent
from core.coe_gateway import GatewayResponse, GatewayStatus


class TestFifoMultiPromptQueue(unittest.TestCase):
    """Test suite for FIFO Multi-Prompt Conversation Queue."""

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

    def test_1_three_requests_execute_in_strict_fifo_order(self):
        """Three requests execute in strict FIFO order: each finishes before the next begins."""
        timeline = []
        lock = threading.Lock()

        def slow_action(*args, **kwargs):
            with lock:
                timeline.append(("req1_action_start", time.time()))
            time.sleep(0.06)
            with lock:
                timeline.append(("req1_action_end", time.time()))
            return True, "Chrome launched"

        def track_speak(text):
            with lock:
                t_lower = text.lower()
                if "launched" in t_lower or "chrome" in t_lower:
                    tag = "req1_speech"
                elif "artificial intelligence" in t_lower:
                    tag = "req2_speech"
                elif "boss" in t_lower or "light ai hoon" in t_lower:
                    tag = "req3_speech"
                else:
                    tag = f"speech_{text[:8]}"
                timeline.append((f"{tag}_start", time.time()))
            time.sleep(0.03)
            with lock:
                timeline.append((f"{tag}_end", time.time()))
            return True

        self.mock_launcher.launch.side_effect = slow_action
        self.mock_tts.speak.side_effect = track_speak

        # Activate session
        self.assistant.state_machine.activate_session()

        # Enqueue 3 requests in rapid succession
        ok1 = self.assistant.enqueue_request("open Chrome")
        ok2 = self.assistant.enqueue_request("what is AI?")
        ok3 = self.assistant.enqueue_request("who are you?")

        self.assertTrue(ok1)
        self.assertTrue(ok2)
        self.assertTrue(ok3)

        # Wait for queue to process completely
        self.assertTrue(self.assistant.wait_for_queue_idle(timeout=5.0))

        # Analyze timeline
        event_names = [event[0] for event in timeline]

        # Verify all events took place
        self.assertIn("req1_action_start", event_names)
        self.assertIn("req1_action_end", event_names)
        self.assertIn("req1_speech_start", event_names)
        self.assertIn("req1_speech_end", event_names)
        self.assertIn("req2_speech_start", event_names)
        self.assertIn("req2_speech_end", event_names)
        self.assertIn("req3_speech_start", event_names)
        self.assertIn("req3_speech_end", event_names)

        # Timestamps
        t_req1_action_end = next(t for name, t in timeline if name == "req1_action_end")
        t_req1_speech_end = next(t for name, t in timeline if name == "req1_speech_end")
        t_req2_start = next(t for name, t in timeline if name == "req2_speech_start")
        t_req2_end = next(t for name, t in timeline if name == "req2_speech_end")
        t_req3_start = next(t for name, t in timeline if name == "req3_speech_start")

        # Request 1 (both action and speech) must finish before Request 2 speech starts
        self.assertLessEqual(t_req1_action_end, t_req2_start)
        self.assertLessEqual(t_req1_speech_end, t_req2_start)

        # Request 2 must finish before Request 3 starts
        self.assertLessEqual(t_req2_end, t_req3_start)

    def test_2_slow_first_request_blocks_second_request_from_starting_early(self):
        """A slow first action holds the sequential queue barrier until it completes."""
        req2_started = threading.Event()
        req1_finished = threading.Event()

        def slow_action(*args, **kwargs):
            time.sleep(0.1)
            req1_finished.set()
            return True, "OK"

        def track_speak(text):
            if "ai" in text.lower():
                # Second request's speech
                req2_started.set()
                # When request 2 starts, request 1 must have already finished!
                self.assertTrue(req1_finished.is_set(), "Request 2 started before Request 1 finished!")
            return True

        self.mock_launcher.launch.side_effect = slow_action
        self.mock_tts.speak.side_effect = track_speak

        self.assistant.state_machine.activate_session()
        self.assistant.enqueue_request("open Chrome")
        self.assistant.enqueue_request("what is AI?")

        self.assertTrue(self.assistant.wait_for_queue_idle(timeout=5.0))
        self.assertTrue(req2_started.is_set())

    def test_3_conversation_request_cannot_overtake_earlier_action(self):
        """A conversational prompt submitted after an action command never speaks before the action finishes."""
        order_of_events = []

        def slow_action(*args, **kwargs):
            order_of_events.append("action_start")
            time.sleep(0.08)
            order_of_events.append("action_end")
            return True, "Done"

        def track_speak(text):
            if "ai" in text.lower():
                order_of_events.append("conversation_spoken")
            elif "chrome" in text.lower():
                order_of_events.append("action_ack_spoken")
            return True

        self.mock_launcher.launch.side_effect = slow_action
        self.mock_tts.speak.side_effect = track_speak

        self.assistant.state_machine.activate_session()
        self.assistant.enqueue_request("open Chrome")
        self.assistant.enqueue_request("what is AI?")

        self.assertTrue(self.assistant.wait_for_queue_idle(timeout=5.0))

        # 'conversation_spoken' must appear strictly after 'action_end'
        action_end_idx = order_of_events.index("action_end")
        convo_idx = order_of_events.index("conversation_spoken")
        self.assertGreater(convo_idx, action_end_idx, "Conversation response overtook earlier action!")

    def test_4_failed_action_does_not_block_subsequent_queue_items(self):
        """If Request 1 raises an exception, the worker catches it and continues to Request 2."""
        def failing_action(*args, **kwargs):
            raise RuntimeError("Fatal process spawn error")

        self.mock_launcher.launch.side_effect = failing_action

        self.assistant.state_machine.activate_session()
        self.assistant.enqueue_request("open Chrome")
        self.assistant.enqueue_request("who are you?")

        self.assertTrue(self.assistant.wait_for_queue_idle(timeout=5.0))

        # Request 2 (identity) was successfully executed despite Request 1 failure
        spoken_calls = [c[0][0] for c in self.mock_tts.speak.call_args_list]
        self.assertTrue(any("light" in s.lower() or "kaun" in s.lower() for s in spoken_calls))

    def test_5_queue_full_behavior_rejects_without_discarding_older_requests(self):
        """When queue reaches capacity (10), new prompts are rejected non-destructively."""
        # Block worker by holding a long task
        worker_started = threading.Event()
        worker_blocker = threading.Event()

        def blocking_action(*args, **kwargs):
            worker_started.set()
            worker_blocker.wait(timeout=2.0)
            return True, "Done"

        self.mock_launcher.launch.side_effect = blocking_action
        self.assistant.state_machine.activate_session()

        # Enqueue item 1 (which will be picked up by worker and block)
        self.assistant.enqueue_request("open Chrome")
        self.assertTrue(worker_started.wait(timeout=2.0), "Worker did not start blocking action")

        # Now fill the queue with 10 items
        for i in range(10):
            res = self.assistant.enqueue_request(f"who are you? {i}")
            self.assertTrue(res, f"Failed to enqueue request {i}")

        self.assertEqual(self.assistant.queue_depth, 10)

        # 11th item must be rejected
        ok_extra = self.assistant.enqueue_request("what is AI?")
        self.assertFalse(ok_extra, "11th request was not rejected when queue was full!")

        # Queue depth must still be 10 (non-destructive)
        self.assertEqual(self.assistant.queue_depth, 10)

        # Spoken rejection was triggered
        spoken_calls = [c[0][0] for c in self.mock_tts.speak.call_args_list]
        self.assertTrue(any("queue full" in s.lower() for s in spoken_calls))

        # Release worker and verify queue drains cleanly
        worker_blocker.set()
        self.assertTrue(self.assistant.wait_for_queue_idle(timeout=5.0))
        self.assertEqual(self.assistant.queue_depth, 0)

    def test_6_shutdown_stops_queue_and_releases_worker_safely(self):
        """Shutdown stops accepting requests and terminates worker thread without deadlocks."""
        self.assertTrue(self.assistant._queue_worker_thread.is_alive())

        self.assistant.state_machine.activate_session()
        self.assistant._shutdown_internal(farewell_message="")

        # Queue rejects any new requests
        ok = self.assistant.enqueue_request("open Chrome")
        self.assertFalse(ok)

        # Worker thread must have terminated cleanly
        time.sleep(0.05)
        self.assertFalse(
            self.assistant._queue_worker_thread is not None and self.assistant._queue_worker_thread.is_alive(),
            "Queue worker thread failed to terminate on shutdown",
        )

    def test_7_active_session_follow_up_without_wake_word(self):
        """After session activation, follow-up prompts do NOT require repeating the wake word."""
        self.assertEqual(self.assistant.state_machine.current_state, SessionState.WAITING_FOR_ACTIVATION)

        # Unprefixed prompt in WAITING_FOR_ACTIVATION is rejected
        rejected = self.assistant.enqueue_request("what is AI?")
        self.assertFalse(rejected)
        self.assertEqual(self.assistant.state_machine.current_state, SessionState.WAITING_FOR_ACTIVATION)

        # Prefixed prompt accepted into queue
        activated = self.assistant.enqueue_request("Light, open Chrome")
        self.assertTrue(activated)

        # Subsequent prompt in same session does NOT require "Light" (accepted into queue)
        follow_up = self.assistant.enqueue_request("what is AI?")
        self.assertTrue(follow_up)

        self.assertTrue(self.assistant.wait_for_queue_idle(timeout=5.0))
        self.assertEqual(self.assistant.state_machine.current_state, SessionState.ACTIVE_SESSION)

    def test_8_music_mode_ptt_wake_word_enforcement_into_queue(self):
        """PTT capture strictly requires 'Light' wake word and feeds valid commands into queue."""
        mock_stt = MagicMock()
        mock_audio = MagicMock(spec=sr.AudioData)

        # 1. Speech without "Light" is rejected
        mock_stt.transcribe.return_value = (True, "tum kaun ho")
        self.assistant.stt = mock_stt
        self.assistant._process_ptt_audio(mock_audio)
        self.assertEqual(self.assistant.queue_depth, 0)

        # 2. Speech with "Light" is accepted into queue
        mock_stt.transcribe.return_value = (True, "Light, tum kaun ho")
        self.assistant._process_ptt_audio(mock_audio)
        self.assertTrue(self.assistant.wait_for_queue_idle(timeout=5.0))

        spoken = [c[0][0] for c in self.mock_tts.speak.call_args_list]
        self.assertTrue(any("light" in s.lower() or "kaun" in s.lower() for s in spoken))

    @patch("core.assistant.find_matching_contacts", return_value=["anand"])
    @patch("core.assistant.resolve_contact_phone", return_value=("919876543210", None))
    @patch("core.assistant.stage_whatsapp_message", return_value=True)
    @patch("core.assistant.send_whatsapp_message_via_pywhatkit", return_value=(True, "Sent"))
    def test_9_whatsapp_confirmation_state_preserved_through_queue(
        self, mock_send, mock_stage, mock_resolve, mock_find
    ):
        """Sequential queue preserves WhatsApp modal confirmation transitions across prompts."""
        self.assistant.state_machine.activate_session()

        # Request 1: Start WhatsApp workflow
        self.assistant.enqueue_request("message Anand that meeting at five")
        time.sleep(0.05)

        # State must transition to AWAITING_CONFIRMATION
        self.assertEqual(self.assistant.state_machine.current_state, SessionState.AWAITING_CONFIRMATION)

        # Request 2: Confirmation "haan"
        self.assistant.enqueue_request("haan")
        self.assertTrue(self.assistant.wait_for_queue_idle(timeout=5.0))

        # Message must have been sent and state restored to ACTIVE_SESSION
        mock_send.assert_called_once()
        self.assertEqual(self.assistant.state_machine.current_state, SessionState.ACTIVE_SESSION)

    def test_10_dequeued_request_immediately_leaves_pending_queue_and_tracks_currently_processing(self):
        """
        Lifecycle verification:
        - Dequeued request is immediately removed from pending queue upon worker takeover.
        - Currently processing request is exposed via get_current_request() and NOT counted in queue_depth or get_pending_requests().
        - Completed requests are moved to task history, leaving pending queue size at 0.
        """
        req1_executing = threading.Event()
        req1_blocker = threading.Event()
        req2_executing = threading.Event()
        req2_blocker = threading.Event()

        def controlled_action(*args, **kwargs):
            req1_executing.set()
            req1_blocker.wait(timeout=2.0)
            return True, "Launched"

        def controlled_speech(text):
            if "light ai" in text.lower() or "boss" in text.lower():
                req2_executing.set()
                req2_blocker.wait(timeout=2.0)
            return True

        self.mock_launcher.launch.side_effect = controlled_action
        self.mock_tts.speak.side_effect = controlled_speech
        self.assistant.state_machine.activate_session()

        # Enqueue req1 and req2
        self.assistant.enqueue_request("open Chrome")
        self.assistant.enqueue_request("who are you?")

        # Wait until req1 is actively executing in worker
        self.assertTrue(req1_executing.wait(timeout=2.0))

        # Check pending queue & current request separation during req1 execution:
        # 1. Current request is req1
        curr = self.assistant.get_current_request()
        self.assertIsNotNone(curr)
        self.assertEqual(curr.raw_text, "open Chrome")
        self.assertEqual(curr.status, "processing")
        self.assertTrue(self.assistant.is_processing)

        # 2. Pending queue contains ONLY req2 (req1 was already removed upon dequeue)
        pending = self.assistant.get_pending_requests()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].raw_text, "who are you?")
        self.assertEqual(self.assistant.queue_depth, 1)

        # Release req1
        req1_blocker.set()

        # Wait until req2 is actively executing
        self.assertTrue(req2_executing.wait(timeout=2.0))

        # Check during req2 execution:
        # 1. Current request is req2
        curr2 = self.assistant.get_current_request()
        self.assertIsNotNone(curr2)
        self.assertEqual(curr2.raw_text, "who are you?")
        self.assertEqual(curr2.status, "processing")

        # 2. Pending queue is now 0 (both requests have been dequeued)
        self.assertEqual(self.assistant.queue_depth, 0)
        self.assertEqual(self.assistant.get_pending_requests(), [])

        # 3. Task history has req1 recorded as completed
        history = self.assistant.get_task_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].raw_text, "open Chrome")
        self.assertEqual(history[0].status, "completed")
        self.assertTrue(history[0].success)

        # Release req2
        req2_blocker.set()
        self.assertTrue(self.assistant.wait_for_queue_idle(timeout=5.0))

        # Final idle state:
        self.assertEqual(self.assistant.queue_depth, 0)
        self.assertEqual(self.assistant.get_pending_requests(), [])
        self.assertIsNone(self.assistant.get_current_request())
        self.assertFalse(self.assistant.is_processing)

        final_history = self.assistant.get_task_history()
        self.assertEqual(len(final_history), 2)
        self.assertEqual(final_history[0].status, "completed")
        self.assertEqual(final_history[1].status, "completed")

    def test_11_exception_does_not_corrupt_queue_accounting_or_drop_subsequent_pending_requests(self):
        """
        Error recovery lifecycle:
        - When an exception occurs during request execution, it is caught.
        - Status is marked 'failed' with error recorded, task_done() is called, and history is updated.
        - Subsequent pending requests execute without disruption.
        """
        def failing_action(*args, **kwargs):
            raise ValueError("Critical device I/O error")

        self.mock_launcher.launch.side_effect = failing_action
        self.assistant.state_machine.activate_session()

        # Enqueue failing request followed by valid conversational request
        self.assistant.enqueue_request("open Chrome")
        self.assistant.enqueue_request("who are you?")

        self.assertTrue(self.assistant.wait_for_queue_idle(timeout=5.0))

        history = self.assistant.get_task_history()
        self.assertEqual(len(history), 2)

        # Req1 failed gracefully with error preserved
        self.assertEqual(history[0].raw_text, "open Chrome")
        self.assertEqual(history[0].status, "failed")
        self.assertFalse(history[0].success)
        self.assertIn("Critical device I/O error", history[0].error)

        # Req2 succeeded without being corrupted or dropped
        self.assertEqual(history[1].raw_text, "who are you?")
        self.assertEqual(history[1].status, "completed")
        self.assertTrue(history[1].success)

        # Pending queue is completely clear and idle
        self.assertEqual(self.assistant.queue_depth, 0)
        self.assertEqual(self.assistant.get_pending_requests(), [])
        self.assertIsNone(self.assistant.get_current_request())

    def test_12_shutdown_lifecycle_marks_remaining_pending_tasks_cancelled_and_drains_cleanly(self):
        """
        Shutdown lifecycle:
        - Draining pending requests on shutdown marks them 'cancelled' with timestamps.
        - Queue depth reaches 0 and worker thread terminates cleanly without hanging.
        """
        worker_started = threading.Event()
        worker_blocker = threading.Event()

        def blocking_action(*args, **kwargs):
            worker_started.set()
            worker_blocker.wait(timeout=2.0)
            return True, "Done"

        self.mock_launcher.launch.side_effect = blocking_action
        self.assistant.state_machine.activate_session()

        # Enqueue req1 (worker grabs it and blocks)
        self.assistant.enqueue_request("open Chrome")
        self.assertTrue(worker_started.wait(timeout=2.0))

        # Enqueue req2 and req3 (stay waiting in queue)
        self.assistant.enqueue_request("who are you?")
        self.assistant.enqueue_request("what is AI?")
        self.assertEqual(self.assistant.queue_depth, 2)

        # Trigger shutdown while req1 is still holding worker
        worker_blocker.set()
        self.assistant._shutdown_internal(farewell_message="")

        # Queue depth is now 0
        self.assertEqual(self.assistant.queue_depth, 0)
        self.assertEqual(self.assistant.get_pending_requests(), [])
        self.assertIsNone(self.assistant.get_current_request())

        # Check history includes cancelled requests
        history = self.assistant.get_task_history()
        cancelled = [item for item in history if item.status == "cancelled"]
        self.assertGreaterEqual(len(cancelled), 1)
        for c in cancelled:
            self.assertIsNotNone(c.end_time)

    def test_13_request_item_serialization_to_dict(self):
        """RequestItem.to_dict() returns accurate dictionary representation."""
        item = RequestItem(raw_text="open Chrome", utterance_id="utt_test_123")
        d = item.to_dict()
        self.assertEqual(d["raw_text"], "open Chrome")
        self.assertEqual(d["utterance_id"], "utt_test_123")
        self.assertEqual(d["status"], "pending")
        self.assertIsNone(d["start_time"])
        self.assertIsNone(d["end_time"])
        self.assertFalse(d["success"])
        self.assertIsNone(d["error"])

    def test_14_queue_state_debug_inspector(self):
        """get_queue_state_debug() returns complete, accurate status snapshot."""
        # Initial idle state
        dbg = self.assistant.get_queue_state_debug()
        self.assertEqual(dbg["pending_count"], 0)
        self.assertEqual(dbg["pending_requests"], [])
        self.assertIsNone(dbg["current_request"])
        self.assertEqual(dbg["task_history_count"], 0)

        # Enqueue and process a request
        self.assistant.state_machine.activate_session()
        self.assistant.enqueue_request("who are you?", wait_for_completion=True)

        # State after completion: pending 0, current None, history 1
        dbg_post = self.assistant.get_queue_state_debug()
        self.assertEqual(dbg_post["pending_count"], 0)
        self.assertIsNone(dbg_post["current_request"])
        self.assertEqual(dbg_post["task_history_count"], 1)
        self.assertEqual(dbg_post["history_summary"]["completed"], 1)
        self.assertEqual(dbg_post["history_summary"]["failed"], 0)

    def test_15_stop_command_initiates_shutdown_and_cleans_up_cleanly(self):
        """Executing 'stop' command sets _shutdown_finished_event and leaves queue empty."""
        self.assistant.state_machine.activate_session()
        self.assistant.enqueue_request("stop", wait_for_completion=True)

        self.assertTrue(self.assistant._shutdown_finished_event.is_set())
        self.assertEqual(self.assistant.queue_depth, 0)
        self.assertEqual(self.assistant.get_pending_requests(), [])
        self.assertIsNone(self.assistant.get_current_request())
        self.assertEqual(self.assistant.state_machine.current_state, SessionState.SHUTDOWN)

    def test_16_repeated_shutdown_requests_are_idempotent_and_safe(self):
        """Multiple consecutive shutdown calls do not raise exceptions or deadlock."""
        self.assistant._shutdown_internal(farewell_message="")
        self.assertTrue(self.assistant._shutdown_completed)
        self.assertTrue(self.assistant._shutdown_finished_event.is_set())

        # Second call
        self.assistant._shutdown_internal(farewell_message="")
        self.assertTrue(self.assistant._shutdown_completed)

        # Third call
        self.assistant._shutdown_internal(farewell_message="")
        self.assertEqual(self.assistant.queue_depth, 0)
        self.assertIsNone(self.assistant.get_current_request())

    def test_17_ctrl_c_keyboard_interrupt_clean_exit(self):
        """Simulating KeyboardInterrupt during run() triggers clean shutdown and exits."""
        # Mock listener to initialize and raise KeyboardInterrupt on first listen()
        self.assistant.listener = MagicMock()
        self.assistant.listener.init_microphone.return_value = True
        self.assistant.listener.listen.side_effect = KeyboardInterrupt()
        self.assistant.run()

        self.assertFalse(self.assistant.running)
        self.assertEqual(self.assistant.state_machine.current_state, SessionState.SHUTDOWN)
        self.assertTrue(self.assistant._shutdown_finished_event.is_set())
        self.assertIsNone(self.assistant._queue_worker_thread)

    def test_18_pending_positions_recalculated_1_to_n_across_separate_utterances(self):
        """
        Verifies:
        1. Pending positions are recalculated dynamically 1..N for each snapshot.
        2. Internal request IDs remain monotonically unique and are NOT used as pending positions.
        3. As soon as a request is dequeued, it immediately disappears from the pending list.
        4. Pending count becomes 0 and current_request becomes None when execution completes.
        5. A subsequent utterance starts its displayed pending positions at 1, while internal IDs advance.
        """
        step1_started = threading.Event()
        step1_proceed = threading.Event()

        def blockable_launch(*args, **kwargs):
            step1_started.set()
            step1_proceed.wait(timeout=3.0)
            return True, "Done"

        self.mock_launcher.launch.side_effect = blockable_launch
        self.assistant.state_machine.activate_session()

        # Enqueue utterance 1: 3 prompts
        # First prompt will be picked up by worker and block on step1_proceed
        self.assistant.enqueue_utterance("open Chrome what is AI who are you")
        self.assertTrue(step1_started.wait(timeout=2.0))

        # At this point, req 1 is currently processing.
        curr = self.assistant.get_current_request()
        self.assertIsNotNone(curr)
        self.assertEqual(curr.status, "processing")
        self.assertIn("open Chrome", curr.raw_text)
        id1 = curr.item_id

        # Remaining pending requests: 2 items
        snapshot1 = self.assistant.get_pending_snapshot()
        self.assertEqual(len(snapshot1), 2)
        # Positions must be 1 and 2
        self.assertEqual(snapshot1[0]["position"], 1)
        self.assertEqual(snapshot1[1]["position"], 2)
        # Verify internal request IDs are distinct and strictly greater than id1
        id2 = snapshot1[0]["item_id"]
        id3 = snapshot1[1]["item_id"]
        self.assertGreater(id2, id1)
        self.assertGreater(id3, id2)

        # Allow req 1 to complete and finish the entire batch
        step1_proceed.set()
        self.assertTrue(self.assistant.wait_for_queue_idle(timeout=5.0))

        # After all requests finish:
        self.assertEqual(self.assistant.queue_depth, 0)
        self.assertEqual(self.assistant.get_pending_requests(), [])
        self.assertEqual(self.assistant.get_pending_snapshot(), [])
        self.assertIsNone(self.assistant.get_current_request())

        # Utterance 2: 2 prompts
        step2_started = threading.Event()
        step2_proceed = threading.Event()

        def blockable_launch_2(*args, **kwargs):
            step2_started.set()
            step2_proceed.wait(timeout=3.0)
            return True, "Done"

        self.mock_launcher.launch.side_effect = blockable_launch_2

        self.assistant.enqueue_utterance("open Brave who are you")
        self.assertTrue(step2_started.wait(timeout=2.0))

        # Req 4 is currently processing
        curr2 = self.assistant.get_current_request()
        self.assertIsNotNone(curr2)
        id4 = curr2.item_id
        self.assertGreater(id4, id3)

        # Fresh pending display for waiting item must start at position 1 (NOT historical ID 5)
        snapshot2 = self.assistant.get_pending_snapshot()
        self.assertEqual(len(snapshot2), 1)
        self.assertEqual(snapshot2[0]["position"], 1)
        self.assertIn("who are you", snapshot2[0]["raw_text"])
        self.assertGreater(snapshot2[0]["item_id"], id4)

        # Complete utterance 2
        step2_proceed.set()
        self.assertTrue(self.assistant.wait_for_queue_idle(timeout=5.0))

        # Final verification: empty queue and current_request is None
        self.assertEqual(self.assistant.queue_depth, 0)
        self.assertEqual(self.assistant.get_pending_snapshot(), [])
        self.assertIsNone(self.assistant.get_current_request())

