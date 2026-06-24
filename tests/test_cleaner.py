import os
import unittest
import tempfile
import shutil
import json
from pipeline import ConversationCleaner

class TestConversationCleaner(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.input_dir = os.path.join(self.test_dir, "input")
        self.output_dir = os.path.join(self.test_dir, "output")
        os.makedirs(self.input_dir)
        os.makedirs(self.output_dir)
        
        self.cleaner = ConversationCleaner(self.input_dir, self.output_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_strip_signature_sent_from_iphone(self):
        text = "Hello Bob,\n\nI need help with my tracking.\n\nSent from my iPhone"
        cleaned = self.cleaner.clean_signatures(text)
        self.assertEqual(cleaned, "Hello Bob,\n\nI need help with my tracking.")

    def test_strip_signature_best_regards(self):
        text = "Hi Jane,\nPlease process the order.\n\nBest regards,\nJohn"
        cleaned = self.cleaner.clean_signatures(text)
        self.assertEqual(cleaned, "Hi Jane,\nPlease process the order.")

    def test_is_autoreply(self):
        self.assertTrue(self.cleaner.is_autoreply("I am out of office until Monday."))
        self.assertTrue(self.cleaner.is_autoreply("This is an Automatic Reply regarding your email."))
        self.assertFalse(self.cleaner.is_autoreply("Hi, can you help me?"))

    def test_is_low_quality(self):
        self.assertTrue(self.cleaner.is_low_quality("ok"))
        self.assertTrue(self.cleaner.is_low_quality("thanks!"))
        self.assertTrue(self.cleaner.is_low_quality(" 👍 "))
        self.assertFalse(self.cleaner.is_low_quality("Okay, I will send the code now."))

    def test_clean_conversation_full(self):
        conv = {
            "conversation_id": "conv_clean_1",
            "source": "gmail",
            "messages": [
                {
                    "message_id": "msg_1",
                    "timestamp": "2026-06-24T10:00:00Z",
                    "speaker": "user",
                    "text": "Hi Support,\nCan you assist?\n\nThanks,\nAlice"
                },
                {
                    "message_id": "msg_2",
                    "timestamp": "2026-06-24T10:01:00Z",
                    "speaker": "user",
                    "text": "Hi Support,\nCan you assist?\n\nThanks,\nAlice"  # Duplicate
                },
                {
                    "message_id": "msg_3",
                    "timestamp": "2026-06-24T10:02:00Z",
                    "speaker": "assistant",
                    "text": "Hello! I am out of office right now."  # Autoreply
                },
                {
                    "message_id": "msg_4",
                    "timestamp": "2026-06-24T10:03:00Z",
                    "speaker": "assistant",
                    "text": "Sorry for the delay. Yes, how can I help?\n\nBest regards,\nSupport Agent"
                },
                {
                    "message_id": "msg_5",
                    "timestamp": "2026-06-24T10:04:00Z",
                    "speaker": "user",
                    "text": "ok"  # Low quality
                }
            ]
        }
        
        file_path = os.path.join(self.input_dir, "conv_1.json")
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(conv, f)
            
        output_paths = self.cleaner.process_all()
        self.assertEqual(len(output_paths), 1)
        
        with open(output_paths[0], 'r', encoding='utf-8') as f:
            cleaned_conv = json.load(f)
            
        msgs = cleaned_conv["messages"]
        self.assertEqual(len(msgs), 2)  # msg_1, msg_4 remain
        
        # msg_1 check
        self.assertEqual(msgs[0]["message_id"], "msg_1")
        self.assertEqual(msgs[0]["text"], "Hi Support,\nCan you assist?")
        
        # msg_4 check
        self.assertEqual(msgs[1]["message_id"], "msg_4")
        self.assertEqual(msgs[1]["text"], "Sorry for the delay. Yes, how can I help?")

if __name__ == '__main__':
    unittest.main()
