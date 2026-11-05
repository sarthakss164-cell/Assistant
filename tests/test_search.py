"""
Unit tests for web search actions (Google Search and YouTube Search).
Verifies URL construction, query encoding, instance reuse in preferred browser, and feminine Hindi grammar.
"""

import pytest
from unittest.mock import patch
from actions.web_search import search_google, search_youtube
from actions.browser import open_google_search, open_youtube


@patch("actions.browser.open_url_in_browser", return_value=(True, "Success"))
def test_google_search_url_encoding(mock_url_open):
    """Verifies that Google search encodes queries properly including spaces and symbols with feminine Hindi."""
    success, msg = search_google("latest AI")
    assert success is True
    assert "Google par 'latest AI' search kar rahi hoon" in msg
    mock_url_open.assert_called_once_with("https://www.google.com/search?q=latest+AI", None)


@patch("actions.browser.open_url_in_browser", return_value=(True, "Success"))
def test_google_search_special_characters(mock_url_open):
    """Verifies that Google search encodes queries with symbols like & and ? properly."""
    success, msg = search_google("python programming & data science?")
    assert success is True
    mock_url_open.assert_called_once_with("https://www.google.com/search?q=python+programming+%26+data+science%3F", None)


@patch("actions.browser.open_url_in_browser", return_value=(True, "Success"))
def test_youtube_search_url_encoding(mock_url_open):
    """Verifies that YouTube search encodes queries properly with feminine Hindi."""
    success, msg = search_youtube("Python full course")
    assert success is True
    assert "YouTube par 'Python full course' search kar rahi hoon" in msg
    mock_url_open.assert_called_once_with("https://www.youtube.com/results?search_query=Python+full+course", None)


@patch("actions.browser.open_url_in_browser", return_value=(True, "Success"))
def test_youtube_open_homepage(mock_url_open):
    """Verifies that empty query for YouTube opens the YouTube homepage with feminine Hindi."""
    success, msg = search_youtube("")
    assert success is True
    assert "YouTube open kar rahi hoon" in msg
    mock_url_open.assert_called_once_with("https://www.youtube.com", None)


def test_empty_google_query_rejected():
    """Verifies that empty Google search queries are safely rejected."""
    success_g, msg_g = search_google("   ")
    assert success_g is False
    assert "Kripya Google" in msg_g


@patch("actions.browser.open_url_in_browser", return_value=(False, "Failed"))
def test_browser_launch_failure(mock_url_open):
    """Verifies error handling if open_url_in_browser fails."""
    success, msg = search_google("test error")
    assert success is False
    assert "Browser open karne mein dikkat aayi" in msg
