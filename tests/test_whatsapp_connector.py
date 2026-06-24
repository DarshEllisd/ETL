import os
import unittest
import tempfile
import shutil
import json
from storage import RawStorage
from connectors import WhatsAppConnector

class TestWhatsAppConnector(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.storage = RawStorage(base_dir=self.test_dir)
        self.connector = WhatsAppConnector(self.storage)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_parse_log_android_format(self):
        chat_content = (
            "19/06/2026, 12:30 - John Doe: Hello Alice!\n"
            "19/06/2026, 12:31 - Alice: Hi John.\n"
        )
        parsed = self.connector.parse_log(chat_content)
        
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["sender"], "John Doe")
        self.assertEqual(parsed[0]["text"], "Hello Alice!")
        self.assertEqual(parsed[0]["raw_date"], "19/06/2026")
        self.assertEqual(parsed[0]["raw_time"], "12:30")
        
        self.assertEqual(parsed[1]["sender"], "Alice")
        self.assertEqual(parsed[1]["text"], "Hi John.")

    def test_parse_log_ios_format(self):
        chat_content = (
            "[19/06/26, 12:30:15] John Doe: Hello Alice!\n"
            "[19/06/26, 12:31:02] Alice: Hi John.\n"
        )
        parsed = self.connector.parse_log(chat_content)
        
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["sender"], "John Doe")
        self.assertEqual(parsed[0]["text"], "Hello Alice!")
        self.assertEqual(parsed[0]["raw_date"], "19/06/26")
        self.assertEqual(parsed[0]["raw_time"], "12:30:15")

    def test_parse_log_multiline_continuation(self):
        chat_content = (
            "19/06/2026, 12:30 - John Doe: Line 1 of message.\n"
            "Line 2 of message.\n"
            "Line 3 of message.\n"
            "19/06/2026, 12:31 - Alice: Reply here.\n"
        )
        parsed = self.connector.parse_log(chat_content)
        
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["sender"], "John Doe")
        self.assertEqual(
            parsed[0]["text"], 
            "Line 1 of message.\nLine 2 of message.\nLine 3 of message."
        )
        self.assertEqual(parsed[1]["sender"], "Alice")
        self.assertEqual(parsed[1]["text"], "Reply here.")

    def test_ingest_chat_file(self):
        chat_content = (
            "19/06/2026, 12:30 - John Doe: Simple message.\n"
        )
        temp_log_path = os.path.join(self.test_dir, "test_chat.txt")
        with open(temp_log_path, "w", encoding="utf-8") as f:
            f.write(chat_content)
            
        saved_json_path = self.connector.ingest_chat_file(temp_log_path)
        self.assertTrue(os.path.exists(saved_json_path))
        self.assertTrue(saved_json_path.endswith("whatsapp_test_chat.json"))
        
        with open(saved_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        self.assertEqual(data["source"], "whatsapp")
        self.assertEqual(len(data["messages"]), 1)
        self.assertEqual(data["messages"][0]["sender"], "John Doe")
        self.assertEqual(data["messages"][0]["text"], "Simple message.")

if __name__ == '__main__':
    unittest.main()
