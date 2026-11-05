"""
Comprehensive unit tests for core/intent_validator.py in Light AI V1.0.
Verifies strict local schema validation, allowlist enforcement, type safety,
browser-app consistency, WhatsApp contact requirement, clarification field isolation,
untrusted text sanitization, and non-dispatchability of UNKNOWN intents.
"""

import pytest
from core.intent_validator import IntentValidator, ValidationResult


@pytest.fixture
def validator():
    return IntentValidator()


# =============================================================================
# 1. VALID INPUT TESTS
# =============================================================================

def test_valid_open_app(validator):
    """Allowlisted applications must pass validation."""
    for app in ["chrome", "brave", "edge", "notepad", "vscode", "whatsapp"]:
        res = validator.validate({"intent": "OPEN_APP", "app_name": app})
        assert res.is_valid is True
        assert res.intent == "OPEN_APP"
        assert res.payload["app_name"] == app


def test_valid_open_app_alias(validator):
    """Application aliases like 'google chrome' and 'vs code' must resolve correctly."""
    res = validator.validate({"intent": "OPEN_APP", "app_name": "google chrome"})
    assert res.is_valid is True
    assert res.payload["app_name"] == "chrome"

    res_vc = validator.validate({"intent": "OPEN_APP", "app_name": "vs code"})
    assert res_vc.is_valid is True
    assert res_vc.payload["app_name"] == "vscode"


def test_valid_open_website(validator):
    """Approved websites and browser options must validate cleanly."""
    res = validator.validate({
        "intent": "OPEN_WEBSITE",
        "website": "youtube",
        "browser": "brave"
    })
    assert res.is_valid is True
    assert res.intent == "OPEN_WEBSITE"
    assert res.payload["website"] == "youtube"
    assert res.payload["browser"] == "brave"


def test_valid_open_website_default_browser(validator):
    """Omitted browser in OPEN_WEBSITE should keep browser as None."""
    res = validator.validate({
        "intent": "OPEN_WEBSITE",
        "website": "google"
    })
    assert res.is_valid is True
    assert res.payload["website"] == "google"
    assert res.payload["browser"] is None


def test_valid_search_google(validator):
    """Google search with query must validate."""
    res = validator.validate({
        "intent": "SEARCH_GOOGLE",
        "query": "latest AI news",
        "browser": "chrome"
    })
    assert res.is_valid is True
    assert res.intent == "SEARCH_GOOGLE"
    assert res.payload["query"] == "latest AI news"
    assert res.payload["browser"] == "chrome"


def test_valid_search_youtube(validator):
    """YouTube search with query must validate."""
    res = validator.validate({
        "intent": "SEARCH_YOUTUBE",
        "query": "python full course"
    })
    assert res.is_valid is True
    assert res.intent == "SEARCH_YOUTUBE"
    assert res.payload["query"] == "python full course"


def test_valid_whatsapp_start(validator):
    """WhatsApp start with valid contact must validate."""
    res = validator.validate({
        "intent": "WHATSAPP_START",
        "contact": "anand",
        "initial_message": "hello bhai"
    })
    assert res.is_valid is True
    assert res.intent == "WHATSAPP_START"
    assert res.payload["contact"] == "anand"
    assert res.payload["initial_message"] == "hello bhai"


def test_valid_identity(validator):
    """Identity query must validate without extra parameters."""
    res = validator.validate({"intent": "IDENTITY"})
    assert res.is_valid is True
    assert res.intent == "IDENTITY"
    assert res.payload == {}


def test_valid_json_string_input(validator):
    """Stringified JSON input must parse and validate identical to a dict."""
    raw_json = '{"intent": "OPEN_APP", "app_name": "notepad"}'
    res = validator.validate(raw_json)
    assert res.is_valid is True
    assert res.intent == "OPEN_APP"
    assert res.payload["app_name"] == "notepad"


def test_valid_markdown_fenced_json(validator):
    """Accidental markdown-wrapped JSON from LLM must be cleaned and parsed."""
    wrapped = '```json\n{"intent": "SEARCH_GOOGLE", "query": "Python"}\n```'
    res = validator.validate(wrapped)
    assert res.is_valid is True
    assert res.intent == "SEARCH_GOOGLE"
    assert res.payload["query"] == "Python"


