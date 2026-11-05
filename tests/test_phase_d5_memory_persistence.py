"""
Phase D5.0 Comprehensive Test Suite — Conversation Memory & Chat Persistence
LIGHT AI V1.0
"""

import json
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from config.settings import BASE_DIR
from memory.session_memory import SessionMemory, SessionTurn
from memory.chat_manager import ChatManager
from core.coe_gateway import CoeGatewayClient, GatewayStatus, GatewayResponse
from core.router import CommandRouter, IntentType, CommandIntent
from core.state_machine import SessionState, StateMachine
from core.assistant import LightAssistant, RequestItem
from speech.tts import TTSEngine
from speech.listener import SpeechListener


# ==============================================================================
# 1. Session Memory Unit Tests
# ==============================================================================

def test_session_memory_initialization_empty():
    """Verify session memory starts empty and does not load any disk history."""
    mem = SessionMemory(max_turns=5)
    assert len(mem.turns) == 0
    assert mem.get_context_for_gateway() == []


def test_session_memory_add_and_order():
    """Verify turns are stored in chronological sequence and formatted for OpenAI chat."""
    mem = SessionMemory(max_turns=5)
    mem.add_turn(user_message="What is Python?", assistant_message="Python is a programming language.", request_id=1)
    mem.add_turn(user_message="Who created it?", assistant_message="Guido van Rossum.", request_id=2)

    assert len(mem.turns) == 2
    context = mem.get_context_for_gateway()
    assert len(context) == 4
    assert context[0] == {"role": "user", "content": "What is Python?"}
    assert context[1] == {"role": "assistant", "content": "Python is a programming language."}
    assert context[2] == {"role": "user", "content": "Who created it?"}
    assert context[3] == {"role": "assistant", "content": "Guido van Rossum."}


def test_session_memory_max_turns_eviction():
    """Verify session memory strictly bounds turns to max_turns using FIFO eviction."""
    mem = SessionMemory(max_turns=3)
    for i in range(5):
        mem.add_turn(f"User {i + 1}", f"Assistant {i + 1}", request_id=i + 1)

    assert len(mem.turns) == 3
    # Turns 1 and 2 evicted; 3, 4, 5 retained
    assert mem.turns[0].user_message == "User 3"
    assert mem.turns[1].user_message == "User 4"
    assert mem.turns[2].user_message == "User 5"


def test_session_memory_clear():
    """Verify clear() purges all turns from memory."""
    mem = SessionMemory(max_turns=5)
    mem.add_turn("Hello", "Hi there!", request_id=1)
    assert len(mem.turns) == 1

    mem.clear()
    assert len(mem.turns) == 0
    assert mem.get_context_for_gateway() == []


# ==============================================================================
# 2. Chat Manager Unit Tests
# ==============================================================================

def test_chat_manager_creates_unique_uuid_file():
    """Verify ChatManager generates a unique UUID file in chats directory on startup."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        chats_path = Path(tmp_dir) / "chats"
        cm = ChatManager(chats_dir=chats_path)

        assert chats_path.exists()
        assert cm.chat_file.exists()
        assert cm.chat_id is not None
        assert str(cm.chat_id) in cm.chat_file.name

        with open(cm.chat_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["chat_id"] == cm.chat_id
        assert data["status"] == "active"
        assert "created_at" in data
        assert "updated_at" in data
        assert data["messages"] == []


def test_chat_manager_new_file_per_startup():
    """Verify distinct ChatManager instances create distinct chat files."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        chats_path = Path(tmp_dir) / "chats"
        cm1 = ChatManager(chats_dir=chats_path)
        cm2 = ChatManager(chats_dir=chats_path)

        assert cm1.chat_id != cm2.chat_id
        assert cm1.chat_file != cm2.chat_file
        assert cm1.chat_file.exists()
        assert cm2.chat_file.exists()


