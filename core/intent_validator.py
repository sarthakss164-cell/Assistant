"""
Local Intent Validator & Schema Engine for Light AI V1.0.
Acts as the authoritative, deterministic security gatekeeper for natural language understanding.
Validates input structure, types, field combinations, allowlisted applications,
supported browsers, and supported websites before any intent can be dispatched.
Never executes code, shell commands, or external actions.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional, Set, Tuple, Union

from config.settings import ALLOWLIST_FILE, PREFERRED_BROWSER
from utils.logger import logger

# Approved Schema Constants
SUPPORTED_INTENTS: Set[str] = {
    "OPEN_APP",
    "OPEN_WEBSITE",
    "SEARCH_GOOGLE",
    "SEARCH_YOUTUBE",
    "WHATSAPP_START",
    "IDENTITY",
    "CLARIFICATION",
    "CONVERSATION",
    "UNKNOWN",
}

ALLOWED_KEYS: Set[str] = {
    "intent",
    "app_name",
    "website",
    "browser",
    "query",
    "contact",
    "initial_message",
    "needs_clarification",
    "clarification_prompt",
    "voice_response",
}

MAX_VOICE_RESPONSE_LENGTH: int = 250

SUPPORTED_BROWSERS: Set[str] = {"brave", "chrome", "edge"}
SUPPORTED_WEBSITES: Set[str] = {"youtube", "google", "whatsapp"}

# Intents that are allowed to request clarification for missing parameters
CLARIFICATION_ALLOWED_INTENTS: Set[str] = {
    "SEARCH_GOOGLE",
    "SEARCH_YOUTUBE",
    "WHATSAPP_START",
    "CLARIFICATION",
}

# Safe Default Clarification Prompts (Untrusted Text Fallbacks for Speech Output)
DEFAULT_CLARIFICATION_PROMPTS: Dict[str, str] = {
    "SEARCH_GOOGLE": "Kya search karna hai?",
    "SEARCH_YOUTUBE": "YouTube par kya search karna hai?",
    "WHATSAPP_START": "Kise WhatsApp message bhejna hai?",
    "DEFAULT": "Kripya aur jaankari dein.",
}

MAX_CLARIFICATION_PROMPT_LENGTH: int = 150


@dataclass
class ValidationResult:
    """Represents the deterministic outcome of local schema and security validation."""
    is_valid: bool
    intent: str
    payload: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    needs_clarification: bool = False
    clarification_prompt: Optional[str] = None
    voice_response: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "intent": self.intent,
            "payload": self.payload,
            "error_message": self.error_message,
            "needs_clarification": self.needs_clarification,
            "clarification_prompt": self.clarification_prompt,
            "voice_response": self.voice_response,
        }


class IntentValidator:
    """
    Authoritative local validator for NLU-generated intent schemas.
    Strictly validates structure, data types, allowable values, and safety invariants.
    """

    def __init__(self, allowlist_path: Path = ALLOWLIST_FILE):
        self.allowlist_path = allowlist_path
        self.allowlist: Dict[str, Any] = self._load_allowlist()

    def _load_allowlist(self) -> Dict[str, Any]:
        """Loads the official application allowlist JSON."""
        if not self.allowlist_path.exists():
            logger.error(f"Allowlist file not found at: {self.allowlist_path}")
            return {}
        try:
            with open(self.allowlist_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load allowlist JSON: {e}")
            return {}

    def resolve_allowed_app(self, app_query: str) -> Optional[str]:
        """
        Matches an application query against allowlisted keys and aliases.
        Returns the canonical app key if approved, or None.
        """
        clean = (app_query or "").strip().lower()
        if not clean:
            return None

        # Generic browser aliases resolve to preferred browser
        if clean in ("browser", "internet"):
            pref = PREFERRED_BROWSER.lower()
            if pref in self.allowlist:
                return pref

        for app_key, app_data in self.allowlist.items():
            if clean == app_key.lower():
                return app_key.lower()
            aliases = [a.lower() for a in app_data.get("aliases", [])]
            if clean in aliases:
                return app_key.lower()

        return None

    def sanitize_clarification_prompt(self, raw_prompt: Optional[str], intent: str) -> str:
        """
        Sanitizes untrusted clarification prompt text for voice assistant output.
        Filters control characters, enforces a 150-char length bound, and falls back to safe Hindi prompts.
        Note: This is audio/TTS prompt text sanitization, not an HTML/web rendering boundary.
        """
        default_prompt = DEFAULT_CLARIFICATION_PROMPTS.get(intent, DEFAULT_CLARIFICATION_PROMPTS["DEFAULT"])
        if not raw_prompt or not isinstance(raw_prompt, str):
            return default_prompt

        # Strip control characters (ASCII 0-31, 127) and suspicious formatting characters
        cleaned = re.sub(r"[\x00-\x1f\x7f<>`$\\]", "", raw_prompt)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        if not cleaned:
            return default_prompt

        # Enforce maximum character limit
        if len(cleaned) > MAX_CLARIFICATION_PROMPT_LENGTH:
            return default_prompt

        return cleaned

    def sanitize_voice_response(self, raw_response: Any) -> Optional[str]:
        """
        Sanitizes untrusted model-generated spoken response for safe voice output.
        Ensures string type, strips control/dangerous characters, and bounds length.
        Returns sanitized string or None on missing/empty/invalid input.
        """
        if raw_response is None or not isinstance(raw_response, str):
            return None

        # Strip control characters (ASCII 0-31, 127) and unsafe script/formatting characters
        cleaned = re.sub(r"[\x00-\x1f\x7f<>`$\\]", "", raw_response)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        if not cleaned:
            return None

        if len(cleaned) > MAX_VOICE_RESPONSE_LENGTH:
            cleaned = cleaned[:MAX_VOICE_RESPONSE_LENGTH].rsplit(" ", 1)[0].strip()

        return cleaned or None

    def validate(self, raw_input: Union[str, Dict[str, Any]]) -> ValidationResult:
        """
        Main entry point for local schema and security validation.
        Accepts raw JSON string or parsed dictionary.
        Returns a ValidationResult. Never raises unhandled exceptions.
        """
        # 1. Parse JSON if string input
        data: Dict[str, Any]
        if isinstance(raw_input, str):
            clean_str = raw_input.strip()
            # Strip accidental markdown code blocks (```json ... ```)
            if clean_str.startswith("```"):
                clean_str = re.sub(r"^```(?:json)?\s*", "", clean_str)
                clean_str = re.sub(r"\s*```$", "", clean_str)
            try:
                parsed = json.loads(clean_str)
                if not isinstance(parsed, dict):
                    return ValidationResult(
                        is_valid=False,
                        intent="UNKNOWN",
                        error_message="JSON root must be an object/dict.",
                    )
                data = parsed
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                return ValidationResult(
                    is_valid=False,
                    intent="UNKNOWN",
                    error_message=f"Malformed JSON input: {e}",
                )
        elif isinstance(raw_input, dict):
            data = raw_input
        else:
            return ValidationResult(
                is_valid=False,
                intent="UNKNOWN",
                error_message="Input must be a JSON string or dict.",
            )

        # 2. Reject unexpected or extra keys
        input_keys = set(data.keys())
        extra_keys = input_keys - ALLOWED_KEYS
        if extra_keys:
            return ValidationResult(
                is_valid=False,
                intent="UNKNOWN",
                error_message=f"Unexpected keys in input: {sorted(list(extra_keys))}",
            )

        # 3. Validate intent presence, type, and value
        raw_intent = data.get("intent")
        if not raw_intent or not isinstance(raw_intent, str):
            return ValidationResult(
                is_valid=False,
                intent="UNKNOWN",
                error_message="Missing or non-string 'intent' field.",
            )

        intent = raw_intent.strip().upper()
        if intent not in SUPPORTED_INTENTS:
            return ValidationResult(
                is_valid=False,
                intent="UNKNOWN",
                error_message=f"Unsupported intent: '{raw_intent}'.",
            )

        # 4. Type Validation for optional fields
        def _check_str_or_none(key: str) -> Tuple[bool, Optional[str]]:
            val = data.get(key)
            if val is None:
                return True, None
            if not isinstance(val, str):
                return False, None
            stripped = val.strip()
            return True, stripped if stripped else None

        for str_key in ("app_name", "website", "browser", "query", "contact", "initial_message"):
            ok, _ = _check_str_or_none(str_key)
            if not ok:
                return ValidationResult(
                    is_valid=False,
                    intent="UNKNOWN",
                    error_message=f"Field '{str_key}' must be a string or null.",
                )

        needs_clarification_val = data.get("needs_clarification", False)
        if needs_clarification_val is not None and not isinstance(needs_clarification_val, bool):
            return ValidationResult(
                is_valid=False,
                intent="UNKNOWN",
                error_message="Field 'needs_clarification' must be a boolean.",
            )
        needs_clarification = bool(needs_clarification_val)

        clarification_prompt_val = data.get("clarification_prompt")
        if clarification_prompt_val is not None and not isinstance(clarification_prompt_val, str):
            return ValidationResult(
                is_valid=False,
                intent="UNKNOWN",
                error_message="Field 'clarification_prompt' must be a string or null.",
            )

        # Extract cleaned values
        _, app_name = _check_str_or_none("app_name")
        _, website = _check_str_or_none("website")
        _, browser = _check_str_or_none("browser")
        _, query = _check_str_or_none("query")
        _, contact = _check_str_or_none("contact")
        _, initial_message = _check_str_or_none("initial_message")

        # Extract and sanitize optional voice_response
        voice_response = self.sanitize_voice_response(data.get("voice_response"))

        # 5. Validate browser value
        # Normalize deliberate null representations ("null", "none") to None
        if browser is not None and browser.strip().lower() in ("null", "none"):
            browser = None

        if browser is not None:
            browser_clean = browser.lower()
            if browser_clean not in SUPPORTED_BROWSERS:
                return ValidationResult(
                    is_valid=False,
                    intent="UNKNOWN",
                    error_message=f"Unsupported browser: '{browser}'. Allowed: {sorted(list(SUPPORTED_BROWSERS))}.",
                )
            browser = browser_clean

        # 6. Validate website value
        if website is not None:
            website_clean = website.lower()
            if website_clean not in SUPPORTED_WEBSITES:
                return ValidationResult(
                    is_valid=False,
                    intent="UNKNOWN",
                    error_message=f"Unsupported website: '{website}'. Allowed: {sorted(list(SUPPORTED_WEBSITES))}.",
                )
            website = website_clean

        # 7. Disallow needs_clarification on intents that do not support clarification
        if needs_clarification and intent not in CLARIFICATION_ALLOWED_INTENTS:
            return ValidationResult(
                is_valid=False,
                intent="UNKNOWN",
                error_message=f"Intent '{intent}' cannot request clarification.",
            )

        # 8. Intent-Specific Semantic and Combinatorial Validation

        # -------------------------------------------------------------
        # A. UNKNOWN (Must NEVER be accepted as executable or dispatchable)
        # -------------------------------------------------------------
        if intent == "UNKNOWN":
            return ValidationResult(
                is_valid=False,
                intent="UNKNOWN",
                payload={},
                error_message="Intent 'UNKNOWN' is not an actionable or dispatchable command.",
            )

        # -------------------------------------------------------------
        # B. OPEN_APP
        # -------------------------------------------------------------
        if intent == "OPEN_APP":
            if not app_name:
                return ValidationResult(
                    is_valid=False,
                    intent="UNKNOWN",
                    error_message="Intent 'OPEN_APP' requires non-empty 'app_name'.",
                )
            # Contradictory fields check
            if query or website or contact or initial_message:
                return ValidationResult(
                    is_valid=False,
                    intent="UNKNOWN",
                    error_message="Contradictory fields in 'OPEN_APP' intent.",
                )
            # Allowlist check
            resolved_app = self.resolve_allowed_app(app_name)
            if not resolved_app:
                return ValidationResult(
                    is_valid=False,
                    intent="UNKNOWN",
                    error_message=f"Application '{app_name}' is not in the approved allowlist.",
                )

            # Strict browser consistency check:
            # 1. Non-browser applications cannot have a browser specified
            if browser is not None and resolved_app not in SUPPORTED_BROWSERS:
                return ValidationResult(
                    is_valid=False,
                    intent="UNKNOWN",
                    error_message=f"Browser field '{browser}' is incompatible with non-browser application '{resolved_app}'.",
                )
            # 2. Browser applications must match explicit browser target if supplied
            if browser is not None and resolved_app in SUPPORTED_BROWSERS and browser != resolved_app:
                return ValidationResult(
                    is_valid=False,
                    intent="UNKNOWN",
                    error_message=f"Conflicting browser target '{browser}' with application '{resolved_app}'.",
                )

            payload = {"app_name": resolved_app}
            if browser is not None:
                payload["browser"] = browser

            return ValidationResult(
                is_valid=True,
                intent="OPEN_APP",
                payload=payload,
                voice_response=voice_response,
            )

        # -------------------------------------------------------------
        # C. OPEN_WEBSITE
        # -------------------------------------------------------------
        if intent == "OPEN_WEBSITE":
            if not website:
                return ValidationResult(
                    is_valid=False,
                    intent="UNKNOWN",
                    error_message="Intent 'OPEN_WEBSITE' requires non-empty 'website'.",
                )
            # Contradictory fields check
            if query or app_name or contact or initial_message:
                return ValidationResult(
                    is_valid=False,
                    intent="UNKNOWN",
                    error_message="Contradictory fields in 'OPEN_WEBSITE' intent.",
                )

            return ValidationResult(
                is_valid=True,
                intent="OPEN_WEBSITE",
                payload={"website": website, "browser": browser},
                voice_response=voice_response,
            )

        # -------------------------------------------------------------
        # D. SEARCH_GOOGLE
        # -------------------------------------------------------------
        if intent == "SEARCH_GOOGLE":
            # Contradictory fields check
            if app_name or website or contact or initial_message:
                return ValidationResult(
                    is_valid=False,
                    intent="UNKNOWN",
                    error_message="Contradictory fields in 'SEARCH_GOOGLE' intent.",
                )

            # If query is missing or clarification requested
            if needs_clarification or not query:
                prompt = self.sanitize_clarification_prompt(clarification_prompt_val, "SEARCH_GOOGLE")
                return ValidationResult(
                    is_valid=True,
                    intent="CLARIFICATION",
                    payload={"target_intent": "SEARCH_GOOGLE", "browser": browser},
                    needs_clarification=True,
                    clarification_prompt=prompt,
                    voice_response=voice_response,
                )

            return ValidationResult(
                is_valid=True,
                intent="SEARCH_GOOGLE",
                payload={"query": query, "browser": browser},
                voice_response=voice_response,
            )

        # -------------------------------------------------------------
        # E. SEARCH_YOUTUBE
        # -------------------------------------------------------------
        if intent == "SEARCH_YOUTUBE":
            # Contradictory fields check
            if app_name or website or contact or initial_message:
                return ValidationResult(
                    is_valid=False,
                    intent="UNKNOWN",
                    error_message="Contradictory fields in 'SEARCH_YOUTUBE' intent.",
                )

            # If query is missing or clarification requested
            if needs_clarification or not query:
                prompt = self.sanitize_clarification_prompt(clarification_prompt_val, "SEARCH_YOUTUBE")
                return ValidationResult(
                    is_valid=True,
                    intent="CLARIFICATION",
                    payload={"target_intent": "SEARCH_YOUTUBE", "browser": browser},
                    needs_clarification=True,
                    clarification_prompt=prompt,
                    voice_response=voice_response,
                )

            return ValidationResult(
                is_valid=True,
                intent="SEARCH_YOUTUBE",
                payload={"query": query, "browser": browser},
                voice_response=voice_response,
            )

        # -------------------------------------------------------------
        # F. WHATSAPP_START
        # -------------------------------------------------------------
        if intent == "WHATSAPP_START":
            # Contradictory fields check
            if app_name or website or browser or query:
                return ValidationResult(
                    is_valid=False,
                    intent="UNKNOWN",
                    error_message="Contradictory fields in 'WHATSAPP_START' intent.",
                )

            # Contact is strictly required for WHATSAPP_START
            # If contact is missing or empty -> produce structured CLARIFICATION
            if not contact:
                prompt = self.sanitize_clarification_prompt(clarification_prompt_val, "WHATSAPP_START")
                return ValidationResult(
                    is_valid=True,
                    intent="CLARIFICATION",
                    payload={"target_intent": "WHATSAPP_START"},
                    needs_clarification=True,
                    clarification_prompt=prompt,
                    voice_response=voice_response,
                )

            # If contact is present but message clarification was explicitly requested
            if needs_clarification:
                prompt = self.sanitize_clarification_prompt(clarification_prompt_val, "WHATSAPP_START")
                return ValidationResult(
                    is_valid=True,
                    intent="CLARIFICATION",
                    payload={"target_intent": "WHATSAPP_START", "contact": contact},
                    needs_clarification=True,
                    clarification_prompt=prompt,
                    voice_response=voice_response,
                )

            return ValidationResult(
                is_valid=True,
                intent="WHATSAPP_START",
                payload={"contact": contact, "initial_message": initial_message or ""},
                voice_response=voice_response,
            )

        # -------------------------------------------------------------
        # G. IDENTITY
        # -------------------------------------------------------------
        if intent == "IDENTITY":
            if app_name or website or browser or query or contact or initial_message:
                return ValidationResult(
                    is_valid=False,
                    intent="UNKNOWN",
                    error_message="Contradictory fields in 'IDENTITY' intent.",
                )
            return ValidationResult(
                is_valid=True,
                intent="IDENTITY",
                payload={},
                voice_response=voice_response,
            )

        # -------------------------------------------------------------
        # H. CLARIFICATION (Strict field checking)
        # -------------------------------------------------------------
        if intent == "CLARIFICATION":
            # Reject unrelated/contradictory action fields
            if app_name or website or query or contact or initial_message:
                return ValidationResult(
                    is_valid=False,
                    intent="UNKNOWN",
                    error_message="Contradictory action fields in 'CLARIFICATION' intent.",
                )

            prompt = self.sanitize_clarification_prompt(clarification_prompt_val, "DEFAULT")
            payload = {}
            if browser is not None:
                payload["browser"] = browser

            return ValidationResult(
                is_valid=True,
                intent="CLARIFICATION",
                payload=payload,
                needs_clarification=True,
                clarification_prompt=prompt,
                voice_response=voice_response,
            )

        # -------------------------------------------------------------
        # I. CONVERSATION (Pure Q&A / conversational chat)
        # -------------------------------------------------------------
        if intent == "CONVERSATION":
            # Reject contradictory action fields
            if app_name or website or browser or query or contact or initial_message:
                return ValidationResult(
                    is_valid=False,
                    intent="UNKNOWN",
                    error_message="Contradictory action fields in 'CONVERSATION' intent.",
                )

            # Require non-empty valid voice_response
            if not voice_response:
                return ValidationResult(
                    is_valid=False,
                    intent="UNKNOWN",
                    error_message="Intent 'CONVERSATION' requires a non-empty 'voice_response'.",
                )

            return ValidationResult(
                is_valid=True,
                intent="CONVERSATION",
                payload={},
                voice_response=voice_response,
            )

        # Catch-all safe fallback
        return ValidationResult(
            is_valid=False,
            intent="UNKNOWN",
            payload={},
            error_message="Unsupported intent state.",
        )