# =============================================================================
# 2. UNKNOWN INTENT NON-DISPATCHABILITY TESTS (Issue A)
# =============================================================================

def test_unknown_intent_is_not_dispatchable(validator):
    """UNKNOWN intent must never be accepted as a valid, dispatchable action."""
    res = validator.validate({"intent": "UNKNOWN"})
    assert res.is_valid is False
    assert res.intent == "UNKNOWN"
    assert "not an actionable or dispatchable command" in res.error_message


def test_unknown_lowercase_intent_rejected(validator):
    """Case-insensitive unknown must also fail dispatchability."""
    res = validator.validate({"intent": "unknown"})
    assert res.is_valid is False
    assert res.intent == "UNKNOWN"


def test_unknown_with_payload_rejected(validator):
    """UNKNOWN with arbitrary payload must be rejected."""
    res = validator.validate({"intent": "UNKNOWN", "query": "something"})
    assert res.is_valid is False
    assert res.intent == "UNKNOWN"


# =============================================================================
# 3. WHATSAPP CONTACT VALIDATION TESTS (Issue B)
# =============================================================================

def test_whatsapp_missing_contact_produces_clarification(validator):
    """WHATSAPP_START without contact must not pass as valid; it must produce CLARIFICATION."""
    res = validator.validate({"intent": "WHATSAPP_START"})
    assert res.is_valid is True
    assert res.intent == "CLARIFICATION"
    assert res.needs_clarification is True
    assert res.clarification_prompt == "Kise WhatsApp message bhejna hai?"
    assert res.payload["target_intent"] == "WHATSAPP_START"


def test_whatsapp_null_contact_produces_clarification(validator):
    """WHATSAPP_START with null contact must produce CLARIFICATION."""
    res = validator.validate({"intent": "WHATSAPP_START", "contact": None})
    assert res.is_valid is True
    assert res.intent == "CLARIFICATION"
    assert res.needs_clarification is True
    assert res.clarification_prompt == "Kise WhatsApp message bhejna hai?"


def test_whatsapp_whitespace_contact_produces_clarification(validator):
    """WHATSAPP_START with empty/whitespace contact must produce CLARIFICATION."""
    res = validator.validate({"intent": "WHATSAPP_START", "contact": "   "})
    assert res.is_valid is True
    assert res.intent == "CLARIFICATION"
    assert res.needs_clarification is True


def test_whatsapp_contact_present_message_clarification(validator):
    """WHATSAPP_START with contact and needs_clarification=True asks for message."""
    res = validator.validate({
        "intent": "WHATSAPP_START",
        "contact": "anand",
        "needs_clarification": True,
        "clarification_prompt": "Anand ko kya message bhejna hai?"
    })
    assert res.is_valid is True
    assert res.intent == "CLARIFICATION"
    assert res.needs_clarification is True
    assert res.payload["contact"] == "anand"
    assert res.clarification_prompt == "Anand ko kya message bhejna hai?"


# =============================================================================
# 4. STRICT CLARIFICATION FIELD VALIDATION (Issue C)
# =============================================================================

def test_valid_clarification_intent(validator):
    """CLARIFICATION intent with valid prompt must pass."""
    res = validator.validate({
        "intent": "CLARIFICATION",
        "clarification_prompt": "Kya search karna hai?",
        "needs_clarification": True
    })
    assert res.is_valid is True
    assert res.intent == "CLARIFICATION"
    assert res.needs_clarification is True
    assert res.clarification_prompt == "Kya search karna hai?"


def test_clarification_intent_with_browser(validator):
    """CLARIFICATION with optional browser context must pass."""
    res = validator.validate({
        "intent": "CLARIFICATION",
        "browser": "brave",
        "needs_clarification": True
    })
    assert res.is_valid is True
    assert res.payload.get("browser") == "brave"


