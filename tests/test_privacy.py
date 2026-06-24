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
        # Edge cases: emails in punctuation, uppercase, multiple dots
        text = "Contact me at Alice@Gmail.Com, support+alert@shop.co.uk or test.name_123@sub.domain.org!"
        res = self.scrubber.scrub_text(text)
        
        self.assertEqual(res["text"], "Contact me at [EMAIL], [EMAIL] or [EMAIL]!")
        self.assertEqual(res["emails"], 3)

    def test_scrub_phones(self):
        # Edge cases: different prefixes, dashes, continuous digits, spaces
        formats = [
            ("Call +1 (555) 019-9234 now", "Call [PHONE] now", 1),
            ("My number is 555-019-9234.", "My number is [PHONE].", 1),
            ("Text +91 98765-43210 immediately", "Text [PHONE] immediately", 1),
            ("Dial 555.019.9234", "Dial [PHONE]", 1),
            ("Old number: 5550199234", "Old number: [PHONE]", 1),
            ("UK number: +44 20 7946 0958", "UK number: [PHONE]", 1) # Matches full sequence
        ]
        
        for input_text, expected_text, expected_count in formats:
            res = self.scrubber.scrub_text(input_text)
            self.assertEqual(res["text"], expected_text)
            self.assertEqual(res["phones"], expected_count)

    def test_scrub_passwords(self):
        # Edge cases: key-value split formats, casing, helper verbs
        formats = [
            ("The password: myPassword123", "The password: [PASSWORD]", 1),
            ("my PIN=9876", "my PIN: [PASSWORD]", 1),
            ("credential is: Secret_Key", "credential is: [PASSWORD]", 1),
            ("casing: PASS=mySecret", "casing: PASS: [PASSWORD]", 1)
        ]
        for input_text, expected_text, expected_count in formats:
            res = self.scrubber.scrub_text(input_text)
            self.assertEqual(res["text"], expected_text)
            self.assertEqual(res["passwords"], expected_count)

    def test_scrub_addresses(self):
        # Edge cases: casing, street suffixes, ZIP codes
        formats = [
            ("Send to 123 Main Street please.", "Send to [ADDRESS] please.", 1),
            ("We live at 456 Elm Ave, New York.", "We live at [ADDRESS], New York.", 1),
            ("Ship to 99 Broadway Road.", "Ship to [ADDRESS].", 1),
            ("Zip code is 10001.", "Zip code is [ADDRESS].", 1),
            ("Zip 90210-1234", "Zip [ADDRESS]", 1)
        ]
        for input_text, expected_text, expected_count in formats:
            res = self.scrubber.scrub_text(input_text)
            self.assertEqual(res["text"], expected_text)
            self.assertEqual(res["addresses"], expected_count)

    def test_scrub_participant_names(self):
        # Test case-insensitivity, word boundaries, name parts
        names = ["Alice Smith", "Bob", "Jane"]
        text = "Hello Alice Smith, is Jane there? Tell Bobcat we said hi to Bob."
        # Alice Smith is replaced first as "[NAME]"
        # Then Jane is replaced as "[NAME]"
        # Bobcat is NOT replaced since it's not a word boundary match
        # Bob is replaced as "[NAME]"
        res = self.scrubber.scrub_text(text, names)
        
        self.assertEqual(res["text"], "Hello [NAME], is [NAME] there? Tell Bobcat we said hi to [NAME].")
        self.assertGreater(res["names"], 0)

    def test_scrub_conversation_pipeline_full(self):
        conv = {
            "conversation_id": "conv_priv_2",
            "source": "whatsapp",
            "messages": [
                {
                    "message_id": "msg_1",
                    "timestamp": "2026-06-24T10:00:00Z",
                    "speaker": "user",
                    "text": "Hey Alice Smith, call me at 555-019-9234 or email me at alice@gmail.com.",
                    "metadata": {
                        "raw_speaker_name": "Alice Smith"
                    }
                },
                {
                    "message_id": "msg_2",
                    "timestamp": "2026-06-24T10:01:00Z",
                    "speaker": "assistant",
                    "text": "Sure Alice, here is the secret key: 123456. Send to 123 Main St.",
                    "metadata": {
                        "raw_speaker_name": "Jane Support"
                    }
                }
            ],
            "metadata": {
                "raw_speaker_name": "Alice Smith"
            }
        }
        
        file_path = os.path.join(self.input_dir, "conv_2.json")
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(conv, f)
            
        report = self.scrubber.process_all()
        
        self.assertEqual(report["stats"]["total_files_anonymized"], 1)
        self.assertEqual(report["stats"]["total_emails_scrubbed"], 1)
        self.assertEqual(report["stats"]["total_phones_scrubbed"], 1)
        self.assertEqual(report["stats"]["total_passwords_scrubbed"], 1)
        self.assertEqual(report["stats"]["total_addresses_scrubbed"], 1)
        self.assertGreater(report["stats"]["total_names_scrubbed"], 0)
        
        # Verify saved file PII is replaced
        out_path = os.path.join(self.output_dir, "conv_2.json")
        self.assertTrue(os.path.exists(out_path))
        with open(out_path, 'r', encoding='utf-8') as f:
            scrubbed_conv = json.load(f)
            
        # Message 1 text should have phone, email, and name scrubbed
        # Note: "Alice Smith" is replaced with "[NAME]"
        self.assertEqual(
            scrubbed_conv["messages"][0]["text"],
            "Hey [NAME], call me at [PHONE] or email me at [EMAIL]."
        )
        # Message 2 text should have name, password, and address scrubbed
        self.assertEqual(
            scrubbed_conv["messages"][1]["text"],
            "Sure [NAME], here is the secret key: [PASSWORD]. Send to [ADDRESS]."
        )

if __name__ == '__main__':
    unittest.main()
