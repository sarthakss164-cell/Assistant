"""
Unit tests for core/coe_gateway.py in Light AI V1.0.
Verifies client initialization, timeout handling, connection failures,
authentication errors, rate limits, empty response handling, and sensitive key isolation.
All tests use mock objects; zero real network requests or credentials are used.
"""

from unittest.mock import MagicMock
import pytest
import openai
from httpx2 import Request, Response

from core.coe_gateway import (
    CoeGatewayClient,
    GatewayStatus,
    GatewayResponse,
    DEFAULT_SYSTEM_PROMPT,
)
from config.settings import (
    COE_AI_BASE_URL,
    COE_AI_MODEL,
    COE_AI_TIMEOUT_SECONDS,
)


# =============================================================================
# Helper Mocks
# =============================================================================

def make_mock_completion(content="{\"intent\": \"OPEN_APP\", \"app_name\": \"chrome\"}", model="qwen3.6"):
    mock_resp = MagicMock()
    mock_resp.model = model
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_resp.choices = [mock_choice]
    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 15
    mock_usage.completion_tokens = 25
    mock_usage.total_tokens = 40
    mock_resp.usage = mock_usage
    return mock_resp


def make_dummy_request():
    return Request("POST", "https://ai.tcetcercd.in/v1/chat/completions")


# =============================================================================
# 1. Initialization and Configuration Tests
# =============================================================================

def test_client_defaults_from_settings():
    """Client must read base URL, model, and timeout from settings module by default."""
    client = CoeGatewayClient(api_key="mock_test_key")
    assert client.base_url == COE_AI_BASE_URL
    assert client.model == COE_AI_MODEL
    assert client.timeout == COE_AI_TIMEOUT_SECONDS
    assert client.is_configured is True


def test_client_custom_configuration():
    """Client must respect explicit custom configuration parameters."""
    client = CoeGatewayClient(
        base_url="https://custom.gateway.internal/v1",
        model="custom-qwen",
        api_key="custom_dummy_key",
        timeout=15.0,
    )
    assert client.base_url == "https://custom.gateway.internal/v1"
    assert client.model == "custom-qwen"
    assert client.timeout == 15.0
    assert client.is_configured is True


def test_client_unconfigured_when_key_empty():
    """Client must recognize when it is unconfigured without raising exceptions."""
    client = CoeGatewayClient(api_key="", client=None)
    assert client.is_configured is False
    resp = client.complete("open chrome")
    assert resp.status == GatewayStatus.NOT_CONFIGURED
    assert resp.is_success is False
    assert "not configured" in resp.error_message


# =============================================================================
# 2. Successful Request Handling Tests
# =============================================================================

def test_successful_complete_request():
    """Successful complete() call must return SUCCESS status, content, and token usage."""
    mock_openai = MagicMock()
    expected_json = '{"intent": "OPEN_WEBSITE", "website": "youtube", "browser": "brave"}'
    mock_openai.chat.completions.create.return_value = make_mock_completion(content=expected_json)

    client = CoeGatewayClient(api_key="mock_key", client=mock_openai)
    resp = client.complete("mera youtube dekhne ka man hai")

    assert resp.status == GatewayStatus.SUCCESS
    assert resp.is_success is True
    assert resp.raw_content == expected_json
    assert resp.model == "qwen3.6"
    assert resp.usage == {"prompt_tokens": 15, "completion_tokens": 25, "total_tokens": 40}

    # Verify parameters passed to the underlying client
    mock_openai.chat.completions.create.assert_called_once()
    kwargs = mock_openai.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "qwen3.6"
    assert kwargs["temperature"] == 0.0
    assert kwargs["response_format"] == {"type": "json_object"}
    assert kwargs["messages"][0]["role"] == "system"
    assert kwargs["messages"][1]["role"] == "user"
    assert kwargs["messages"][1]["content"] == "mera youtube dekhne ka man hai"


def test_complete_empty_utterance_rejected():
    """Empty or whitespace utterance must return EMPTY_RESPONSE before calling client."""
    mock_openai = MagicMock()
    client = CoeGatewayClient(api_key="mock_key", client=mock_openai)

    resp = client.complete("   ")
    assert resp.status == GatewayStatus.EMPTY_RESPONSE
    assert resp.is_success is False
    mock_openai.chat.completions.create.assert_not_called()


# =============================================================================
# 3. Empty & Malformed Response Handling Tests
# =============================================================================

def test_empty_choices_in_response():
    """Response containing an empty choices list must return EMPTY_RESPONSE status."""
    mock_openai = MagicMock()
    empty_resp = MagicMock()
    empty_resp.choices = []
    empty_resp.model = "qwen3.6"
    mock_openai.chat.completions.create.return_value = empty_resp

    client = CoeGatewayClient(api_key="mock_key", client=mock_openai)
    resp = client.complete("open chrome")

    assert resp.status == GatewayStatus.EMPTY_RESPONSE
    assert resp.is_success is False
    assert "no choices" in resp.error_message


def test_null_content_in_choice():
    """Choice with null or whitespace-only message content must return EMPTY_RESPONSE status."""
    mock_openai = MagicMock()
    mock_openai.chat.completions.create.return_value = make_mock_completion(content="   ")

    client = CoeGatewayClient(api_key="mock_key", client=mock_openai)
    resp = client.complete("open chrome")

    assert resp.status == GatewayStatus.EMPTY_RESPONSE
    assert resp.is_success is False
    assert "empty or null" in resp.error_message


