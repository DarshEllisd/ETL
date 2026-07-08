import os
import unittest
import tempfile
import shutil
import json
from pipeline import PrivacyScrubber

class TestPrivacyScrubber(unittest.TestCase):
    def setUp(self):
        os.environ["ETL_TESTING"] = "true"
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

        # Additional Edge cases
        more_cases = [
            ("<alice.bob@sub.example.com>", "<[EMAIL]>"),
            ("charlie@gmail.com is my email", "[EMAIL] is my email"),
            ("My email is charlie@gmail.com", "My email is [EMAIL]"),
            ("test@my-domain.com", "[EMAIL]"),
            ("user+label@domain.com", "[EMAIL]"),
            ("USER@DOMAIN.CO.UK", "[EMAIL]"),
            ("Send to one@test.com,two@test.com;three@test.com", "Send to [EMAIL],[EMAIL];[EMAIL]"),
            ("Not an email: user@domain, @domain.com, user@.com, user@domain..com", "Not an email: user@domain, @domain.com, user@.com, [EMAIL]"),
        ]
        for input_text, expected_text in more_cases:
            res = self.scrubber.scrub_text(input_text)
            self.assertEqual(res["text"], expected_text)

    def test_scrub_phones(self):
        # Edge cases: different prefixes, dashes, continuous digits, spaces
        formats = [
            ("Call +1 (555) 019-9234 now", "Call [PHONE] now", 1),
            ("My number is 555-019-9234.", "My number is [PHONE].", 1),
            ("Text +91 98765-43210 immediately", "Text [PHONE] immediately", 1),
            ("Dial 555.019.9234", "Dial [PHONE]", 1),
            ("Old number: 5550199234", "Old number: [PHONE]", 1),
            ("UK number: +44 20 7946 0958", "UK number: [PHONE]", 1),
            
            # Additional Edge cases
            ("Call +15550199234 today", "Call [PHONE] today", 1),
            ("Dial 0015550199234", "Dial [PHONE]", 1),
            ("Indian number: 9876543210", "Indian number: [PHONE]", 1),
            ("Dashed Indian: 98765-43210", "Dashed Indian: [PHONE]", 1),
            ("Spaced US: 555 019 9234", "Spaced US: [PHONE]", 1),
            ("UK standard: 020 7946 0958", "UK standard: [PHONE]", 1),
            ("UK mobile: 07911 123456", "UK mobile: [PHONE]", 1),
            ("With leading +: +1-555-019-9234", "With leading +: [PHONE]", 1),
            ("Without boundaries: 12345678901234", "Without boundaries: 12345678901234", 0),
            ("Standard date like 2026-06-24", "Standard date like 2026-06-24", 0),
            ("IP Address like 192.168.1.1", "IP Address like 192.168.1.1", 0)
        ]
        
        for input_text, expected_text, expected_count in formats:
            res = self.scrubber.scrub_text(input_text)
            self.assertEqual(res["text"], expected_text)
            self.assertEqual(res["phones"], expected_count)

    def test_scrub_passwords(self):
        # Edge cases: key-value split formats, casing, helper verbs, special chars
        formats = [
            ("The password: myPassword123", "The password: [PASSWORD]", 1),
            ("my PIN=9876", "my PIN: [PASSWORD]", 1),
            ("credential is: Secret_Key", "credential is: [PASSWORD]", 1),
            ("casing: PASS=mySecret", "casing: PASS: [PASSWORD]", 1),
            
            # Additional Edge cases
            ("password:1234", "password:[PASSWORD]", 1),
            ("pin = 5678", "pin: [PASSWORD]", 1),
            ("secret key is: my_secret", "secret key is: [PASSWORD]", 1),
            ("PASS: abc", "PASS: [PASSWORD]", 1),
            ("Secret: xyz", "Secret: [PASSWORD]", 1),
            ("KEY = foo", "KEY: [PASSWORD]", 1),
            ("password: Secret#123", "password: [PASSWORD]", 1),
            ("passwd: my-password@1.", "passwd: [PASSWORD].", 1),
            ("Multiple passwords: pin: 1234, key = abcd", "Multiple passwords: pin: [PASSWORD], key: [PASSWORD]", 2),
            ("False positive: the key aspect is high", "False positive: the key aspect is high", 0)
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
            ("Zip 90210-1234", "Zip [ADDRESS]", 1),
            
            # Additional Edge cases
            ("Delivery to 1600 Amphitheatre Parkway", "Delivery to [ADDRESS]", 1),
            ("Meet at 555 Market Street", "Meet at [ADDRESS]", 1),
            ("Address is 12 main st", "Address is [ADDRESS]", 1),
            ("Visit 789 5th St.", "Visit [ADDRESS].", 1),
            ("Location: 42 2nd Avenue", "Location: [ADDRESS]", 1),
            ("Stop by 100 Main Road, Suite A, New York.", "Stop by [ADDRESS], Suite A, New York.", 1),
            ("Postal code 95051-1234", "Postal code [ADDRESS]", 1),
            ("I bought 3 items from the store.", "I bought 3 items from the store.", 0),
            ("We have 100 ways to do this.", "We have 100 ways to do this.", 0),
            ("I placed order #12345.", "I placed order #12345.", 0),
            ("Price is $90210.", "Price is $90210.", 0),
            ("Ref number is #90210-1234.", "Ref number is #90210-1234.", 0)
        ]
        for input_text, expected_text, expected_count in formats:
            res = self.scrubber.scrub_text(input_text)
            self.assertEqual(res["text"], expected_text)
            self.assertEqual(res["addresses"], expected_count)

    def test_scrub_participant_names(self):
        # Test case-insensitivity, word boundaries, name parts, hyphenated names, apostrophes
        names = ["Alice Smith", "Bob", "Jane", "Jean-Luc", "O'Connor"]
        text = "Hello Alice Smith, is Jane there? Tell Bobcat we said hi to Bob. Ask Jean-Luc and O'Connor."
        res = self.scrubber.scrub_text(text, names)
        
        self.assertEqual(res["text"], "Hello [NAME], is [NAME] there? Tell Bobcat we said hi to [NAME]. Ask [NAME] and [NAME].")
        self.assertEqual(res["names"], 5)

        # Additional Edge cases
        res2 = self.scrubber.scrub_text("alice smith and ALICE SMITH and aLiCe sMiTh", ["Alice Smith"])
        self.assertEqual(res2["text"], "[NAME] and [NAME] and [NAME]")
        
        res3 = self.scrubber.scrub_text("Malice and Bobcat", ["Alice", "Bob"])
        self.assertEqual(res3["text"], "Malice and Bobcat")
        self.assertEqual(res3["names"], 0)

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
