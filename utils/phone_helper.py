"""
Phone helper module for Light AI V1.0.
Provides deterministic Indian mobile phone normalization, validation, and privacy masking.
"""

import re

# Strict ASCII digit pattern to disallow non-ASCII Unicode numerals
ASCII_DIGITS_REGEX = re.compile(r"^[0-9]+$")

def normalize_indian_phone(raw_phone: str) -> tuple[bool, str, str]:
    """
    Deterministically normalizes and validates an Indian mobile number using strict ASCII digits.
    Returns: (is_valid: bool, normalized_phone: str, log_or_error_message: str)
    
    Supported input formats:
      1. International (+ prefix):
         - Must start with '+' followed by country code '91' and 10 ASCII digits starting with 6-9.
         - e.g. "+919893371769", "+91 98933 71769", "+91-98933-71769" -> "919893371769"
         - Any other '+' prefix (e.g. +1, +44, +98) is strictly REJECTED.
      2. Domestic formats (no '+' prefix):
         - 10 digits starting with 6-9: "9893371769" -> "919893371769"
         - 11 digits starting with trunk '0' followed by 6-9: "09893371769" -> "919893371769"
         - 12 digits starting with '91' followed by 6-9: "919893371769" -> "919893371769"
      
    Delimiter handling:
      - Embedded whitespace, dashes, dots, and parentheses are stripped.
      
    Rejection rules:
      - Any non-ASCII numerals (e.g. Unicode digits) or non-numeric characters.
      - Any '+' prefixed number that is not explicitly '+91' + 10 valid mobile digits.
      - Numbers with invalid digit counts or invalid leading mobile digits (not 6-9).
    """
    if not raw_phone or not isinstance(raw_phone, str):
        return False, "", "Phone number is empty or non-string."

    cleaned_raw = raw_phone.strip()
    starts_with_plus = cleaned_raw.startswith("+")

    # 1. Strip common formatting delimiters
    cleaned = re.sub(r"[\s\-\.\(\)]", "", cleaned_raw)

    # 2. Handle '+' prefixed international format
    if starts_with_plus or cleaned.startswith("+"):
        if not cleaned.startswith("+"):
            return False, "", "Malformed '+' prefix formatting."
        without_plus = cleaned[1:]

        # Must be strict ASCII digits
        if not ASCII_DIGITS_REGEX.fullmatch(without_plus):
            return False, "", "Phone number contains non-ASCII or invalid characters."

        # Must be exactly 12 digits starting with '91' and mobile series 6-9
        if len(without_plus) == 12 and without_plus.startswith("91") and without_plus[2] in "6789":
            normalized = without_plus
        else:
            return False, "", "Unsupported international number: only Indian numbers (+91 followed by valid 10-digit mobile) are supported."

    # 3. Handle Domestic formats (no '+' prefix)
    else:
        # Must be strict ASCII digits
        if not ASCII_DIGITS_REGEX.fullmatch(cleaned):
            return False, "", "Phone number contains non-ASCII or invalid characters."

        # Case A: 10-digit mobile number starting with 6-9
        if len(cleaned) == 10 and cleaned[0] in "6789":
            normalized = f"91{cleaned}"
        # Case B: 11-digit number with leading trunk zero '0' followed by 6-9
        elif len(cleaned) == 11 and cleaned[0] == "0" and cleaned[1] in "6789":
            normalized = f"91{cleaned[1:]}"
        # Case C: 12-digit number starting with '91' followed by 6-9
        elif len(cleaned) == 12 and cleaned.startswith("91") and cleaned[2] in "6789":
            normalized = cleaned
        else:
            return False, "", "Malformed domestic Indian phone number: incorrect length or invalid mobile prefix."

    # 4. Generate privacy-safe masked string for logging (e.g. '91******1769')
    masked = f"{normalized[:2]}******{normalized[-4:]}"
    return True, normalized, masked
