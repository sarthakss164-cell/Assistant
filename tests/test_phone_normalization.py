"""
Unit tests for deterministic Indian phone normalization, validation, and privacy masking.
"""

import unittest
from utils.phone_helper import normalize_indian_phone

class TestPhoneNormalization(unittest.TestCase):

    def test_valid_domestic_10_digit(self):
        # 10 digits starting with 6-9
        valid, normalized, masked = normalize_indian_phone("9893371769")
        self.assertTrue(valid)
        self.assertEqual(normalized, "919893371769")
        self.assertEqual(masked, "91******1769")

    def test_valid_domestic_10_digit_with_spaces_and_dashes(self):
        valid, normalized, masked = normalize_indian_phone(" 98933-71769 ")
        self.assertTrue(valid)
        self.assertEqual(normalized, "919893371769")

        valid2, normalized2, masked2 = normalize_indian_phone("(86524) 84743")
        self.assertTrue(valid2)
        self.assertEqual(normalized2, "918652484743")

    def test_valid_domestic_11_digit_with_trunk_zero(self):
        # Leading 0 followed by 10 valid mobile digits
        valid, normalized, masked = normalize_indian_phone("09893371769")
        self.assertTrue(valid)
        self.assertEqual(normalized, "919893371769")
        self.assertEqual(masked, "91******1769")

        valid2, normalized2, _ = normalize_indian_phone("0 79772 08295")
        self.assertTrue(valid2)
        self.assertEqual(normalized2, "917977208295")

    def test_valid_domestic_12_digit_already_prefixed(self):
        # 12 digits starting with 91 - must not duplicate country code to 9191...
        valid, normalized, masked = normalize_indian_phone("919893371769")
        self.assertTrue(valid)
        self.assertEqual(normalized, "919893371769")
        self.assertFalse(normalized.startswith("9191"))
        self.assertEqual(masked, "91******1769")

    def test_valid_international_plus_91(self):
        # Starts with +91 followed by 10 valid digits
        valid, normalized, masked = normalize_indian_phone("+919893371769")
        self.assertTrue(valid)
        self.assertEqual(normalized, "919893371769")
        self.assertEqual(masked, "91******1769")

        valid2, normalized2, _ = normalize_indian_phone("+91 86524 84743")
        self.assertTrue(valid2)
        self.assertEqual(normalized2, "918652484743")

        valid3, normalized3, _ = normalize_indian_phone("+91-95066-86315")
        self.assertTrue(valid3)
        self.assertEqual(normalized3, "919506686315")

    def test_reject_foreign_country_codes(self):
        # Foreign country codes must NEVER be silently reinterpreted as domestic Indian numbers
        valid_us, _, msg_us = normalize_indian_phone("+1 555 123 4567")
        self.assertFalse(valid_us)
        self.assertIn("international", msg_us.lower())

        valid_uk, _, msg_uk = normalize_indian_phone("+44 7911 123456")
        self.assertFalse(valid_uk)

        valid_iran, _, msg_iran = normalize_indian_phone("+98 933 71769")
        self.assertFalse(valid_iran)

    def test_reject_malformed_plus_prefixes(self):
        # Malformed + numbers
        valid, _, _ = normalize_indian_phone("+9")
        self.assertFalse(valid)

        # Trunk 0 with +91 is malformed
        valid2, _, _ = normalize_indian_phone("+9109893371769")
        self.assertFalse(valid2)

        # Too short
        valid3, _, _ = normalize_indian_phone("+9112345")
        self.assertFalse(valid3)

    def test_reject_unicode_numerals(self):
        # Devanagari numerals must be rejected
        valid, _, msg = normalize_indian_phone("+91९८९३३७१७६९")
        self.assertFalse(valid)

        # Superscript numerals
        valid2, _, _ = normalize_indian_phone("9893371769²")
        self.assertFalse(valid2)

    def test_reject_invalid_mobile_series(self):
        # Indian mobile numbers must start with 6, 7, 8, or 9
        valid, _, _ = normalize_indian_phone("5123456789")
        self.assertFalse(valid)

        valid2, _, _ = normalize_indian_phone("+915123456789")
        self.assertFalse(valid2)

        valid3, _, _ = normalize_indian_phone("1234567890")
        self.assertFalse(valid3)

    def test_reject_invalid_length_and_letters(self):
        valid, _, _ = normalize_indian_phone("98933")
        self.assertFalse(valid)

        valid2, _, _ = normalize_indian_phone("919893371769999")
        self.assertFalse(valid2)

        valid3, _, _ = normalize_indian_phone("98933abcde")
        self.assertFalse(valid3)

        valid4, _, _ = normalize_indian_phone("")
        self.assertFalse(valid4)

        valid5, _, _ = normalize_indian_phone(None)
        self.assertFalse(valid5)

if __name__ == "__main__":
    unittest.main()
