"""
Unit tests for configuration and timeout validation in Light AI V1.0.
Verifies finite positive number validation, secret-free default fallbacks,
and CoE AI Gateway configuration variables.
"""

import pytest
from config.settings import (
    parse_timeout,
    COE_AI_BASE_URL,
    COE_AI_MODEL,
    COE_AI_KEY,
    COE_AI_TIMEOUT_SECONDS,
)


def test_parse_timeout_valid_floats():
    """Valid finite positive floats must be parsed accurately."""
    assert parse_timeout("10.0") == 10.0
    assert parse_timeout("12.5") == 12.5
    assert parse_timeout("0.5") == 0.5
    assert parse_timeout(" 8.0 ") == 8.0


def test_parse_timeout_nan_rejected():
    """NaN and variants must be rejected and safely default to fallback."""
    assert parse_timeout("NaN") == 10.0
    assert parse_timeout("nan") == 10.0
    assert parse_timeout("NAN", default=5.0) == 5.0


def test_parse_timeout_infinity_rejected():
    """Positive and negative infinity must be rejected."""
    assert parse_timeout("Infinity") == 10.0
    assert parse_timeout("inf") == 10.0
    assert parse_timeout("-Infinity") == 10.0
    assert parse_timeout("-inf") == 10.0


def test_parse_timeout_non_positive_rejected():
    """Zero and negative numbers must be rejected."""
    assert parse_timeout("0.0") == 10.0
    assert parse_timeout("0") == 10.0
    assert parse_timeout("-1.0") == 10.0
    assert parse_timeout("-10.0", default=15.0) == 15.0


def test_parse_timeout_non_numeric_and_whitespace_rejected():
    """Strings, units, and empty strings must be rejected."""
    assert parse_timeout("fast") == 10.0
    assert parse_timeout("10s") == 10.0
    assert parse_timeout("") == 10.0
    assert parse_timeout("   ") == 10.0
    assert parse_timeout(None) == 10.0


def test_coe_ai_settings_exported():
    """Settings module must export the required CoE AI Gateway parameters."""
    assert COE_AI_BASE_URL == "https://ai.tcetcercd.in/v1"
    assert COE_AI_MODEL == "qwen3.6"
    assert isinstance(COE_AI_TIMEOUT_SECONDS, float)
    assert COE_AI_TIMEOUT_SECONDS > 0.0
    assert isinstance(COE_AI_KEY, str)
