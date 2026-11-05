"""
CoE AI Gateway Client for Light AI V1.0.
Provides an isolated, OpenAI-compatible client wrapper for the college CoE AI Gateway.
Handles communication, timeouts, connection drops, authentication failures,
and returns structured data responses.
Never executes actions, code, shell commands, or external processes.
"""

import collections
from dataclasses import dataclass
from enum import Enum, auto
import threading
import time
from typing import Dict, Any, List, Optional, Callable
import openai

from config.settings import (
    COE_AI_BASE_URL,
    COE_AI_MODEL,
    COE_AI_KEY,
    COE_AI_TIMEOUT_SECONDS,
    COE_AI_CONTEXT_CAPACITY,
)
from utils.logger import logger


class GatewayStatus(Enum):
    """Enumeration of possible CoE AI Gateway communication outcomes."""
    SUCCESS = auto()
    EMPTY_RESPONSE = auto()
    INVALID_RESPONSE = auto()
    TIMEOUT = auto()
    CONNECTION_FAILURE = auto()
    AUTHENTICATION_FAILURE = auto()
    RATE_LIMIT = auto()
    API_ERROR = auto()
    NOT_CONFIGURED = auto()


@dataclass
class GatewayResponse:
    """Predictable response structure returned by CoE AI Gateway client."""
    status: GatewayStatus
    raw_content: Optional[str] = None
    error_message: Optional[str] = None
    model: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    latency_ms: Optional[int] = None

    @property
    def is_success(self) -> bool:
        """Returns True if the gateway call was successful and produced content."""
        return self.status == GatewayStatus.SUCCESS and bool(self.raw_content)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the response for structured logging or downstream processing."""
        return {
            "status": self.status.name,
            "is_success": self.is_success,
            "raw_content": self.raw_content,
            "error_message": self.error_message,
            "model": self.model,
            "usage": self.usage,
            "latency_ms": self.latency_ms,
        }


DEFAULT_SYSTEM_PROMPT: str = (
    "You are Light AI (version 1.0), a friendly, polite, and smart FEMALE desktop assistant created by Sarthak Sir.\n\n"
    "GENDER & LINGUISTIC RULES (CRITICAL):\n"
    "1. ALWAYS speak as a FEMALE using proper feminine Hindi grammar endings:\n"
    '   - Prefer forms like: "karungi", "bol rahi hu", "khol rahi hu", "kar sakti hu", "aayi hu".\n'
    '   - NEVER use masculine verb forms like: "karunga", "bol raha hu", "khol raha hu", "kar sakta hu".\n'
    "2. Speak in natural, everyday Indian Hinglish (a polite mix of simple Hindi and English words).\n"
    '   - Example: "Ji sir, main abhi Notepad open kar rahi hu."\n'
    '   - Example: "Main bilkul theek hu sir! Aap kaise hain?"\n'
    "3. Spoken responses must be concise (1-3 short sentences), natural, polite, and suitable for direct voice output.\n\n"
    "YOUR TASK:\n"
    "Analyze the user's spoken input and output ONLY a valid JSON object matching one of the two categories:\n\n"
    "CATEGORY 1: NORMAL QUESTIONS, EXPLANATIONS & CONVERSATION\n"
    "When the user asks general questions, seeks explanations, chats, or asks about concepts (e.g., 'what is AI', 'explain machine learning', 'tell me a fun fact', 'who created you'):\n"
    "Set intent to 'CONVERSATION' and provide the clear, conversational answer in 'voice_response'. All action fields must be literal null.\n"
    "Example:\n"
    "{\n"
    '  "intent": "CONVERSATION",\n'
    '  "app_name": null,\n'
    '  "website": null,\n'
    '  "browser": null,\n'
    '  "query": null,\n'
    '  "contact": null,\n'
    '  "initial_message": null,\n'
    '  "needs_clarification": false,\n'
    '  "clarification_prompt": null,\n'
    '  "voice_response": "Artificial Intelligence yaani AI aisi technology hai jisse computers insaan ki tarah soch aur samajh sakte hain."\n'
    "}\n\n"
    "CATEGORY 2: COMMANDS & SYSTEM ACTIONS\n"
    "When the user wants to perform an action on the computer, choose the appropriate intent:\n"
    '- OPEN_APP: app_name ("chrome", "brave", "edge", "notepad", "vscode", "whatsapp")\n'
    '- OPEN_WEBSITE: website ("youtube", "google", "whatsapp"), optional browser ("brave", "chrome", "edge")\n'
    "- SEARCH_GOOGLE: query (string), optional browser\n"
    "- SEARCH_YOUTUBE: query (string), optional browser\n"
    "- WHATSAPP_START: contact (string), optional initial_message (string)\n"
    "- IDENTITY: Details about Light AI and creator Sarthak Sir\n"
    "- CLARIFICATION: Missing parameters for action commands\n"
    "- UNKNOWN: Truly unrecognized input\n\n"
    "RULES & SAFETY INVARIANTS:\n"
    "1. Output ONLY the raw JSON object. Do not include markdown codeblocks, backticks, or conversational commentary outside JSON.\n"
    '2. For unused fields, ALWAYS use JSON null literal (null), NEVER the string "null".\n'
    "3. Do not invent missing search queries. If query is missing, set needs_clarification to true.\n"
    "4. Never execute actions or generate code/commands. Only select supported intents."
)


class CoeGatewayClient:
    """
    Isolated client wrapper for OpenAI-compatible CoE AI Gateway (Qwen 35B).
    Reads settings by default while permitting full dependency injection for testability.
    Enforces a strict 0-retry policy to avoid voice-assistant latency hangs.
    Provides thread-safe AI runtime telemetry and performance tracking.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,
        client: Optional[openai.OpenAI] = None,
    ):
        self.base_url: str = (base_url if base_url is not None else COE_AI_BASE_URL).strip()
        self.model: str = (model if model is not None else COE_AI_MODEL).strip()
        self._api_key: str = (api_key if api_key is not None else COE_AI_KEY).strip()
        self.timeout: float = timeout if timeout is not None else COE_AI_TIMEOUT_SECONDS

        self.provider: str = "CoE AI Gateway"
        self.configured_model: str = self.model
        self.resolved_model: Optional[str] = None
        self.on_state_change: Optional[Callable[[Dict[str, Any]], None]] = None

        # Thread-safe session performance and telemetry state
        self._telemetry_lock = threading.Lock()
        self._current_state: str = "IDLE"
        self._in_flight_count: int = 0
        self._success_count: int = 0
        self._failure_count: int = 0
        self._last_latency_ms: Optional[int] = None
        self._last_successful_latency_ms: Optional[int] = None
        self._recent_latencies: collections.deque[int] = collections.deque(maxlen=20)
        self._last_success_timestamp: Optional[float] = None
        self._last_status: Optional[GatewayStatus] = None
        self._last_error_category: Optional[str] = None
        self._last_tokens: Optional[Dict[str, Optional[int]]] = None
        self._session_tokens: Dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        self._last_history_included: bool = False

        self._client: Optional[openai.OpenAI] = client
        if self._client is None and self.is_configured:
            try:
                self._client = openai.OpenAI(
                    base_url=self.base_url,
                    api_key=self._api_key,
                    timeout=self.timeout,
                    max_retries=0,  # Strict single attempt to bound conversational latency
                )
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {type(e).__name__}")
                self._client = None

    @property
    def is_configured(self) -> bool:
        """Checks if the client has a non-empty API key and valid base URL."""
        return bool(self._api_key and self.base_url)

    def _notify_state_change(self) -> None:
        """Dispatches an asynchronous or protected telemetry snapshot notification."""
        cb = self.on_state_change
        if cb and callable(cb):
            try:
                snap = self.get_telemetry_snapshot()
                cb(snap)
            except Exception as e:
                logger.debug(f"[GATEWAY] Error invoking on_state_change callback: {e}")

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.0,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> GatewayResponse:
        """
        Executes a chat completion request against the gateway.
        Never exposes the API key or raw credentials in error messages or logs.
        """
        if not self.is_configured or self._client is None:
            logger.debug("CoE AI Gateway is not configured. Request skipped.")
            with self._telemetry_lock:
                self._last_status = GatewayStatus.NOT_CONFIGURED
                self._last_error_category = "NOT_CONFIGURED"
            return GatewayResponse(
                status=GatewayStatus.NOT_CONFIGURED,
                error_message="CoE AI Gateway is not configured (missing key or base URL).",
                latency_ms=0,
            )

        if not messages or not isinstance(messages, list):
            with self._telemetry_lock:
                self._last_status = GatewayStatus.INVALID_RESPONSE
                self._last_error_category = "INVALID_RESPONSE"
            return GatewayResponse(
                status=GatewayStatus.INVALID_RESPONSE,
                error_message="Invalid or empty messages payload provided.",
                latency_ms=0,
            )

        format_kwarg: Dict[str, Any] = {}
        if response_format is not None:
            format_kwarg["response_format"] = response_format

        # Transition to PROCESSING under lock
        with self._telemetry_lock:
            self._in_flight_count += 1
            self._current_state = "PROCESSING"
        self._notify_state_change()

        t0 = time.perf_counter()
        gateway_resp: Optional[GatewayResponse] = None

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                **format_kwarg,
            )
            latency_ms = max(1, round((time.perf_counter() - t0) * 1000))

            if not response or not getattr(response, "choices", None):
                logger.warning("CoE AI Gateway returned response with no choices.")
                with self._telemetry_lock:
                    self._failure_count += 1
                    self._last_latency_ms = latency_ms
                    self._last_status = GatewayStatus.EMPTY_RESPONSE
                    self._last_error_category = "EMPTY_RESPONSE"
                gateway_resp = GatewayResponse(
                    status=GatewayStatus.EMPTY_RESPONSE,
                    error_message="Gateway response contained no choices.",
                    model=getattr(response, "model", self.model),
                    latency_ms=latency_ms,
                )
                return gateway_resp

            choice = response.choices[0]
            message = getattr(choice, "message", None)
            content = getattr(message, "content", None) if message else None

            if not content or not str(content).strip():
                logger.warning("CoE AI Gateway choice message content was empty.")
                with self._telemetry_lock:
                    self._failure_count += 1
                    self._last_latency_ms = latency_ms
                    self._last_status = GatewayStatus.EMPTY_RESPONSE
                    self._last_error_category = "EMPTY_RESPONSE"
                gateway_resp = GatewayResponse(
                    status=GatewayStatus.EMPTY_RESPONSE,
                    error_message="Gateway choice content was empty or null.",
                    model=getattr(response, "model", self.model),
                    latency_ms=latency_ms,
                )
                return gateway_resp

            # Extract token usage safely
            usage_dict = None
            if getattr(response, "usage", None):
                try:
                    usage = response.usage
                    p_tok = getattr(usage, "prompt_tokens", None)
                    c_tok = getattr(usage, "completion_tokens", None)
                    t_tok = getattr(usage, "total_tokens", None)
                    usage_dict = {
                        "prompt_tokens": p_tok if isinstance(p_tok, int) else None,
                        "completion_tokens": c_tok if isinstance(c_tok, int) else None,
                        "total_tokens": t_tok if isinstance(t_tok, int) else None,
                    }
                except Exception:
                    usage_dict = None

            resolved_m = getattr(response, "model", self.model)
            with self._telemetry_lock:
                self._success_count += 1
                self._last_latency_ms = latency_ms
                self._last_successful_latency_ms = latency_ms
                self._recent_latencies.append(latency_ms)
                self._last_success_timestamp = time.time()
                self._last_status = GatewayStatus.SUCCESS
                self._last_error_category = None
                if resolved_m:
                    self.resolved_model = str(resolved_m)
                self._last_tokens = usage_dict
                if usage_dict:
                    pt = usage_dict.get("prompt_tokens")
                    ct = usage_dict.get("completion_tokens")
                    tt = usage_dict.get("total_tokens")
                    if isinstance(pt, int) and pt > 0:
                        self._session_tokens["prompt_tokens"] += pt
                    if isinstance(ct, int) and ct > 0:
                        self._session_tokens["completion_tokens"] += ct
                    if isinstance(tt, int) and tt > 0:
                        self._session_tokens["total_tokens"] += tt

            gateway_resp = GatewayResponse(
                status=GatewayStatus.SUCCESS,
                raw_content=str(content).strip(),
                model=getattr(response, "model", self.model),
                usage=usage_dict,
                latency_ms=latency_ms,
            )
            return gateway_resp

        except openai.APITimeoutError:
            latency_ms = max(1, round((time.perf_counter() - t0) * 1000))
            logger.warning(f"CoE AI Gateway request timed out after {self.timeout}s.")
            with self._telemetry_lock:
                self._failure_count += 1
                self._last_latency_ms = latency_ms
                self._last_status = GatewayStatus.TIMEOUT
                self._last_error_category = "TIMEOUT"
            gateway_resp = GatewayResponse(
                status=GatewayStatus.TIMEOUT,
                error_message=f"Gateway request timed out after {self.timeout} seconds.",
                latency_ms=latency_ms,
            )
            return gateway_resp

        except openai.APIConnectionError:
            latency_ms = max(1, round((time.perf_counter() - t0) * 1000))
            logger.warning("CoE AI Gateway connection failure: host unreachable or network drop.")
            with self._telemetry_lock:
                self._failure_count += 1
                self._last_latency_ms = latency_ms
                self._last_status = GatewayStatus.CONNECTION_FAILURE
                self._last_error_category = "CONNECTION_FAILURE"
            gateway_resp = GatewayResponse(
                status=GatewayStatus.CONNECTION_FAILURE,
                error_message="Gateway connection failure: server unreachable or network error.",
                latency_ms=latency_ms,
            )
            return gateway_resp

        except openai.AuthenticationError:
            latency_ms = max(1, round((time.perf_counter() - t0) * 1000))
            logger.error("CoE AI Gateway authentication failed (HTTP 401).")
            with self._telemetry_lock:
                self._failure_count += 1
                self._last_latency_ms = latency_ms
                self._last_status = GatewayStatus.AUTHENTICATION_FAILURE
                self._last_error_category = "AUTHENTICATION_FAILURE"
            gateway_resp = GatewayResponse(
                status=GatewayStatus.AUTHENTICATION_FAILURE,
                error_message="Gateway authentication failed: invalid or unauthorized API key.",
                latency_ms=latency_ms,
            )
            return gateway_resp

        except openai.RateLimitError:
            latency_ms = max(1, round((time.perf_counter() - t0) * 1000))
            logger.warning("CoE AI Gateway rate limit exceeded (HTTP 429).")
            with self._telemetry_lock:
                self._failure_count += 1
                self._last_latency_ms = latency_ms
                self._last_status = GatewayStatus.RATE_LIMIT
                self._last_error_category = "RATE_LIMIT"
            gateway_resp = GatewayResponse(
                status=GatewayStatus.RATE_LIMIT,
                error_message="Gateway rate limit reached or server congested.",
                latency_ms=latency_ms,
            )
            return gateway_resp

        except (openai.APIStatusError, openai.APIError) as e:
            latency_ms = max(1, round((time.perf_counter() - t0) * 1000))
            status_code = getattr(e, "status_code", "Unknown")
            logger.error(f"CoE AI Gateway returned API error: HTTP {status_code}.")
            with self._telemetry_lock:
                self._failure_count += 1
                self._last_latency_ms = latency_ms
                self._last_status = GatewayStatus.API_ERROR
                self._last_error_category = f"HTTP_{status_code}"
            gateway_resp = GatewayResponse(
                status=GatewayStatus.API_ERROR,
                error_message=f"Gateway returned HTTP {status_code} error.",
                latency_ms=latency_ms,
            )
            return gateway_resp

        except Exception as e:
            latency_ms = max(1, round((time.perf_counter() - t0) * 1000))
            err_type = type(e).__name__
            logger.error(f"Unexpected error during CoE AI Gateway communication: {err_type}")
            with self._telemetry_lock:
                self._failure_count += 1
                self._last_latency_ms = latency_ms
                self._last_status = GatewayStatus.API_ERROR
                self._last_error_category = err_type
            gateway_resp = GatewayResponse(
                status=GatewayStatus.API_ERROR,
                error_message=f"Unexpected error: {err_type}",
                latency_ms=latency_ms,
            )
            return gateway_resp

        finally:
            with self._telemetry_lock:
                self._in_flight_count = max(0, self._in_flight_count - 1)
                if self._in_flight_count == 0:
                    self._current_state = "IDLE" if (self._last_status == GatewayStatus.SUCCESS) else "ERROR"
            self._notify_state_change()

    def complete(
        self,
        user_utterance: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> GatewayResponse:
        """
        Convenience method to request structured intent JSON for a user speech utterance.
        Configures the default system prompt, optional prior conversational context,
        and requests JSON object format.
        """
        clean_utterance = (user_utterance or "").strip()
        if not clean_utterance:
            return GatewayResponse(
                status=GatewayStatus.EMPTY_RESPONSE,
                error_message="User utterance is empty.",
            )

        messages = [
            {"role": "system", "content": system_prompt or DEFAULT_SYSTEM_PROMPT},
        ]
        clean_history = bool(history and isinstance(history, list) and len(history) > 0)
        with self._telemetry_lock:
            self._last_history_included = clean_history

        if clean_history:
            for h in history:
                if isinstance(h, dict) and "role" in h and "content" in h:
                    messages.append({"role": h["role"], "content": str(h["content"])})

        messages.append({"role": "user", "content": clean_utterance})

        return self.chat(
            messages=messages,
            temperature=temperature,
            response_format={"type": "json_object"},
        )

    def get_telemetry_snapshot(self) -> Dict[str, Any]:
        """
        Thread-safe snapshot of AI Core telemetry without sensitive credentials or prompts.
        """
        with self._telemetry_lock:
            avg_lat = (
                round(sum(self._recent_latencies) / len(self._recent_latencies), 1)
                if self._recent_latencies
                else None
            )

            if not self.is_configured:
                gw_status = "NOT_CONFIGURED"
            elif self._current_state == "PROCESSING":
                gw_status = "PROCESSING"
            elif self._last_error_category:
                gw_status = "ERROR"
            elif self._success_count > 0:
                gw_status = "ONLINE"
            else:
                gw_status = "STANDBY"

            capacity = COE_AI_CONTEXT_CAPACITY
            remaining = None
            utilization = None
            if capacity is not None and isinstance(capacity, int) and capacity > 0:
                if self._last_tokens and self._last_tokens.get("total_tokens") is not None:
                    tot = self._last_tokens["total_tokens"]
                    remaining = max(0, capacity - tot)
                    utilization = round((tot / capacity) * 100, 2)

            return {
                "provider": self.provider,
                "base_url": self.base_url,
                "configured_model": self.model,
                "resolved_model": self.resolved_model,
                "is_configured": self.is_configured,
                "gateway_status": gw_status,
                "runtime_state": self._current_state,
                "in_flight_requests": self._in_flight_count,
                "last_request_status": self._last_status.name if self._last_status else None,
                "last_error_category": self._last_error_category,
                "last_request_latency_ms": self._last_latency_ms,
                "last_successful_latency_ms": self._last_successful_latency_ms,
                "avg_latency_ms": avg_lat,
                "recent_latencies_ms": list(self._recent_latencies),
                "success_count": self._success_count,
                "failure_count": self._failure_count,
                "last_success_timestamp": self._last_success_timestamp,
                "last_tokens": dict(self._last_tokens) if self._last_tokens else None,
                "session_tokens": dict(self._session_tokens),
                "context_capacity": capacity,
                "remaining_tokens": remaining,
                "utilization_percentage": utilization,
                "history_included": self._last_history_included,
            }
