import os
import unittest
import tempfile
import shutil
import json
from pipeline.dataset_generator import DatasetGenerator

class TestConversationApprovals(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.input_dir = os.path.join(self.test_dir, "anonymized")
        self.output_dir = os.path.join(self.test_dir, "datasets")
        os.makedirs(self.input_dir)
        os.makedirs(self.output_dir)
        
        # Write mock conversation files
        self.conv1 = {
            "conversation_id": "conv_approved_123",
            "messages": [
                {"speaker": "user", "text": "Approved thread"},
                {"speaker": "assistant", "text": "Glad to help"}
            ]
        }
        self.conv2 = {
            "conversation_id": "conv_pending_456",
            "messages": [
                {"speaker": "user", "text": "Pending thread"},
                {"speaker": "assistant", "text": "Need approval"}
            ]
        }
        
        with open(os.path.join(self.input_dir, "conv1.json"), 'w', encoding='utf-8') as f:
            json.dump(self.conv1, f)
        with open(os.path.join(self.input_dir, "conv2.json"), 'w', encoding='utf-8') as f:
            json.dump(self.conv2, f)
            
        self.root_approved_path = "approved.json"
        self.approved_backup = None
        if os.path.exists(self.root_approved_path):
            with open(self.root_approved_path, 'r', encoding='utf-8') as f:
                self.approved_backup = f.read()

    def tearDown(self):
        shutil.rmtree(self.test_dir)
        
        if self.approved_backup is not None:
            with open(self.root_approved_path, 'w', encoding='utf-8') as f:
                f.write(self.approved_backup)
        elif os.path.exists(self.root_approved_path):
            os.remove(self.root_approved_path)

    def test_approvals_filter_applied_correctly(self):
        generator = DatasetGenerator(self.input_dir, self.output_dir, "1.0.0")
        convs = generator.load_conversations()
        self.assertEqual(len(convs), 2)
        
        with open(self.root_approved_path, 'w', encoding='utf-8') as f:
            json.dump(["conv_approved_123"], f)
            
        convs_filtered = generator.load_conversations()
        self.assertEqual(len(convs_filtered), 1)
        self.assertEqual(convs_filtered[0]["conversation_id"], "conv_approved_123")

if __name__ == '__main__':
    unittest.main()