def test_clarification_rejects_app_name(validator):
    """CLARIFICATION must reject contradictory action fields like app_name."""
    res = validator.validate({
        "intent": "CLARIFICATION",
        "app_name": "notepad"
    })
    assert res.is_valid is False
    assert "Contradictory action fields" in res.error_message


def test_clarification_rejects_website(validator):
    """CLARIFICATION must reject contradictory website field."""
    res = validator.validate({
        "intent": "CLARIFICATION",
        "website": "youtube"
    })
    assert res.is_valid is False
    assert "Contradictory action fields" in res.error_message


def test_clarification_rejects_query(validator):
    """CLARIFICATION must reject contradictory query field."""
    res = validator.validate({
        "intent": "CLARIFICATION",
        "query": "something"
    })
    assert res.is_valid is False
    assert "Contradictory action fields" in res.error_message


def test_clarification_rejects_contact(validator):
    """CLARIFICATION must reject contradictory contact field."""
    res = validator.validate({
        "intent": "CLARIFICATION",
        "contact": "anand"
    })
    assert res.is_valid is False
    assert "Contradictory action fields" in res.error_message


def test_clarification_rejects_initial_message(validator):
    """CLARIFICATION must reject contradictory initial_message field."""
    res = validator.validate({
        "intent": "CLARIFICATION",
        "initial_message": "hello"
    })
    assert res.is_valid is False
    assert "Contradictory action fields" in res.error_message


# =============================================================================
# 5. OPEN_APP BROWSER FIELD CONSISTENCY (Issue D)
# =============================================================================

def test_open_app_browser_app_with_matching_browser(validator):
    """Browser app with matching explicit browser must be accepted."""
    res1 = validator.validate({"intent": "OPEN_APP", "app_name": "chrome", "browser": "chrome"})
    assert res1.is_valid is True
    assert res1.payload["app_name"] == "chrome"
    assert res1.payload["browser"] == "chrome"

    res2 = validator.validate({"intent": "OPEN_APP", "app_name": "brave", "browser": "brave"})
    assert res2.is_valid is True
    assert res2.payload["app_name"] == "brave"
    assert res2.payload["browser"] == "brave"

    res3 = validator.validate({"intent": "OPEN_APP", "app_name": "edge", "browser": "edge"})
    assert res3.is_valid is True
    assert res3.payload["app_name"] == "edge"
    assert res3.payload["browser"] == "edge"


def test_open_app_browser_app_without_browser(validator):
    """Browser app without explicit browser must be accepted cleanly."""
    res = validator.validate({"intent": "OPEN_APP", "app_name": "chrome"})
    assert res.is_valid is True
    assert res.payload["app_name"] == "chrome"
    assert "browser" not in res.payload


def test_open_app_non_browser_app_with_browser_rejected(validator):
    """Non-browser app (notepad, vscode, whatsapp) with browser field must be rejected."""
    for non_browser in ["notepad", "vscode", "whatsapp"]:
        res = validator.validate({
            "intent": "OPEN_APP",
            "app_name": non_browser,
            "browser": "brave"
        })
        assert res.is_valid is False
        assert "incompatible with non-browser application" in res.error_message


def test_open_app_browser_mismatch_rejected(validator):
    """Browser app with conflicting browser (e.g. app='chrome', browser='brave') must be rejected."""
    res = validator.validate({
        "intent": "OPEN_APP",
        "app_name": "chrome",
        "browser": "brave"
    })
    assert res.is_valid is False
    assert "Conflicting browser target" in res.error_message


def test_open_app_unsupported_browser_rejected(validator):
    """OPEN_APP with unsupported browser (e.g. safari) must be rejected."""
    res = validator.validate({
        "intent": "OPEN_APP",
        "app_name": "chrome",
        "browser": "safari"
    })
    assert res.is_valid is False
    assert "Unsupported browser" in res.error_message


# =============================================================================
# 6. NEEDS_CLARIFICATION CONSISTENCY (Issue E)
# =============================================================================

