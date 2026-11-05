"""
Chat Manager module for LIGHT AI V1.0.
Creates and maintains persistent JSON chat files inside 'chats/<uuid>.json'.
Handles atomic file writes, crash resilience, UTF-8/Hinglish preservation,
detailed action status tracking, and actual TTS playback lifecycle synchronization.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
from typing import Dict, Any, List, Optional
import uuid

from config.settings import CHATS_DIR, BASE_DIR
from utils.logger import logger


class ChatManager:
    """
    Manages persistent JSON chat files for LIGHT AI.
    Each application startup creates a new unique UUID chat file representing that session.
    All disk writes are atomic via temporary file replacement.
    """

    def __init__(
        self,
        chats_dir: Optional[Path] = None,
        chat_id: Optional[str] = None,
    ):
        self.chats_dir: Path = Path(chats_dir) if chats_dir is not None else CHATS_DIR
        self.chats_dir.mkdir(parents=True, exist_ok=True)

        self.chat_id: str = str(chat_id) if chat_id else str(uuid.uuid4())
        self.chat_file: Path = self.chats_dir / f"{self.chat_id}.json"
        self._lock = threading.Lock()

        now_iso = datetime.now(timezone.utc).isoformat()
        self._data: Dict[str, Any] = {
            "chat_id": self.chat_id,
            "created_at": now_iso,
            "updated_at": now_iso,
            "status": "active",
            "messages": [],
        }

        # Initialize the file atomically on startup
        self._save_atomic()
        logger.info(f"[CHAT_MANAGER] Initialized new persistent chat session: {self.chat_file}")

    def _save_atomic(self) -> bool:
        """
        Thread-safely writes the current chat session to disk using atomic temporary file replacement.
        Ensures UTF-8 encoding without ASCII escaping (ensure_ascii=False).
        """
        with self._lock:
            self._data["updated_at"] = datetime.now(timezone.utc).isoformat()
            temp_path = self.chats_dir / f".tmp_{self.chat_id}_{uuid.uuid4().hex[:6]}.json"
            try:
                content = json.dumps(self._data, ensure_ascii=False, indent=2)
                with open(temp_path, "w", encoding="utf-8") as f:
                    f.write(content)
                    f.flush()
                    os.fsync(f.fileno())

                os.replace(temp_path, self.chat_file)
                return True
            except Exception as e:
                logger.error(f"[CHAT_MANAGER] Failed to atomically save chat file '{self.chat_file}': {e}")
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except Exception:
                        pass
                return False

    def _find_message_entry(self, req_id_str: str) -> Optional[Dict[str, Any]]:
        """Finds an existing message entry by stringified request_id (must be called with _lock held)."""
        for item in self._data["messages"]:
            if str(item.get("request_id")) == req_id_str:
                return item
        return None

    def record_user_message(
        self,
        request_id: Any,
        message: str,
        source: str = "voice",
        timestamp: Optional[str] = None,
    ) -> None:
        """
        Records an admitted user utterance or command in the persistent chat file.
        Idempotent: updates existing entry if request_id already exists.
        """
        req_id_str = str(request_id)
        now_iso = timestamp or datetime.now(timezone.utc).isoformat()
        clean_msg = (message or "").strip()
        clean_source = "text" if str(source).lower() == "text" else "voice"

        with self._lock:
            existing = self._find_message_entry(req_id_str)
            if existing:
                existing["User"] = {
                    "message": clean_msg,
                    "timestamp": now_iso,
                    "source": clean_source,
                }
            else:
                new_entry: Dict[str, Any] = {
                    "request_id": req_id_str,
                    "User": {
                        "message": clean_msg,
                        "timestamp": now_iso,
                        "source": clean_source,
                    },
                    "Light": {
                        "message": "",
                        "timestamp": now_iso,
                        "action": {
                            "performed": False,
                            "intent": "UNKNOWN",
                            "name": None,
                            "status": "NOT_PERFORMED",
                            "details": None,
                        },
                        "speech": {
                            "status": "PENDING",
                        },
                    },
                }
                self._data["messages"].append(new_entry)

        self._save_atomic()
        logger.debug(f"[CHAT_MANAGER] Recorded user message [req_id={req_id_str}, src={clean_source}]: '{clean_msg[:40]}'")

    def record_assistant_response(
        self,
        request_id: Any,
        message: str,
        action: Optional[Dict[str, Any]] = None,
        speech_status: str = "PENDING",
        timestamp: Optional[str] = None,
    ) -> None:
        """
        Records LIGHT AI's response text, action execution details, and initial speech status.
        """
        req_id_str = str(request_id)
        now_iso = timestamp or datetime.now(timezone.utc).isoformat()
        clean_msg = (message or "").strip()

        default_action = {
            "performed": False,
            "intent": "CONVERSATION",
            "name": None,
            "status": "NOT_PERFORMED",
            "details": None,
        }
        action_payload = dict(action) if action else default_action

        with self._lock:
            entry = self._find_message_entry(req_id_str)
            if not entry:
                entry = {
                    "request_id": req_id_str,
                    "User": {
                        "message": "",
                        "timestamp": now_iso,
                        "source": "unknown",
                    },
                    "Light": {},
                }
                self._data["messages"].append(entry)

            entry["Light"] = {
                "message": clean_msg,
                "timestamp": now_iso,
                "action": action_payload,
                "speech": {
                    "status": speech_status,
                },
            }

        self._save_atomic()
        logger.debug(
            f"[CHAT_MANAGER] Recorded assistant response [req_id={req_id_str}]: "
            f"'{clean_msg[:40]}' (action={action_payload.get('intent')}, speech={speech_status})"
        )

    def update_action_status(
        self,
        request_id: Any,
        status: str,
        details: Optional[str] = None,
        name: Optional[str] = None,
        performed: Optional[bool] = None,
    ) -> None:
        """
        Updates the action execution outcome (SUCCESS, FAILED, CANCELLED, REJECTED)
        for a specific request after async execution completes.
        """
        req_id_str = str(request_id)
        with self._lock:
            entry = self._find_message_entry(req_id_str)
            if entry and "Light" in entry and "action" in entry["Light"]:
                action_obj = entry["Light"]["action"]
                if performed is not None:
                    action_obj["performed"] = bool(performed)
                if not action_obj.get("performed", False) and status == "SUCCESS":
                    # Non-action conversational turns retain NOT_PERFORMED
                    pass
                else:
                    action_obj["status"] = status
                if details is not None:
                    action_obj["details"] = details
                if name is not None:
                    action_obj["name"] = name

        self._save_atomic()

    def update_speech_status(self, request_id: Any, status: str) -> None:
        """
        Updates the speech playback outcome (PLAYED, FAILED, CANCELLED)
        based on actual TTSEngine callbacks.
        """
        req_id_str = str(request_id)
        with self._lock:
            entry = self._find_message_entry(req_id_str)
            if entry and "Light" in entry and "speech" in entry["Light"]:
                entry["Light"]["speech"]["status"] = status

        self._save_atomic()
        logger.debug(f"[CHAT_MANAGER] Updated speech status [req_id={req_id_str}]: {status}")

    def finalize(self, status: str = "completed") -> None:
        """
        Finalizes the chat session on assistant shutdown.
        Marks overall session status and transitions any unplayed speech to CANCELLED.
        """
        with self._lock:
            self._data["status"] = status
            for msg in self._data["messages"]:
                light = msg.get("Light", {})
                speech = light.get("speech", {})
                if speech.get("status") == "PENDING":
                    speech["status"] = "CANCELLED"
                action = light.get("action", {})
                if action.get("status") == "PENDING":
                    action["status"] = "CANCELLED"

        self._save_atomic()
        logger.info(f"[CHAT_MANAGER] Finalized chat session '{self.chat_id}' with status '{status}'.")

