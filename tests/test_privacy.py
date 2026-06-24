import os
import unittest
import tempfile
import shutil
import json
from pipeline import PrivacyScrubber

class TestPrivacyScrubber(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.input_dir = os.path.join(self.test_dir, "input")
        self.output_dir = os.path.join(self.test_dir, "output")
        os.makedirs(self.input_dir)
        os.makedirs(self.output_dir)
        
        self.report_path = os.path.join(self.test_dir, "privacy_report.json")
        self.scrubber = PrivacyScrubber(self.input_dir, self.output_dir, self.report_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_scrub_emails(self):
        text = "Contact me at alice@gmail.com or support@shop.com."
        scrubbed, e_count, p_count = self.scrubber.scrub_text(text)
        
        self.assertEqual(scrubbed, "Contact me at [EMAIL] or [EMAIL].")
        self.assertEqual(e_count, 2)
        self.assertEqual(p_count, 0)

    def test_scrub_phones(self):
        # Test various phone formats
        formats = [
            ("Call +1 (555) 019-9234 now", "Call [PHONE] now", 1),
            ("My number is 555-019-9234.", "My number is [PHONE].", 1),
            ("Text +91 98765-43210 immediately", "Text [PHONE] immediately", 1),
            ("Dial 555.019.9234", "Dial [PHONE]", 1),
            ("Old number: 5550199234", "Old number: [PHONE]", 1)
        ]
        
        for input_text, expected_text, expected_count in formats:
            scrubbed, e_count, p_count = self.scrubber.scrub_text(input_text)
            self.assertEqual(scrubbed, expected_text)
            self.assertEqual(p_count, expected_count)
            self.assertEqual(e_count, 0)

    def test_scrub_conversation_pipeline(self):
        conv = {
            "conversation_id": "conv_priv_1",
            "source": "whatsapp",
            "messages": [
                {
                    "message_id": "msg_1",
                    "timestamp": "2026-06-24T10:00:00Z",
                    "speaker": "user",
                    "text": "Send it to charlie@gmail.com or call me at 555-019-9234."
                },
                {
                    "message_id": "msg_2",
                    "timestamp": "2026-06-24T10:01:00Z",
                    "speaker": "assistant",
                    "text": "Sure. I will email you at [EMAIL] or call [PHONE] if needed."  # Check mock/already redacted or clean
                }
            ]
        }
        
        file_path = os.path.join(self.input_dir, "conv_1.json")
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(conv, f)
            
        report = self.scrubber.process_all()
        
        self.assertEqual(report["stats"]["total_files_anonymized"], 1)
        self.assertEqual(report["stats"]["total_emails_scrubbed"], 1)
        self.assertEqual(report["stats"]["total_phones_scrubbed"], 1)
        
        # Verify saved file PII is replaced
        out_path = os.path.join(self.output_dir, "conv_1.json")
        self.assertTrue(os.path.exists(out_path))
        with open(out_path, 'r', encoding='utf-8') as f:
            scrubbed_conv = json.load(f)
            
        self.assertEqual(
            scrubbed_conv["messages"][0]["text"],
            "Send it to [EMAIL] or call me at [PHONE]."
        )
        self.assertEqual(scrubbed_conv["metadata"]["pii_emails_scrubbed"], 1)
        self.assertEqual(scrubbed_conv["metadata"]["pii_phones_scrubbed"], 1)

if __name__ == '__main__':
    unittest.main()
