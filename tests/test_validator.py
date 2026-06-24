import os
import unittest
import tempfile
import shutil
import json
from pipeline import ConversationValidator

class TestConversationValidator(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.input_dir = os.path.join(self.test_dir, "input")
        os.makedirs(self.input_dir)
        self.report_path = os.path.join(self.test_dir, "report.json")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_validator_clean_conversation(self):
        conv = {
            "conversation_id": "clean_1",
            "source": "gmail",
            "start_timestamp": "2026-06-24T10:00:00Z",
            "end_timestamp": "2026-06-24T10:05:00Z",
            "messages": [
                {
                    "message_id": "msg_1",
                    "conversation_id": "clean_1",
                    "timestamp": "2026-06-24T10:00:00Z",
                    "speaker": "user",
                    "text": "Hello support"
                },
                {
                    "message_id": "msg_2",
                    "conversation_id": "clean_1",
                    "timestamp": "2026-06-24T10:05:00Z",
                    "speaker": "assistant",
                    "text": "Hello customer"
                }
            ]
        }
        
        file_path = os.path.join(self.input_dir, "clean_1.json")
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(conv, f)
            
        validator = ConversationValidator(self.input_dir, self.report_path)
        report = validator.validate_all()
        
        self.assertEqual(report["stats"]["total_files_checked"], 1)
        self.assertEqual(report["stats"]["total_errors"], 0)
        self.assertEqual(report["stats"]["status"], "PASS")
        self.assertEqual(len(report["failures"]), 0)

    def test_validator_dirty_conversation(self):
        # Errors: Invalid speaker, empty body, timestamp out of order
        conv = {
            "conversation_id": "dirty_1",
            "source": "gmail",
            "start_timestamp": "2026-06-24T10:00:00Z",
            "end_timestamp": "2026-06-24T10:05:00Z",
            "messages": [
                {
                    "message_id": "msg_1",
                    "conversation_id": "dirty_1",
                    "timestamp": "2026-06-24T10:10:00Z", # Out of order
                    "speaker": "unauthorized_role",     # Error
                    "text": "   "                       # Empty text
                },
                {
                    "message_id": "msg_2",
                    "conversation_id": "dirty_1",
                    "timestamp": "2026-06-24T10:05:00Z",
                    "speaker": "assistant",
                    "text": "Valid reply"
                }
            ]
        }
        
        file_path = os.path.join(self.input_dir, "dirty_1.json")
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(conv, f)
            
        validator = ConversationValidator(self.input_dir, self.report_path)
        report = validator.validate_all()
        
        self.assertEqual(report["stats"]["total_files_checked"], 1)
        self.assertGreater(report["stats"]["total_errors"], 0)
        self.assertEqual(report["stats"]["status"], "FAIL")
        self.assertEqual(len(report["failures"]), 1)
        
        # Verify errors are caught
        errors = report["failures"][0]["errors"]
        has_speaker_error = any("unauthorized_role" in e for e in errors)
        has_text_error = any("text body is empty" in e for e in errors)
        has_time_error = any("preceding" in e for e in errors)
        
        self.assertTrue(has_speaker_error)
        self.assertTrue(has_text_error)
        self.assertTrue(has_time_error)

if __name__ == '__main__':
    unittest.main()
