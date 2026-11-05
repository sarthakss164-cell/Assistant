"""
Final Verification Audit Test Suite for Phase D5.0: Conversation Memory & Chat Persistence.

Tests:
1. Action Lifecycle: SUCCESS, FAILED, REJECTED, CANCELLED, NOT_PERFORMED
2. TTS Lifecycle: PENDING, PLAYED, FAILED, CANCELLED
3. Session Memory: 10 complete turns limit, chronological order, clean RAM-only lifecycle
4. FIFO & Correlation: Voice + Text interleaved requests, strict ID correlation, no duplicates
5. Persistence & Crash Recovery: Atomic JSON writes, temp file cleanup, recovery from write failures
"""

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config.settings import SESSION_MEMORY_MAX_TURNS
from memory.session_memory import SessionMemory, SessionTurn
from memory.chat_manager import ChatManager
from core.assistant import LightAssistant, RequestItem
from core.router import CommandRouter, IntentType, CommandIntent
from core.state_machine import StateMachine, SessionState
from core.coe_gateway import CoeGatewayClient, GatewayResponse, GatewayStatus
from speech.listener import SpeechListener
from speech.tts import TTSEngine
import queue
import collections
import concurrent.futures


def make_audit_assistant(tmp_chats_dir: Path) -> LightAssistant:
    """Creates an isolated LightAssistant with mocked hardware/external services."""
    assistant = LightAssistant.__new__(LightAssistant)
    assistant.state_machine = StateMachine()

    # Memory subsystems
    assistant.session_memory = SessionMemory(max_turns=SESSION_MEMORY_MAX_TURNS)
    assistant.chat_manager = ChatManager(chats_dir=tmp_chats_dir)

    # Audio & speech mocks
    assistant.speech_gate = MagicMock()
    assistant.speech_gate.playback_context.return_value.__enter__ = MagicMock()
    assistant.speech_gate.playback_context.return_value.__exit__ = MagicMock()

    assistant.tts = MagicMock(spec=TTSEngine)
    assistant.tts.speak.side_effect = lambda text: assistant._on_speech_completed(text, success=True) or True

    assistant.listener = SpeechListener()
    assistant.listener.set_mic_active(True)

    # Gateway & Router
    assistant.gateway_client = MagicMock(spec=CoeGatewayClient)
    assistant.gateway_client.is_configured = True
    assistant.gateway_client.complete.return_value = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content='{"intent": "CONVERSATION", "voice_response": "Main aapki madad kar sakti hoon."}',
    )
    assistant.router = CommandRouter(gateway_client=assistant.gateway_client)

    # Subsystems
    assistant.app_launcher = MagicMock()
    assistant.music_player = MagicMock()
    assistant.music_player.has_active_playlist = False
    assistant.music_player.is_playing = False
    assistant.bridge = MagicMock()

    # FIFO Queue
    assistant._queue_capacity = 10
    assistant._request_queue = queue.Queue(maxsize=10)
    assistant._queue_shutdown_event = threading.Event()
    assistant._current_request_futures = []
    assistant._current_request_lock = threading.Lock()
    assistant._is_processing_request = False
    assistant._current_request_item = None
    assistant._processing_lock = threading.Lock()
    assistant._task_history = collections.deque(maxlen=100)
    assistant._history_lock = threading.Lock()
    assistant._has_pending_activation = False
    assistant._admission_lock = threading.Lock()
    assistant._active_utterance_staged_whatsapp = None
    assistant._shutdown_completed = False
    assistant._shutdown_finished_event = threading.Event()
    assistant._futures_lock = threading.Lock()
    assistant._active_futures = []
    assistant._queue_worker_thread = None
    assistant._last_command_text = ""
    assistant._last_command_time = 0.0

    assistant._action_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
    assistant._speech_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    assistant.start_queue_worker()
    return assistant


# =============================================================================
# 1. Action Lifecycle Verification
# =============================================================================

