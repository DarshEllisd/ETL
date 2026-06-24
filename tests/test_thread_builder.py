import os
import unittest
import tempfile
import shutil
import json
from pipeline import ThreadBuilder

class TestThreadBuilder(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.input_dir = os.path.join(self.test_dir, "input")
        self.output_dir = os.path.join(self.test_dir, "output")
        os.makedirs(self.input_dir)
        os.makedirs(self.output_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_sessionize_under_threshold(self):
        # Two messages separated by 1 hour (threshold is 24 hours / 86400 seconds)
        conv = {
            "conversation_id": "conv_1",
            "source": "whatsapp",
            "messages": [
                {
                    "message_id": "msg_1",
                    "conversation_id": "conv_1",
                    "timestamp": "2026-06-24T10:00:00Z",
                    "speaker": "user",
                    "text": "Hello"
                },
                {
                    "message_id": "msg_2",
                    "conversation_id": "conv_1",
                    "timestamp": "2026-06-24T11:00:00Z",
                    "speaker": "assistant",
                    "text": "Hi"
                }
            ]
        }
        
        file_path = os.path.join(self.input_dir, "conv_1.json")
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(conv, f)
            
        builder = ThreadBuilder(
            input_dir=self.input_dir,
            output_dir=self.output_dir,
            gap_threshold_seconds=86400
        )
        
        output_paths = builder.process_all()
        # Should not split, so exactly 1 session
        self.assertEqual(len(output_paths), 1)
        
        with open(output_paths[0], 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        self.assertEqual(data["conversation_id"], "conv_1_session_0")
        self.assertEqual(data["metadata"]["total_sessions"], 1)
        self.assertEqual(len(data["messages"]), 2)
        # Verify internal conversation_id has been updated
        self.assertEqual(data["messages"][0]["conversation_id"], "conv_1_session_0")

    def test_sessionize_over_threshold(self):
        # Two messages separated by 25 hours (threshold is 24 hours / 86400 seconds)
        conv = {
            "conversation_id": "conv_2",
            "source": "whatsapp",
            "messages": [
                {
                    "message_id": "msg_1",
                    "conversation_id": "conv_2",
                    "timestamp": "2026-06-24T10:00:00Z",
                    "speaker": "user",
                    "text": "First query"
                },
                {
                    "message_id": "msg_2",
                    "conversation_id": "conv_2",
                    "timestamp": "2026-06-25T11:00:00Z",
                    "speaker": "assistant",
                    "text": "Reply after a day"
                }
            ]
        }
        
        file_path = os.path.join(self.input_dir, "conv_2.json")
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(conv, f)
            
        builder = ThreadBuilder(
            input_dir=self.input_dir,
            output_dir=self.output_dir,
            gap_threshold_seconds=86400
        )
        
        output_paths = builder.process_all()
        # Must split into 2 sessions
        self.assertEqual(len(output_paths), 2)
        
        # Sort paths to be sure of order
        output_paths.sort()
        
        # Check first session
        with open(output_paths[0], 'r', encoding='utf-8') as f:
            data_1 = json.load(f)
        self.assertEqual(data_1["conversation_id"], "conv_2_session_0")
        self.assertEqual(len(data_1["messages"]), 1)
        self.assertEqual(data_1["messages"][0]["message_id"], "msg_1")
        self.assertEqual(data_1["messages"][0]["conversation_id"], "conv_2_session_0")
        
        # Check second session
        with open(output_paths[1], 'r', encoding='utf-8') as f:
            data_2 = json.load(f)
        self.assertEqual(data_2["conversation_id"], "conv_2_session_1")
        self.assertEqual(len(data_2["messages"]), 1)
        self.assertEqual(data_2["messages"][0]["message_id"], "msg_2")
        self.assertEqual(data_2["messages"][0]["conversation_id"], "conv_2_session_1")

if __name__ == '__main__':
    unittest.main()
