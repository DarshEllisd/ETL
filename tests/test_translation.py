import os
import unittest
import tempfile
import shutil
import json
from pipeline import ConversationTranslator

class TestConversationTranslation(unittest.TestCase):
    def setUp(self):
        import logging
        # Clear stale handlers on root logger to avoid FileNotFoundError from other tests' temp dirs
        for handler in logging.root.handlers[:]:
            try:
                handler.close()
            except Exception:
                pass
            logging.root.removeHandler(handler)

        os.environ["ETL_TESTING"] = "true"
        self.test_dir = tempfile.mkdtemp()
        self.input_dir = os.path.join(self.test_dir, "input")
        self.output_dir = os.path.join(self.test_dir, "output")
        os.makedirs(self.input_dir)
        os.makedirs(self.output_dir)

        # Create a mock conversation that has some regional languages
        self.conv = {
            "conversation_id": "conv_translation_test",
            "messages": [
                {"message_id": "msg_gu_1", "speaker": "user", "text": "નમસ્તે, મારે મારા ઓર્ડર વિશે મદદ જોઈએ છે"},
                {"message_id": "msg_en_1", "speaker": "assistant", "text": "Sure, I can help you."}
            ]
        }
        with open(os.path.join(self.input_dir, "conv_translation_test.json"), 'w', encoding='utf-8') as f:
            json.dump(self.conv, f, indent=2, ensure_ascii=False)

        # Create languages.jsonl mapping
        self.languages_path = os.path.join(self.output_dir, "languages.jsonl")
        with open(self.languages_path, 'w', encoding='utf-8') as f:
            f.write(json.dumps({
                "conversation_id": "conv_translation_test",
                "detected_languages": [
                    {"message_id": "msg_gu_1", "languages": ["gu - Gujarati"]},
                    {"message_id": "msg_en_1", "languages": ["en - English"]}
                ]
            }, ensure_ascii=False) + "\n")

        self.translator = ConversationTranslator(
            input_dir=self.input_dir,
            output_dir=self.output_dir
        )

    def tearDown(self):
        import logging
        for handler in logging.root.handlers[:]:
            try:
                handler.close()
            except Exception:
                pass
            logging.root.removeHandler(handler)
        shutil.rmtree(self.test_dir)

    def test_translation_process(self):
        # Mock call_groq_translation to return translated text without calling the API
        self.translator.call_groq_translation = lambda batch: {
            "msg_gu_1": "Hello, I need help with my order"
        }

        # Run process_all
        count = self.translator.process_all()
        self.assertEqual(count, 1)

        # Verify file was updated in-place
        path = os.path.join(self.input_dir, "conv_translation_test.json")
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.assertEqual(data["messages"][0]["text"], "Hello, I need help with my order")
        self.assertEqual(data["messages"][1]["text"], "Sure, I can help you.")

        # Verify translation status file was written
        status_path = os.path.join(self.output_dir, "translation_status.jsonl")
        self.assertTrue(os.path.exists(status_path))
        with open(status_path, 'r', encoding='utf-8') as f:
            status_data = json.loads(f.read().strip())
        self.assertEqual(status_data["conversation_id"], "conv_translation_test")
        self.assertIn("text_hash", status_data)

        # Running again should skip translation (returns 0 because already in status)
        self.translator.call_groq_translation = lambda batch: {
            "msg_gu_1": "Should not be called"
        }
        count2 = self.translator.process_all()
        self.assertEqual(count2, 0)
