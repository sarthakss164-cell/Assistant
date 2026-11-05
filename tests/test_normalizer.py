"""
Unit tests for text normalization in Light AI V1.0.
"""

import unittest
from core.normalizer import normalize_text, strip_wake_prefix

class TestNormalizer(unittest.TestCase):

    def test_normalize_text_basic(self):
        self.assertEqual(normalize_text("Open Chrome."), "open chrome")
        self.assertEqual(normalize_text("  Light, Open WhatsApp!  "), "light open whatsapp")
        self.assertEqual(normalize_text("Search Python Tutorials on Google?"), "search python tutorials on google")

    def test_strip_wake_prefix_present(self):
        has_prefix, remainder = strip_wake_prefix("Light, open Chrome")
        self.assertTrue(has_prefix)
        self.assertEqual(remainder, "open chrome")

        has_prefix2, remainder2 = strip_wake_prefix("light who are you")
        self.assertTrue(has_prefix2)
        self.assertEqual(remainder2, "who are you")

        # Devanagari / Hindi phonetic alias 'लाइट'
        has_prefix3, remainder3 = strip_wake_prefix("लाइट open WhatsApp")
        self.assertTrue(has_prefix3)
        self.assertEqual(remainder3, "open whatsapp")

    def test_strip_wake_prefix_missing(self):
        has_prefix, remainder = strip_wake_prefix("open Chrome")
        self.assertFalse(has_prefix)
        self.assertEqual(remainder, "open chrome")

        has_prefix2, remainder2 = strip_wake_prefix("who are you")
        self.assertFalse(has_prefix2)
        self.assertEqual(remainder2, "who are you")

    def test_strip_wake_prefix_internal_or_standalone(self):
        # "Light" standalone
        has_prefix, remainder = strip_wake_prefix("Light")
        self.assertTrue(has_prefix)
        self.assertEqual(remainder, "")

        # Word "light" inside sentence (not at beginning)
        has_prefix2, remainder2 = strip_wake_prefix("turn on the light please")
        self.assertFalse(has_prefix2)
        self.assertEqual(remainder2, "turn on the light please")

if __name__ == "__main__":
    unittest.main()
