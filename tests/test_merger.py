import os
import unittest
import tempfile
import shutil
import json
from pipeline import ConversationMerger

class TestConversationMerger(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.dir1 = os.path.join(self.test_dir, "gmail")
        self.dir2 = os.path.join(self.test_dir, "whatsapp")
        self.unified_dir = os.path.join(self.test_dir, "unified")
        os.makedirs(self.dir1)
        os.makedirs(self.dir2)
        os.makedirs(self.unified_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_merge_and_sort_conversations(self):
        # Create normalized gmail messages for thread 1
        msg1 = {
            "message_id": "gmail_msg_1",
            "conversation_id": "thread_1",
            "timestamp": "2026-06-24T10:00:00Z",
            "speaker": "user",
            "text": "First message"
        }
        msg3 = {
            "message_id": "gmail_msg_3",
            "conversation_id": "thread_1",
            "timestamp": "2026-06-24T10:10:00Z",
            "speaker": "user",
            "text": "Third message"
        }
        
        # Create normalized message out of order
        msg2 = {
            "message_id": "gmail_msg_2",
            "conversation_id": "thread_1",
            "timestamp": "2026-06-24T10:05:00Z",
            "speaker": "assistant",
            "text": "Second message"
        }
        
        # Write to folders
        with open(os.path.join(self.dir1, "msg1.json"), 'w', encoding='utf-8') as f:
            json.dump(msg1, f)
        with open(os.path.join(self.dir1, "msg3.json"), 'w', encoding='utf-8') as f:
            json.dump(msg3, f)
        with open(os.path.join(self.dir1, "msg2.json"), 'w', encoding='utf-8') as f:
            json.dump(msg2, f)
            
        merger = ConversationMerger(
            normalized_dirs=[self.dir1, self.dir2],
            unified_dir=self.unified_dir
        )
        
        output_paths = merger.merge_all()
        self.assertEqual(len(output_paths), 1)
        
        with open(output_paths[0], 'r', encoding='utf-8') as f:
            unified = json.load(f)
            
        self.assertEqual(unified["conversation_id"], "thread_1")
        self.assertEqual(unified["source"], "gmail")
        self.assertEqual(unified["start_timestamp"], "2026-06-24T10:00:00Z")
        self.assertEqual(unified["end_timestamp"], "2026-06-24T10:10:00Z")
        
        # Check chronological ordering
        msgs = unified["messages"]
        self.assertEqual(len(msgs), 3)
        self.assertEqual(msgs[0]["message_id"], "gmail_msg_1")
        self.assertEqual(msgs[1]["message_id"], "gmail_msg_2")
        self.assertEqual(msgs[2]["message_id"], "gmail_msg_3")

if __name__ == '__main__':
    unittest.main()
