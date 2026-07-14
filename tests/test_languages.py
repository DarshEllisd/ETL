import os
import unittest
import tempfile
import shutil
import json
from pipeline import ConversationAnnotator

class TestLanguagesDetection(unittest.TestCase):
    def setUp(self):
        os.environ["ETL_TESTING"] = "true"
        self.test_dir = tempfile.mkdtemp()
        self.input_dir = os.path.join(self.test_dir, "input")
        self.output_dir = os.path.join(self.test_dir, "output")
        os.makedirs(self.input_dir)
        os.makedirs(self.output_dir)

        self.annotator = ConversationAnnotator(
            input_dir=self.input_dir,
            output_dir=self.output_dir
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_english_only_detection(self):
        conv = {
            "conversation_id": "conv_en",
            "messages": [
                {"message_id": "m1", "speaker": "user", "text": "Hello support, I need help with my account."},
                {"message_id": "m2", "speaker": "assistant", "text": "Sure, I can assist you with your account details."}
            ]
        }
        res = self.annotator.fallback_annotate(conv)
        langs = res.get("detected_languages", [])
        self.assertEqual(len(langs), 2)
        self.assertEqual(langs[0]["languages"], ["en - English"])
        self.assertEqual(langs[1]["languages"], ["en - English"])

    def test_devanagari_hindi_detection(self):
        conv = {
            "conversation_id": "conv_hi_dev",
            "messages": [
                {"message_id": "m1", "speaker": "user", "text": "नमस्ते, मुझे मदद चाहिए।"},
                {"message_id": "m2", "speaker": "assistant", "text": "जी हाँ, मैं आपकी मदद कर सकता हूँ।"}
            ]
        }
        res = self.annotator.fallback_annotate(conv)
        langs = res.get("detected_languages", [])
        self.assertEqual(len(langs), 2)
        self.assertIn("hi - Hindi", langs[0]["languages"])
        self.assertIn("hi - Hindi", langs[1]["languages"])

    def test_hinglish_detection(self):
        conv = {
            "conversation_id": "conv_hinglish",
            "messages": [
                {"message_id": "m1", "speaker": "user", "text": "aaj office meri update nai rahe hain"},
                {"message_id": "m2", "speaker": "assistant", "text": "Koi issue nahi hai, main check karta hoon"}
            ]
        }
        res = self.annotator.fallback_annotate(conv)
        langs = res.get("detected_languages", [])
        self.assertEqual(len(langs), 2)
        self.assertIn("hi - Hindi", langs[0]["languages"])
        self.assertIn("hi - Hindi", langs[1]["languages"])

    def test_pure_english_not_hindi(self):
        """Sentences like 'He told me there is some work' should NOT be Hindi"""
        conv = {
            "conversation_id": "conv_en_pure",
            "messages": [
                {"message_id": "m1", "speaker": "user", "text": "He told me there is some work for figuring out any logical error in a validation program"},
                {"message_id": "m2", "speaker": "user", "text": "I asked him to send me i didn't get it till now"}
            ]
        }
        res = self.annotator.fallback_annotate(conv)
        langs = res.get("detected_languages", [])
        self.assertEqual(len(langs), 2)
        self.assertEqual(langs[0]["languages"], ["en - English"])
        self.assertEqual(langs[1]["languages"], ["en - English"])

    def test_gujarati_unicode_detection(self):
        conv = {
            "conversation_id": "conv_gu",
            "messages": [
                {"message_id": "m1", "speaker": "user", "text": "નમસ્તે, મારે મારા ઓર્ડર વિશે મદદ જોઈએ છે"}
            ]
        }
        res = self.annotator.fallback_annotate(conv)
        langs = res.get("detected_languages", [])
        self.assertIn("gu - Gujarati", langs[0]["languages"])

    def test_marathi_unicode_detection(self):
        conv = {
            "conversation_id": "conv_mr",
            "messages": [
                {"message_id": "m1", "speaker": "user", "text": "माझा पासवर्ड काम करत नाही"}
            ]
        }
        res = self.annotator.fallback_annotate(conv)
        langs = res.get("detected_languages", [])
        self.assertIn("hi - Hindi", langs[0]["languages"])  # Devanagari triggers Hindi

    def test_romanized_marathi_detection(self):
        conv = {
            "conversation_id": "conv_mr_rom",
            "messages": [
                {"message_id": "m1", "speaker": "user", "text": "namaskar, mala ek issue aahe majhya account sobat"},
                {"message_id": "m2", "speaker": "user", "text": "dhanyavad, sagla theek aahe aata"}
            ]
        }
        res = self.annotator.fallback_annotate(conv)
        langs = res.get("detected_languages", [])
        self.assertIn("mr - Marathi", langs[0]["languages"])
        self.assertIn("mr - Marathi", langs[1]["languages"])

    def test_romanized_gujarati_detection(self):
        conv = {
            "conversation_id": "conv_gu_rom",
            "messages": [
                {"message_id": "m1", "speaker": "user", "text": "tamne aabhar for helping, majama chho?"}
            ]
        }
        res = self.annotator.fallback_annotate(conv)
        langs = res.get("detected_languages", [])
        self.assertIn("gu - Gujarati", langs[0]["languages"])

    def test_unrecognized_lang_fallback(self):
        conv = {
            "conversation_id": "conv_unrecognized",
            "messages": [
                {"message_id": "m1", "speaker": "user", "text": "مرحبا بك في موقعنا"}
            ]
        }
        res = self.annotator.fallback_annotate(conv)
        langs = res.get("detected_languages", [])
        self.assertIn("no lang found - No Language Found", langs[0]["languages"])

if __name__ == '__main__':
    unittest.main()
