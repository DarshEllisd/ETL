import os
import unittest
import tempfile
import shutil
import json
import email
from storage import RawStorage
from connectors import GmailConnector

class TestGmailConnector(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.storage = RawStorage(base_dir=self.test_dir)
        self.connector = GmailConnector(self.storage)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_parse_message_simple(self):
        # Create a simple raw email string
        eml_str = (
            "Message-ID: <test1234@mail.gmail.com>\n"
            "From: alice@gmail.com\n"
            "To: bob@gmail.com\n"
            "Subject: Tracking Inquiry\n"
            "Date: Wed, 24 Jun 2026 10:00:00 +0000\n"
            "Content-Type: text/plain; charset=\"utf-8\"\n"
            "\n"
            "Hello Bob,\n"
            "Where is my package?\n"
        )
        msg = email.message_from_string(eml_str)
        parsed = self.connector.parse_message(msg)
        
        self.assertEqual(parsed["source"], "gmail")
        self.assertEqual(parsed["headers"]["Message-ID"], "<test1234@mail.gmail.com>")
        self.assertEqual(parsed["headers"]["From"], "alice@gmail.com")
        self.assertEqual(parsed["headers"]["Subject"], "Tracking Inquiry")
        self.assertEqual(parsed["body"], "Hello Bob,\nWhere is my package?")

    def test_ingest_eml_file(self):
        eml_str = (
            "Message-ID: <emlfile5678@mail.gmail.com>\n"
            "From: charlie@gmail.com\n"
            "To: support@gmail.com\n"
            "Subject: Order Issue\n"
            "\n"
            "My widget is broken.\n"
        )
        # Write this eml to a temporary file
        temp_eml_path = os.path.join(self.test_dir, "test_email.eml")
        with open(temp_eml_path, "w", encoding="utf-8") as f:
            f.write(eml_str)
            
        saved_json_path = self.connector.ingest_eml_file(temp_eml_path)
        self.assertTrue(os.path.exists(saved_json_path))
        self.assertTrue(saved_json_path.endswith("email_emlfile5678_mail_gmail_com.json"))
        
        with open(saved_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        self.assertEqual(data["headers"]["From"], "charlie@gmail.com")
        self.assertEqual(data["body"], "My widget is broken.")

if __name__ == '__main__':
    unittest.main()