def test_invalid_messages_payload():
    """Passing invalid messages payload to chat() must return INVALID_RESPONSE."""
    client = CoeGatewayClient(api_key="mock_key", client=MagicMock())
    resp = client.chat(messages=None)
    assert resp.status == GatewayStatus.INVALID_RESPONSE
    assert resp.is_success is False


# =============================================================================
# 4. Exception & Failure Handling Tests
# =============================================================================

def test_timeout_error_handling():
    """APITimeoutError must be caught and mapped to GatewayStatus.TIMEOUT."""
    mock_openai = MagicMock()
    mock_openai.chat.completions.create.side_effect = openai.APITimeoutError(
        request=make_dummy_request()
    )

    client = CoeGatewayClient(api_key="mock_key", timeout=10.0, client=mock_openai)
    resp = client.complete("kuch search karna hai")

    assert resp.status == GatewayStatus.TIMEOUT
    assert resp.is_success is False
    assert "timed out after 10.0 seconds" in resp.error_message


def test_connection_error_handling():
    """APIConnectionError must be caught and mapped to GatewayStatus.CONNECTION_FAILURE."""
    mock_openai = MagicMock()
    mock_openai.chat.completions.create.side_effect = openai.APIConnectionError(
        request=make_dummy_request(),
        message="Connection dropped by peer"
    )

    client = CoeGatewayClient(api_key="mock_key", client=mock_openai)
    resp = client.complete("chrome kholo")

    assert resp.status == GatewayStatus.CONNECTION_FAILURE
    assert resp.is_success is False
    assert "server unreachable or network error" in resp.error_message


def test_authentication_error_handling():
    """AuthenticationError (HTTP 401) must be caught and mapped to GatewayStatus.AUTHENTICATION_FAILURE."""
    mock_openai = MagicMock()
    dummy_response = Response(status_code=401, request=make_dummy_request())
    mock_openai.chat.completions.create.side_effect = openai.AuthenticationError(
        message="Invalid API Key",
        response=dummy_response,
        body=None
    )

    secret_key = "sensitive_dummy_secret_12345"
    client = CoeGatewayClient(api_key=secret_key, client=mock_openai)
    resp = client.complete("chrome kholo")

    assert resp.status == GatewayStatus.AUTHENTICATION_FAILURE
    assert resp.is_success is False
    assert "authentication failed" in resp.error_message
    # Verify the secret key is NOT leaked into the error message
    assert secret_key not in resp.error_message


def test_rate_limit_error_handling():
    """RateLimitError (HTTP 429) must be caught and mapped to GatewayStatus.RATE_LIMIT."""
    mock_openai = MagicMock()
    dummy_response = Response(status_code=429, request=make_dummy_request())
    mock_openai.chat.completions.create.side_effect = openai.RateLimitError(
        message="Quota exceeded",
        response=dummy_response,
        body=None
    )

    client = CoeGatewayClient(api_key="mock_key", client=mock_openai)
    resp = client.complete("open brave")

    assert resp.status == GatewayStatus.RATE_LIMIT
    assert resp.is_success is False
    assert "rate limit reached" in resp.error_message


def test_api_status_error_handling():
    """APIStatusError (e.g. HTTP 503) must be caught and mapped to GatewayStatus.API_ERROR."""
    mock_openai = MagicMock()
    dummy_response = Response(status_code=503, request=make_dummy_request())
    mock_openai.chat.completions.create.side_effect = openai.APIStatusError(
        message="Service Unavailable",
        response=dummy_response,
        body=None
    )

    client = CoeGatewayClient(api_key="mock_key", client=mock_openai)
    resp = client.complete("open brave")

    assert resp.status == GatewayStatus.API_ERROR
    assert resp.is_success is False
    assert "503" in resp.error_message


def test_unexpected_exception_handling():
    """Generic unexpected exceptions must be caught safely without crashing."""
    mock_openai = MagicMock()
    mock_openai.chat.completions.create.side_effect = RuntimeError("Socket layer broken")

    client = CoeGatewayClient(api_key="mock_key", client=mock_openai)
    resp = client.complete("open brave")

    assert resp.status == GatewayStatus.API_ERROR
    assert resp.is_success is False
    assert "RuntimeError" in resp.error_message


# =============================================================================
# 5. Isolation & Pure Data Boundary Tests
# =============================================================================

def test_gateway_response_to_dict():
    """GatewayResponse must serialize cleanly to a dictionary."""
    resp = GatewayResponse(
        status=GatewayStatus.SUCCESS,
        raw_content='{"intent": "IDENTITY"}',
        model="qwen3.6",
        usage={"total_tokens": 50}
    )
    d = resp.to_dict()
    assert d["status"] == "SUCCESS"
    assert d["is_success"] is True
    assert d["raw_content"] == '{"intent": "IDENTITY"}'
    assert d["model"] == "qwen3.6"
    assert d["usage"] == {"total_tokens": 50}


def test_gateway_client_does_not_execute_actions():
    """Gateway client must only return data and never execute actions or call subprocesses."""
    # Verify client class does not have execution methods
    assert not hasattr(CoeGatewayClient, "launch")
    assert not hasattr(CoeGatewayClient, "execute")
    assert not hasattr(CoeGatewayClient, "send_message")
