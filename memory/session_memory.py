"""
Session Memory module for LIGHT AI V1.0.
Stores conversational context in RAM only during the current application run.
Provides recent conversation turns to the CoE Gateway for multi-turn conversational follow-ups.
Cleared completely on application shutdown; never loads disk history on startup.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import collections
import threading
from typing import List, Dict, Any, Optional

from config.settings import SESSION_MEMORY_MAX_TURNS
from utils.logger import logger


@dataclass
class SessionTurn:
    """Represents a single conversational exchange between User and LIGHT AI."""
    user_message: str
    assistant_message: str
    timestamp: str
    request_id: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_message": self.user_message,
            "assistant_message": self.assistant_message,
            "timestamp": self.timestamp,
            "request_id": self.request_id,
        }


class SessionMemory:
    """
    Thread-safe in-memory store for recent conversation turns.
    Enforces a strict configurable FIFO turn limit to avoid unbounded token accumulation.
    Is isolated strictly to RAM for the current application process.
    """

    def __init__(self, max_turns: int = SESSION_MEMORY_MAX_TURNS):
        self.max_turns: int = max(1, int(max_turns))
        self._turns: collections.deque[SessionTurn] = collections.deque(maxlen=self.max_turns)
        self._lock = threading.Lock()

    @property
    def turns(self) -> List[SessionTurn]:
        """Returns a thread-safe snapshot list of currently active turns in chronological order."""
        with self._lock:
            return list(self._turns)

    def add_turn(
        self,
        user_message: str,
        assistant_message: str,
        request_id: Optional[Any] = None,
        timestamp: Optional[str] = None,
    ) -> None:
        """
        Adds a completed conversation turn to session memory.
        Automatically evicts oldest turns if max_turns is exceeded.
        """
        clean_user = (user_message or "").strip()
        clean_assistant = (assistant_message or "").strip()
        if not clean_user and not clean_assistant:
            return

        ts = timestamp or datetime.now(timezone.utc).isoformat()
        turn = SessionTurn(
            user_message=clean_user,
            assistant_message=clean_assistant,
            timestamp=ts,
            request_id=request_id,
        )

        with self._lock:
            self._turns.append(turn)
            logger.debug(
                f"[MEMORY] Added session turn [req_id={request_id}]: "
                f"'{clean_user[:40]}...' -> '{clean_assistant[:40]}...' (active_turns={len(self._turns)}/{self.max_turns})"
            )

    def get_context_for_gateway(self) -> List[Dict[str, str]]:
        """
        Formats recent turns as an OpenAI-compatible message history list:
        [
            {"role": "user", "content": "..."},
            {"role": "assistant", "content": "..."},
            ...
        ]
        """
        with self._lock:
            context: List[Dict[str, str]] = []
            for turn in self._turns:
                context.append({"role": "user", "content": turn.user_message})
                context.append({"role": "assistant", "content": turn.assistant_message})
            return context

    def clear(self) -> None:
        """Purges all turns from memory on shutdown."""
        with self._lock:
            count = len(self._turns)
            self._turns.clear()
            logger.info(f"[MEMORY] Session memory cleared ({count} turns purged).")