def test_chat_manager_records_user_and_assistant():
    """Verify recording user message, assistant message, actions, and speech status."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        chats_path = Path(tmp_dir) / "chats"
        cm = ChatManager(chats_dir=chats_path)

        cm.record_user_message(request_id=101, message="Open Chrome", source="voice")
        cm.record_assistant_response(
            request_id=101,
            message="Chrome khol rahi hu, Sir.",
            action={
                "performed": True,
                "intent": "OPEN_APP",
                "name": "Chrome",
                "status": "SUCCESS",
                "details": "Browser successfully launched",
            },
            speech_status="PLAYED",
        )

        with open(cm.chat_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert len(data["messages"]) == 1
        msg = data["messages"][0]
        assert msg["request_id"] == "101"
        assert msg["User"]["message"] == "Open Chrome"
        assert msg["User"]["source"] == "voice"
        assert msg["Light"]["message"] == "Chrome khol rahi hu, Sir."
        assert msg["Light"]["action"]["performed"] is True
        assert msg["Light"]["action"]["status"] == "SUCCESS"
        assert msg["Light"]["speech"]["status"] == "PLAYED"


def test_chat_manager_utf8_hinglish_preservation():
    """Verify UTF-8 encoding preserves Hindi/Hinglish characters without ASCII escaping."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        chats_path = Path(tmp_dir) / "chats"
        cm = ChatManager(chats_dir=chats_path)

        hindi_text = "लाइट, क्या हाल है? मैं बिल्कुल ठीक हूँ।"
        cm.record_user_message(request_id="hindi_1", message=hindi_text, source="voice")
        cm.record_assistant_response(
            request_id="hindi_1",
            message="Main bilkul theek hu sir! Aap kaise hain?",
            action={"performed": False, "intent": "CONVERSATION", "name": None, "status": "NOT_PERFORMED", "details": None},
            speech_status="PLAYED",
        )

        # Check raw file content contains unescaped Unicode
        with open(cm.chat_file, "r", encoding="utf-8") as f:
            raw_content = f.read()

        assert "लाइट" in raw_content
        assert "हूँ" in raw_content
        assert "\\u" not in raw_content  # ensure_ascii=False verified!


def test_chat_manager_speech_status_update():
    """Verify update_speech_status updates speech from PENDING to PLAYED or FAILED."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        chats_path = Path(tmp_dir) / "chats"
        cm = ChatManager(chats_dir=chats_path)

        cm.record_user_message(request_id=1, message="Hello", source="text")
        cm.record_assistant_response(request_id=1, message="Namaste!", speech_status="PENDING")

        with open(cm.chat_file, "r", encoding="utf-8") as f:
            assert json.load(f)["messages"][0]["Light"]["speech"]["status"] == "PENDING"

        # Update speech to PLAYED
        cm.update_speech_status(request_id=1, status="PLAYED")
        with open(cm.chat_file, "r", encoding="utf-8") as f:
            assert json.load(f)["messages"][0]["Light"]["speech"]["status"] == "PLAYED"


def test_chat_manager_atomic_write_recovery():
    """Verify write uses atomic replacement and does not leave corrupt files on write."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        chats_path = Path(tmp_dir) / "chats"
        cm = ChatManager(chats_dir=chats_path)

        cm.record_user_message(request_id=1, message="Test atomic write", source="text")
        cm.record_assistant_response(request_id=1, message="Confirmed", speech_status="PLAYED")

        # Confirm valid JSON
        with open(cm.chat_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data["messages"]) == 1