def test_needs_clarification_allowed_intents(validator):
    """SEARCH_GOOGLE, SEARCH_YOUTUBE, WHATSAPP_START allow needs_clarification."""
    res1 = validator.validate({"intent": "SEARCH_GOOGLE", "query": "python", "needs_clarification": True})
    assert res1.is_valid is True
    assert res1.intent == "CLARIFICATION"

    res2 = validator.validate({"intent": "SEARCH_YOUTUBE", "query": "songs", "needs_clarification": True})
    assert res2.is_valid is True
    assert res2.intent == "CLARIFICATION"

    res3 = validator.validate({"intent": "WHATSAPP_START", "contact": "anand", "needs_clarification": True})
    assert res3.is_valid is True
    assert res3.intent == "CLARIFICATION"


def test_needs_clarification_disallowed_on_open_app(validator):
    """OPEN_APP cannot request clarification."""
    res = validator.validate({
        "intent": "OPEN_APP",
        "app_name": "chrome",
        "needs_clarification": True
    })
    assert res.is_valid is False
    assert "cannot request clarification" in res.error_message


def test_needs_clarification_disallowed_on_open_website(validator):
    """OPEN_WEBSITE cannot request clarification."""
    res = validator.validate({
        "intent": "OPEN_WEBSITE",
        "website": "youtube",
        "needs_clarification": True
    })
    assert res.is_valid is False
    assert "cannot request clarification" in res.error_message


def test_needs_clarification_disallowed_on_identity(validator):
    """IDENTITY cannot request clarification."""
    res = validator.validate({
        "intent": "IDENTITY",
        "needs_clarification": True
    })
    assert res.is_valid is False
    assert "cannot request clarification" in res.error_message


def test_needs_clarification_disallowed_on_unknown(validator):
    """UNKNOWN cannot request clarification."""
    res = validator.validate({
        "intent": "UNKNOWN",
        "needs_clarification": True
    })
    assert res.is_valid is False


# =============================================================================
# 7. CLARIFICATION TEXT SANITIZATION TESTS (Issue F)
# =============================================================================

def test_clarification_prompt_length_limit(validator):
    """Untrusted clarification prompt exceeding 150 chars must default to safe fallback."""
    long_prompt = "A" * 200
    res = validator.validate({
        "intent": "SEARCH_GOOGLE",
        "query": None,
        "needs_clarification": True,
        "clarification_prompt": long_prompt
    })
    assert res.is_valid is True
    assert res.clarification_prompt == "Kya search karna hai?"


def test_clarification_prompt_control_characters_filtered(validator):
    """Control characters (ASCII 0-31, 127) and script characters must be filtered."""
    raw_prompt = "\x00Kaun \x08sa \x1fgaana \x7fsunenge?"
    cleaned = validator.sanitize_clarification_prompt(raw_prompt, "SEARCH_YOUTUBE")
    assert "\x00" not in cleaned
    assert "\x08" not in cleaned
    assert "\x1f" not in cleaned
    assert "\x7f" not in cleaned
    assert "Kaun sa gaana sunenge?" in cleaned


def test_clarification_prompt_empty_and_whitespace_fallback(validator):
    """Empty or whitespace-only prompts must use safe fallback."""
    for empty_val in ["", "    ", None, "\x00\x1f"]:
        cleaned = validator.sanitize_clarification_prompt(empty_val, "SEARCH_GOOGLE")
        assert cleaned == "Kya search karna hai?"


def test_clarification_prompt_normal_text_preserved(validator):
    """Valid short prompt within 150 characters is preserved."""
    normal_prompt = "Aap YouTube par kaun sa course dekhna chahte hain?"
    cleaned = validator.sanitize_clarification_prompt(normal_prompt, "SEARCH_YOUTUBE")
    assert cleaned == normal_prompt


# =============================================================================
# 8. INVALID INPUT & SECURITY TESTS
# =============================================================================

def test_malformed_json_rejected(validator):
    """Broken JSON syntax must be rejected safely."""
    res = validator.validate("{intent: 'OPEN_APP', app_name: }")
    assert res.is_valid is False
    assert res.intent == "UNKNOWN"
    assert "Malformed JSON" in res.error_message


def test_non_dict_root_rejected(validator):
    """Non-dict root objects must be rejected."""
    for bad_input in [["OPEN_APP"], 12345, "just a string", True, None]:
        res = validator.validate(bad_input)
        assert res.is_valid is False
        assert res.intent == "UNKNOWN"