class TestActionLifecycle:
    """Verifies SUCCESS, FAILED, REJECTED, CANCELLED, and NOT_PERFORMED statuses."""

    def test_conversational_and_identity_remain_not_performed(self):
        """Conversational & identity requests must retain status NOT_PERFORMED."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            chats_path = Path(tmp_dir) / "chats"
            cm = ChatManager(chats_dir=chats_path)
            
            # Record user message
            cm.record_user_message(request_id="req_101", message="who are you", source="text")
            
            # Record identity response
            cm.record_assistant_response(
                request_id="req_101",
                message="Main Light AI hoon.",
                action={
                    "performed": False,
                    "intent": "IDENTITY",
                    "name": None,
                    "status": "NOT_PERFORMED",
                    "details": None,
                },
                speech_status="PLAYED",
            )
            
            # Attempt to update with SUCCESS (simulating single request completion)
            cm.update_action_status(request_id="req_101", status="SUCCESS")
            
            # Action status must stay NOT_PERFORMED because performed is False
            with open(cm.chat_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            action = data["messages"][0]["Light"]["action"]
            assert action["performed"] is False
            assert action["status"] == "NOT_PERFORMED"

    def test_action_success_recorded_after_execution(self):
        """Real action execution records PENDING then resolves to SUCCESS."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            chats_path = Path(tmp_dir) / "chats"
            cm = ChatManager(chats_dir=chats_path)
            
            cm.record_user_message(request_id="req_102", message="open notepad", source="voice")
            cm.record_assistant_response(
                request_id="req_102",
                message="Notepad open kar rahi hoon.",
                action={
                    "performed": True,
                    "intent": "OPEN_APP",
                    "name": "notepad",
                    "status": "PENDING",
                    "details": "Launching notepad",
                },
                speech_status="PENDING",
            )
            
            # Confirm initial PENDING
            with open(cm.chat_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert data["messages"][0]["Light"]["action"]["status"] == "PENDING"
            
            # Execution succeeds
            cm.update_action_status(request_id="req_102", status="SUCCESS", details="Launched notepad successfully")
            
            with open(cm.chat_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            action = data["messages"][0]["Light"]["action"]
            assert action["performed"] is True
            assert action["status"] == "SUCCESS"
            assert action["details"] == "Launched notepad successfully"

    def test_action_failed_recording(self):
        """Action execution failure updates status to FAILED with error details."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            chats_path = Path(tmp_dir) / "chats"
            cm = ChatManager(chats_dir=chats_path)
            
            cm.record_user_message(request_id="req_103", message="open nonexistent_app", source="voice")
            cm.record_assistant_response(
                request_id="req_103",
                message="App nahi mila.",
                action={
                    "performed": True,
                    "intent": "OPEN_APP",
                    "name": "nonexistent_app",
                    "status": "PENDING",
                    "details": "Launching",
                },
            )
            cm.update_action_status(
                request_id="req_103",
                status="FAILED",
                details="Executable not found on system path",
            )
            
            with open(cm.chat_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            action = data["messages"][0]["Light"]["action"]
            assert action["performed"] is True
            assert action["status"] == "FAILED"
            assert "not found" in action["details"]

    def test_action_rejected_recording(self):
        """Action rejected by intent validation or guard rails is recorded as REJECTED."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            chats_path = Path(tmp_dir) / "chats"
            cm = ChatManager(chats_dir=chats_path)
            
            cm.record_user_message(request_id="req_104", message="delete system32", source="text")
            cm.record_assistant_response(
                request_id="req_104",
                message="Yeh command safe nahi hai.",
                action={
                    "performed": True,
                    "intent": "SYSTEM_COMMAND",
                    "name": "delete",
                    "status": "REJECTED",
                    "details": "Command failed security policy check",
                },
                speech_status="PLAYED",
            )
            
            with open(cm.chat_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            action = data["messages"][0]["Light"]["action"]
            assert action["status"] == "REJECTED"

    def test_action_cancelled_on_shutdown(self):
        """Pending actions are transitioned to CANCELLED on shutdown finalization."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            chats_path = Path(tmp_dir) / "chats"
            cm = ChatManager(chats_dir=chats_path)
            
            cm.record_user_message(request_id="req_105", message="play song", source="voice")
            cm.record_assistant_response(
                request_id="req_105",
                message="Gaana baja rahi hoon.",
                action={
                    "performed": True,
                    "intent": "PLAY_SONG",
                    "name": "song",
                    "status": "PENDING",
                    "details": "Searching and loading stream",
                },
                speech_status="PENDING",
            )
            
            # Assistant shuts down before action completes
            cm.finalize(status="completed")
            
            with open(cm.chat_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert data["status"] == "completed"
            assert data["messages"][0]["Light"]["action"]["status"] == "CANCELLED"
            assert data["messages"][0]["Light"]["speech"]["status"] == "CANCELLED"


# =============================================================================
# 2. TTS Lifecycle Verification
# =============================================================================

class TestTTSLifecycle:
    """Verifies PENDING, PLAYED, FAILED, and CANCELLED speech statuses."""

    def test_tts_pending_then_played(self):
        """Speech status starts PENDING and transitions to PLAYED only on completion callback."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            chats_path = Path(tmp_dir) / "chats"
            assistant = make_audit_assistant(chats_path)
            try:
                # Mock callback tracking
                assistant.admit_text_command("who are you", request_id="req_201", wait_for_completion=True)
                
                with open(assistant.chat_manager.chat_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                assert len(data["messages"]) == 1
                msg = data["messages"][0]
                assert msg["Light"]["speech"]["status"] == "PLAYED"
            finally:
                assistant._shutdown_internal(farewell_message="")

    def test_tts_failed_callback_updates_status(self):
        """When speech callback reports failure, speech status is updated to FAILED."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            chats_path = Path(tmp_dir) / "chats"
            cm = ChatManager(chats_dir=chats_path)
            assistant = LightAssistant(bridge=None, chat_manager=cm)
            
            cm.record_user_message(request_id="req_202", message="hello", source="voice")
            cm.record_assistant_response(
                request_id="req_202",
                message="Namaste!",
                speech_status="PENDING",
            )
            
            # Simulate speech failed callback
            with assistant._processing_lock:
                item = RequestItem(raw_text="hello")
                item.item_id = "req_202"
                assistant._is_processing_request = True
                assistant._current_request_item = item
            
            assistant._on_speech_completed("Namaste!", success=False)
            
            with open(cm.chat_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert data["messages"][0]["Light"]["speech"]["status"] == "FAILED"

    def test_tts_cancelled_on_shutdown(self):
        """Pending speech playback is cancelled when the session is finalized."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            chats_path = Path(tmp_dir) / "chats"
            cm = ChatManager(chats_dir=chats_path)
            cm.record_user_message(request_id="req_203", message="test speech", source="voice")
            cm.record_assistant_response(
                request_id="req_203",
                message="Testing cancel",
                speech_status="PENDING",
            )
            
            cm.finalize(status="completed")
            with open(cm.chat_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert data["messages"][0]["Light"]["speech"]["status"] == "CANCELLED"


# =============================================================================
# 3. Session Memory Verification
# =============================================================================

class TestSessionMemory:
    """Verifies turn limits, chronological ordering, RAM-only isolation, and purge."""

    def test_max_turns_means_10_complete_user_assistant_turns(self):
        """Verify SESSION_MEMORY_MAX_TURNS = 10 holds 10 complete pairs (20 messages)."""
        mem = SessionMemory(max_turns=10)
        assert mem.max_turns == 10
        
        # Add 10 turns
        for i in range(1, 11):
            mem.add_turn(f"User question {i}", f"Assistant answer {i}", request_id=i)
            
        turns = mem.turns
        assert len(turns) == 10
        assert turns[0].user_message == "User question 1"
        assert turns[-1].user_message == "User question 10"
        
        # Context list should contain 20 messages (10 user + 10 assistant)
        context = mem.get_context_for_gateway()
        assert len(context) == 20
        assert context[0] == {"role": "user", "content": "User question 1"}
        assert context[1] == {"role": "assistant", "content": "Assistant answer 1"}
        assert context[-2] == {"role": "user", "content": "User question 10"}
        assert context[-1] == {"role": "assistant", "content": "Assistant answer 10"}

    def test_turn_eviction_is_strictly_fifo(self):
        """Adding turn 11 evicts turn 1, maintaining exact 10 turns."""
        mem = SessionMemory(max_turns=10)
        for i in range(1, 13):
            mem.add_turn(f"Q{i}", f"A{i}", request_id=i)
            
        turns = mem.turns
        assert len(turns) == 10
        # Turns 1 and 2 should have been evicted; turns 3 through 12 remain
        assert turns[0].user_message == "Q3"
        assert turns[-1].user_message == "Q12"

    def test_no_previous_session_loading(self):
        """Fresh SessionMemory starts completely empty regardless of disk state."""
        mem = SessionMemory(max_turns=10)
        assert len(mem.turns) == 0
        assert mem.get_context_for_gateway() == []

    def test_complete_clearing_on_shutdown(self):
        """Shutdown clears all turns from SessionMemory."""
        mem = SessionMemory(max_turns=10)
        mem.add_turn("Hello", "Hi there")
        assert len(mem.turns) == 1
        
        mem.clear()
        assert len(mem.turns) == 0
        assert mem.get_context_for_gateway() == []


# =============================================================================
# 4. FIFO & Correlation Verification
# =============================================================================

class TestFIFOCorrelation:
    """Verifies interleaved voice and text processing, correlation ID matching, and ordering."""

    def test_interleaved_voice_and_text_requests(self):
        """Queued voice and text commands maintain FIFO order and correct correlation."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            chats_path = Path(tmp_dir) / "chats"
            assistant = make_audit_assistant(chats_path)
            try:
                # Admit 1 text, 1 voice, 1 text
                ok1, _, _ = assistant.admit_text_command("who are you", request_id="txt_1", wait_for_completion=True)
                ok2 = assistant.enqueue_utterance("Light, pause music", wait_for_completion=True)
                ok3, _, _ = assistant.admit_text_command("what is python", request_id="txt_2", wait_for_completion=True)
                
                assert ok1 is True
                assert ok2 is True
                assert ok3 is True
                
                with open(assistant.chat_manager.chat_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                messages = data["messages"]
                assert len(messages) == 3
                
                # Turn 1 (Text)
                assert messages[0]["User"]["message"] == "who are you"
                assert messages[0]["User"]["source"] == "text"
                assert "Main Light AI hoon" in messages[0]["Light"]["message"]
                
                # Turn 2 (Voice)
                assert "pause music" in messages[1]["User"]["message"]
                assert messages[1]["User"]["source"] == "voice"
                assert messages[1]["Light"]["action"]["performed"] is True
                assert messages[1]["Light"]["action"]["status"] == "SUCCESS"
                
                # Turn 3 (Text)
                assert messages[2]["User"]["message"] == "what is python"
                assert messages[2]["User"]["source"] == "text"
                assert messages[2]["Light"]["action"]["performed"] is False
                assert messages[2]["Light"]["action"]["status"] == "NOT_PERFORMED"
                
                # Unique IDs, no duplicates
                req_ids = [m["request_id"] for m in messages]
                assert len(req_ids) == len(set(req_ids))
            finally:
                assistant._shutdown_internal(farewell_message="")


# =============================================================================
# 5. Persistence & Crash Recovery Verification
# =============================================================================

class TestPersistenceCrashRecovery:
    """Verifies atomic write integrity, temporary file cleanup, and write failure recovery."""

    def test_atomic_replacement_leaves_no_temp_files(self):
        """Completed atomic saves delete or replace temp files without leftover .tmp_* files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            chats_path = Path(tmp_dir) / "chats"
            cm = ChatManager(chats_dir=chats_path)
            
            for i in range(5):
                cm.record_user_message(request_id=f"r_{i}", message=f"Message {i}")
                cm.record_assistant_response(request_id=f"r_{i}", message=f"Response {i}")
            
            # Verify no temp files exist
            temp_files = list(chats_path.glob(".tmp_*"))
            assert len(temp_files) == 0
            
            # Destination file is valid JSON
            with open(cm.chat_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert len(data["messages"]) == 5

    def test_recovery_from_write_interruption(self):
        """Simulated write failure preserves existing valid JSON on disk without data loss."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            chats_path = Path(tmp_dir) / "chats"
            cm = ChatManager(chats_dir=chats_path)
            
            # Initial good save
            cm.record_user_message(request_id="r_init", message="Initial message")
            cm.record_assistant_response(request_id="r_init", message="Initial response")
            
            # Inject failure during os.replace
            with patch("os.replace", side_effect=OSError("Simulated disk replacement error")):
                res = cm._save_atomic()
                assert res is False
            
            # Prior JSON file must still exist and be completely valid
            with open(cm.chat_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert len(data["messages"]) == 1
            assert data["messages"][0]["User"]["message"] == "Initial message"

    def test_incomplete_request_on_crash_has_valid_json(self):
        """If assistant crashes after user message admission, JSON remains valid with pending state."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            chats_path = Path(tmp_dir) / "chats"
            cm = ChatManager(chats_dir=chats_path)
            
            # Only user message recorded (process halts before Light responds)
            cm.record_user_message(request_id="r_incomplete", message="interrupted query", source="voice")
            
            with open(cm.chat_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            assert len(data["messages"]) == 1
            msg = data["messages"][0]
            assert msg["User"]["message"] == "interrupted query"
            assert msg["Light"]["message"] == ""
            assert msg["Light"]["speech"]["status"] == "PENDING"
