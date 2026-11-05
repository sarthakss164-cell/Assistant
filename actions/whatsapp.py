"""
WhatsApp action for Light AI V1.0.
Handles contact lookup, phone normalization, WhatsApp Web in Brave,
and messaging via PyWhatKit with explicit user confirmation.
Never claims delivery without verification. Protects privacy by masking phone numbers in logs.
"""

import json
import os
import re
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

from config.settings import CONTACTS_FILE
from utils.logger import logger, mask_phone_for_log
from utils.phone_helper import normalize_indian_phone
from actions.browser import open_whatsapp_web

MAX_DISAMBIGUATION_CANDIDATES = 4


def load_contacts(contacts_path: Path = CONTACTS_FILE) -> Dict[str, str]:
    """
    Loads contacts from the local contacts JSON file.
    Keys are normalized to lowercase.
    """
    if not contacts_path.exists():
        logger.warning(f"Contacts file not found at: {contacts_path}")
        return {}

    try:
        with open(contacts_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {k.strip().lower(): str(v).strip() for k, v in data.items()}
    except Exception as e:
        logger.error(f"Failed to read contacts JSON: {e}")
        return {}


def find_matching_contacts(
    contact_query: str,
    contacts: Optional[Dict[str, str]] = None
) -> List[str]:
    """
    Deterministically finds matching contact keys from the contacts book.
    Rules:
      1. Normalizes contact_query: strip and lowercase.
      2. Exact Match Priority: If contact_query matches a contact key exactly,
         returns [exact_key] immediately, superseding partial matches.
      3. Partial Matching (if no exact match):
         Matches contact keys where contact_query is a word prefix or whole token.
         e.g., query 'rahul' matches 'rahul office' and 'rahul personal'.
      4. Stable Ordering: Alphabetically sorted by contact name.
      5. Deduplicated: Unique keys only.
    """
    if contacts is None:
        contacts = load_contacts()

    clean_query = (contact_query or "").strip().lower()
    if not clean_query or not contacts:
        return []

    # 1. Exact match takes strict priority
    if clean_query in contacts:
        return [clean_query]

    # 2. Deterministic partial / token / prefix matching
    matches: List[str] = []
    for key in sorted(contacts.keys()):
        tokens = key.split()
        if any(t == clean_query or t.startswith(clean_query) for t in tokens):
            matches.append(key)
        elif key.startswith(clean_query):
            matches.append(key)

    # Deduplicate while preserving alphabetical order
    seen = set()
    ordered_matches: List[str] = []
    for m in matches:
        if m not in seen:
            seen.add(m)
            ordered_matches.append(m)

    return ordered_matches


def resolve_contact_phone(contact_name: str, contacts: Optional[Dict[str, str]] = None) -> Tuple[Optional[str], Optional[str]]:
    """
    Resolves contact name to a normalized Indian phone number (91XXXXXXXXXX).
    Returns:
        (normalized_phone: Optional[str], error_message: Optional[str])
    """
    if contacts is None:
        contacts = load_contacts()

    clean_name = contact_name.strip().lower()
    if not clean_name:
        return None, "Contact ka naam nahi bataya gaya."

    if clean_name not in contacts:
        matches = find_matching_contacts(clean_name, contacts)
        if len(matches) == 1:
            clean_name = matches[0]
        else:
            return None, f"Maaf kijiye, '{contact_name}' contacts mein nahi mila."

    raw_phone = contacts[clean_name]
    is_valid, normalized_phone, masked_or_err = normalize_indian_phone(raw_phone)

    if not is_valid:
        logger.error(f"Phone validation failed for contact '{contact_name}': {masked_or_err}")
        return None, f"Contact '{contact_name}' ka phone number invalid hai."

    logger.info(f"Resolved contact '{contact_name}' -> {masked_or_err}")
    return normalized_phone, None


def open_whatsapp_web() -> Tuple[bool, str]:
    """
    Opens WhatsApp Web in preferred browser, reusing an existing instance.
    """
    from actions.browser import open_whatsapp_web as browser_open_whatsapp_web
    return browser_open_whatsapp_web()


def send_whatsapp_message_via_pywhatkit(
    normalized_phone: str,
    message: str,
    contact_name: str = "",
    wait_time: int = 15
) -> Tuple[bool, str]:
    """
    Initiates WhatsApp messaging using PyWhatKit in the configured browser.
    Formats phone with '+' prefix (e.g., +91XXXXXXXXXX).
    Reports honest status (does not claim delivered).
    """
    clean_digits = re.sub(r"\D", "", normalized_phone)
    if not clean_digits:
        return False, "Phone number invalid hai."

    phone_e164 = f"+{clean_digits}"
    masked = mask_phone_for_log(phone_e164)
    name_display = contact_name.capitalize() if contact_name else "Contact"

    logger.info(f"Initiating PyWhatKit WhatsApp send to {masked} (wait_time={wait_time}s)...")
    try:
        import pywhatkit
        pywhatkit.sendwhatmsg_instantly(
            phone_no=phone_e164,
            message=message,
            wait_time=wait_time,
            tab_close=False
        )
        status_msg = (
            f"{name_display} ke liye WhatsApp Web par message process shuru kar rahi hoon. "
            f"Kripya ensure karein ki WhatsApp Web logged in hai."
        )
        return True, status_msg
    except Exception as e:
        logger.error(f"PyWhatKit WhatsApp sending failed for {masked}: {e}")
        return False, f"WhatsApp message bhejne mein dikkat aayi: {e}. Kripya check karein ki WhatsApp Web authenticated hai."


def build_whatsapp_uris(normalized_phone: str, message: str) -> Tuple[str, str]:
    """
    Constructs the desktop URI and web fallback URL with safe URL encoding.
    Returns:
        (desktop_uri, web_url)
    """
    encoded_message = urllib.parse.quote(message)
    desktop_uri = f"whatsapp://send?phone={normalized_phone}&text={encoded_message}"
    web_url = f"https://web.whatsapp.com/send?phone={normalized_phone}&text={encoded_message}"
    return desktop_uri, web_url


def stage_whatsapp_message(
    normalized_phone: str,
    message: str,
    contact_name: str = ""
) -> Tuple[bool, str]:
    """
    Opens WhatsApp Web in Brave with staged message parameters for manual sending.
    """
    _, web_url = build_whatsapp_uris(normalized_phone, message)
    name_display = contact_name.capitalize() if contact_name else "Contact"

    try:
        from actions.browser import open_in_brave
        logger.info(f"Staging message in Brave for {mask_phone_for_log(normalized_phone)}")
        open_in_brave(web_url)
        status_msg = (
            f"{name_display} ke liye WhatsApp message stage kar diya gaya hai. "
            f"Kripya message bhejne ke liye Send button dabayein."
        )
        return True, status_msg
    except Exception as e:
        logger.error(f"Failed to stage WhatsApp message in Brave: {e}")
        return False, "WhatsApp open karne mein dikkat aayi."
