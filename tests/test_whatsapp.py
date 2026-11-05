"""
Unit tests for WhatsApp action module.
Verifies contact lookup, phone normalization, URI construction,
preferred browser WhatsApp Web integration, and PyWhatKit messaging with mocked execution.
"""

import pytest
from unittest.mock import patch, MagicMock
from actions.whatsapp import (
    load_contacts,
    resolve_contact_phone,
    build_whatsapp_uris,
    stage_whatsapp_message,
    open_whatsapp_web,
    send_whatsapp_message_via_pywhatkit,
)

SAMPLE_CONTACTS = {
    "rahul": "+919876543210",
    "anand": "+91 98933 71769",
    "boss": "9876543210",
    "mom": "09876543210",
    "invalid_user": "+14155552671",  # Foreign number - rejected by policy
}


def test_resolve_contact_phone_success():
    """Verifies that valid contacts are correctly resolved to 91XXXXXXXXXX."""
    phone_rahul, err1 = resolve_contact_phone("rahul", SAMPLE_CONTACTS)
    assert phone_rahul == "919876543210"
    assert err1 is None

    phone_anand, err_anand = resolve_contact_phone("anand", SAMPLE_CONTACTS)
    assert phone_anand == "919893371769"
    assert err_anand is None

    # Case insensitivity
    phone_boss, err2 = resolve_contact_phone("BOSS", SAMPLE_CONTACTS)
    assert phone_boss == "919876543210"
    assert err2 is None

    phone_mom, err3 = resolve_contact_phone("Mom", SAMPLE_CONTACTS)
    assert phone_mom == "919876543210"
    assert err3 is None


def test_resolve_contact_phone_errors():
    """Verifies error handling for missing contacts or invalid phone formats."""
    # Unknown contact
    phone_unknown, err_unknown = resolve_contact_phone("stranger", SAMPLE_CONTACTS)
    assert phone_unknown is None
    assert "contacts mein nahi mila" in err_unknown

    # Foreign / invalid contact phone
    phone_inv, err_inv = resolve_contact_phone("invalid_user", SAMPLE_CONTACTS)
    assert phone_inv is None
    assert "phone number invalid hai" in err_inv


def test_build_whatsapp_uris_encoding():
    """Verifies correct URL encoding of phone and message in WhatsApp URIs."""
    phone = "919876543210"
    msg = "Hello Rahul! Are you free at 5 PM? Check: https://example.com"
    desktop_uri, web_url = build_whatsapp_uris(phone, msg)

    assert desktop_uri.startswith("whatsapp://send?phone=919876543210&text=")
    assert "Hello%20Rahul%21" in desktop_uri
    assert "5%20PM%3F" in desktop_uri
    assert "https%3A//example.com" in desktop_uri

    assert web_url.startswith("https://web.whatsapp.com/send?phone=919876543210&text=")
    assert "Hello%20Rahul%21" in web_url


@patch("actions.browser.open_url_in_browser", return_value=(True, "Success"))
def test_open_whatsapp_web(mock_browser):
    """Verifies that open_whatsapp_web opens web.whatsapp.com in preferred browser."""
    success, msg = open_whatsapp_web()
    assert success is True
    assert "WhatsApp Web" in msg
    mock_browser.assert_called_once_with("https://web.whatsapp.com", None)


@patch("actions.browser.open_in_brave", return_value=(True, "Success"))
def test_stage_whatsapp_message_in_brave(mock_brave):
    """Verifies that stage_whatsapp_message opens WhatsApp Web in Brave."""
    success, msg = stage_whatsapp_message("919876543210", "Hello", "rahul")
    assert success is True
    assert "Rahul ke liye WhatsApp message stage kar diya gaya hai" in msg
    mock_brave.assert_called_once_with("https://web.whatsapp.com/send?phone=919876543210&text=Hello")


@patch("pywhatkit.sendwhatmsg_instantly")
def test_send_whatsapp_message_via_pywhatkit_success(mock_pywhatkit):
    """Verifies PyWhatKit WhatsApp messaging initiates sending with feminine Hindi response."""
    success, msg = send_whatsapp_message_via_pywhatkit("919876543210", "Hello Rahul", "rahul", wait_time=10)
    assert success is True
    assert "Rahul ke liye WhatsApp Web par message process shuru kar rahi hoon" in msg
    assert "logged in hai" in msg
    # Verify phone format passed to pywhatkit has +
    mock_pywhatkit.assert_called_once_with(
        phone_no="+919876543210",
        message="Hello Rahul",
        wait_time=10,
        tab_close=False
    )


@patch("pywhatkit.sendwhatmsg_instantly", side_effect=Exception("Connection timeout"))
def test_send_whatsapp_message_via_pywhatkit_failure(mock_pywhatkit):
    """Verifies PyWhatKit error handling and authentication reminder."""
    success, msg = send_whatsapp_message_via_pywhatkit("919876543210", "Hello", "rahul")
    assert success is False
    assert "Connection timeout" in msg
    assert "authenticated" in msg