def test_unexpected_keys_rejected(validator):
    """Any key outside the approved set must cause immediate rejection."""
    res = validator.validate({
        "intent": "OPEN_APP",
        "app_name": "chrome",
        "shell_command": "rmdir /s /q C:\\"
    })
    assert res.is_valid is False
    assert res.intent == "UNKNOWN"
    assert "Unexpected keys" in res.error_message


def test_unsupported_intent_rejected(validator):
    """Unrecognized intents must be rejected."""
    for bad_intent in ["EXECUTE_COMMAND", "RUN_SCRIPT", "DOWNLOAD_FILE", "SHUTDOWN_COMPUTER"]:
        res = validator.validate({"intent": bad_intent})
        assert res.is_valid is False
        assert res.intent == "UNKNOWN"
        assert "Unsupported intent" in res.error_message


def test_unapproved_application_rejected(validator):
    """Applications not in config/app_allowlist.json must be rejected."""
    for unapproved in ["cmd.exe", "powershell", "regedit", "photoshop", "calc.exe", "terminal"]:
        res = validator.validate({"intent": "OPEN_APP", "app_name": unapproved})
        assert res.is_valid is False
        assert res.intent == "UNKNOWN"
        assert "not in the approved allowlist" in res.error_message


def test_unsupported_browser_rejected(validator):
    """Browsers other than brave, chrome, edge must be rejected."""
    for unapproved_browser in ["safari", "firefox", "opera", "tor", "powershell"]:
        res = validator.validate({
            "intent": "OPEN_WEBSITE",
            "website": "youtube",
            "browser": unapproved_browser
        })
        assert res.is_valid is False
        assert res.intent == "UNKNOWN"
        assert "Unsupported browser" in res.error_message


def test_unsupported_website_rejected(validator):
    """Websites outside youtube, google, whatsapp must be rejected."""
    for bad_site in ["malicious-site.com", "facebook", "twitter", "reddit"]:
        res = validator.validate({
            "intent": "OPEN_WEBSITE",
            "website": bad_site
        })
        assert res.is_valid is False
        assert res.intent == "UNKNOWN"
        assert "Unsupported website" in res.error_message


def test_invalid_field_types_rejected(validator):
    """Fields with incorrect data types must be rejected."""
    res1 = validator.validate({"intent": "SEARCH_GOOGLE", "query": 12345})
    assert res1.is_valid is False

    res2 = validator.validate({"intent": "SEARCH_GOOGLE", "query": "test", "needs_clarification": "yes"})
    assert res2.is_valid is False

    res3 = validator.validate({"intent": "OPEN_APP", "app_name": ["chrome"]})
    assert res3.is_valid is False


# =============================================================================
# 9. CONTRADICTORY COMBINATIONS TESTS
# =============================================================================

def test_contradictory_open_app_fields(validator):
    """OPEN_APP with search query or website must be rejected."""
    res = validator.validate({
        "intent": "OPEN_APP",
        "app_name": "notepad",
        "query": "some text"
    })
    assert res.is_valid is False
    assert "Contradictory fields" in res.error_message


def test_contradictory_open_website_fields(validator):
    """OPEN_WEBSITE with app_name or query must be rejected."""
    res = validator.validate({
        "intent": "OPEN_WEBSITE",
        "website": "youtube",
        "app_name": "notepad"
    })
    assert res.is_valid is False
    assert "Contradictory fields" in res.error_message


def test_contradictory_whatsapp_fields(validator):
    """WHATSAPP_START with browser or website or query must be rejected."""
    res = validator.validate({
        "intent": "WHATSAPP_START",
        "contact": "anand",
        "website": "youtube"
    })
    assert res.is_valid is False
    assert "Contradictory fields" in res.error_message


def test_contradictory_identity_fields(validator):
    """IDENTITY with app_name or query must be rejected."""
    res = validator.validate({
        "intent": "IDENTITY",
        "app_name": "chrome"
    })
    assert res.is_valid is False
    assert "Contradictory fields" in res.error_message