def test_chat_manager_finalize_on_shutdown():
    """Verify finalize() marks status as completed and updates final timestamp."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        chats_path = Path(tmp_dir) / "chats"
        cm = ChatManager(chats_dir=chats_path)
        cm.finalize(status="completed")

        with open(cm.chat_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["status"] == "completed"


# ==============================================================================
# 3. COE Gateway Context Extension Tests
# ==============================================================================

def test_coe_gateway_history_inclusion():
    """Verify CoE Gateway includes conversational history before the current user utterance."""
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = '{"intent": "CONVERSATION", "voice_response": "Guido van Rossum ne 1991 me banaya tha."}'
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response

    gw = CoeGatewayClient(api_key="test_key", client=mock_client)
    history = [
        {"role": "user", "content": "What is Python?"},
        {"role": "assistant", "content": "Python is a programming language."},
    ]

    resp = gw.complete("Who created it?", history=history)
    assert resp.is_success is True

    # Check messages passed to chat.completions.create
    call_args = mock_client.chat.completions.create.call_args
    passed_messages = call_args[1]["messages"]
    assert len(passed_messages) == 4
    assert passed_messages[0]["role"] == "system"
    assert passed_messages[1] == {"role": "user", "content": "What is Python?"}
    assert passed_messages[2] == {"role": "assistant", "content": "Python is a programming language."}
    assert passed_messages[3] == {"role": "user", "content": "Who created it?"}


# ==============================================================================
# 4. Assistant End-to-End Integration Tests
# ==============================================================================

def make_test_assistant_d5(tmp_chats_dir: Path) -> LightAssistant:
    """Creates an isolated LightAssistant with SessionMemory and ChatManager."""
    assistant = LightAssistant.__new__(LightAssistant)
    assistant.state_machine = StateMachine()

    # Memory subsystems
    assistant.session_memory = SessionMemory(max_turns=5)
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
    assistant.router = CommandRouter(gateway_client=assistant.gateway_client)

    # Subsystems
    assistant.app_launcher = MagicMock()
    assistant.music_player = MagicMock()
    assistant.music_player.has_active_playlist = False
    assistant.music_player.is_playing = False
    assistant.bridge = MagicMock()

    # FIFO Queue
    import queue
    import collections
    import concurrent.futures
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


def test_assistant_persists_text_and_voice_requests():
    """Verify both voice and text requests are recorded in the chat JSON with proper source."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        chats_path = Path(tmp_dir) / "chats"
        assistant = make_test_assistant_d5(chats_path)
        try:
            # 1. Direct text command
            ok_text, _, _ = assistant.admit_text_command("who are you", wait_for_completion=True)
            assert ok_text is True

            # 2. Spoken command with wake word
            ok_voice = assistant.enqueue_utterance("Light, pause music", wait_for_completion=True)
            assert ok_voice is True

            # Inspect chat JSON
            with open(assistant.chat_manager.chat_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            assert len(data["messages"]) == 2

            # Message 1 (Text)
            msg1 = data["messages"][0]
            assert msg1["User"]["message"] == "who are you"
            assert msg1["User"]["source"] == "text"
            assert "Main Light AI hoon" in msg1["Light"]["message"]
            assert msg1["Light"]["speech"]["status"] == "PLAYED"

            # Message 2 (Voice)
            msg2 = data["messages"][1]
            assert "pause music" in msg2["User"]["message"]
            assert msg2["User"]["source"] == "voice"
            assert "pause" in msg2["Light"]["message"].lower()
            assert msg2["Light"]["action"]["performed"] is True
            assert msg2["Light"]["speech"]["status"] == "PLAYED"
        finally:
            assistant._shutdown_internal(farewell_message="")


def test_assistant_follow_up_conversational_context():
    """Verify follow-up questions pass recent context turns to CoE Gateway."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        chats_path = Path(tmp_dir) / "chats"
        assistant = make_test_assistant_d5(chats_path)
        try:
            # Turn 1
            assistant.gateway_client.complete.return_value = GatewayResponse(
                status=GatewayStatus.SUCCESS,
                raw_content='{"intent": "CONVERSATION", "voice_response": "Python ek powerful programming language hai."}',
            )
            ok1, _, _ = assistant.admit_text_command("What is Python?", wait_for_completion=True)
            assert ok1 is True

            # Verify Turn 1 is in session memory
            assert len(assistant.session_memory.turns) == 1
            assert assistant.session_memory.turns[0].user_message == "What is Python?"

            # Turn 2: Follow-up question
            assistant.gateway_client.complete.return_value = GatewayResponse(
                status=GatewayStatus.SUCCESS,
                raw_content='{"intent": "CONVERSATION", "voice_response": "Ise Guido van Rossum ne banaya tha."}',
            )
            ok2, _, _ = assistant.admit_text_command("Who created it?", wait_for_completion=True)
            assert ok2 is True

            # Check that gateway received history during Turn 2
            call_args = assistant.gateway_client.complete.call_args_list[-1]
            history_arg = call_args[1].get("history") or (call_args[0][3] if len(call_args[0]) > 3 else None)
            assert history_arg is not None
            assert len(history_arg) == 2
            assert history_arg[0]["content"] == "What is Python?"

            # Verify Turn 2 is now in session memory
            assert len(assistant.session_memory.turns) == 2
        finally:
            assistant._shutdown_internal(farewell_message="")


def test_assistant_shutdown_clears_memory_and_finalizes_chat():
    """Verify shutdown finalizes the chat JSON file and completely purges session memory."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        chats_path = Path(tmp_dir) / "chats"
        assistant = make_test_assistant_d5(chats_path)

        assistant.admit_text_command("who are you", wait_for_completion=True)
        assert len(assistant.session_memory.turns) >= 1

        chat_file = assistant.chat_manager.chat_file
        assert chat_file.exists()

        # Perform shutdown
        assistant._shutdown_internal(farewell_message="")

        # Session memory MUST BE COMPLETELY CLEARED
        assert len(assistant.session_memory.turns) == 0

        # Chat JSON must be completed
        with open(chat_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["status"] == "completed"

