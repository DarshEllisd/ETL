import os
import unittest
import tempfile
import shutil
import json
from pipeline.dataset_generator import DatasetGenerator
from pipeline.annotator import ConversationAnnotator
from pipeline.rag_generator import RAGGenerator

class TestConversationExclusions(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.input_dir = os.path.join(self.test_dir, "anonymized")
        self.output_dir = os.path.join(self.test_dir, "datasets")
        os.makedirs(self.input_dir)
        os.makedirs(self.output_dir)
        
        # Write mock conversation files
        self.conv1 = {
            "conversation_id": "conv_keep_123",
            "messages": [
                {"speaker": "user", "text": "Hello support"},
                {"speaker": "assistant", "text": "Hello customer"}
            ]
        }
        self.conv2 = {
            "conversation_id": "conv_exclude_456",
            "messages": [
                {"speaker": "user", "text": "This contains secrets password123"},
                {"speaker": "assistant", "text": "Please don't share passwords"}
            ]
        }
        
        with open(os.path.join(self.input_dir, "conv1.json"), 'w', encoding='utf-8') as f:
            json.dump(self.conv1, f)
        with open(os.path.join(self.input_dir, "conv2.json"), 'w', encoding='utf-8') as f:
            json.dump(self.conv2, f)
            
        self.root_exclusions_path = "exclusions.json"
        self.exclusions_backup = None
        if os.path.exists(self.root_exclusions_path):
            with open(self.root_exclusions_path, 'r', encoding='utf-8') as f:
                self.exclusions_backup = f.read()

    def tearDown(self):
        shutil.rmtree(self.test_dir)
        
        if self.exclusions_backup is not None:
            with open(self.root_exclusions_path, 'w', encoding='utf-8') as f:
                f.write(self.exclusions_backup)
        elif os.path.exists(self.root_exclusions_path):
            os.remove(self.root_exclusions_path)

    def test_exclusions_applied_successfully(self):
        # 1. Without exclusions, load_conversations loads both
        generator = DatasetGenerator(self.input_dir, self.output_dir, "1.0.0")
        convs = generator.load_conversations()
        self.assertEqual(len(convs), 2)
        
        # 2. Write exclusion list
        with open(self.root_exclusions_path, 'w', encoding='utf-8') as f:
            json.dump(["conv_exclude_456"], f)
            
        # Reload generator conversations
        convs_filtered = generator.load_conversations()
        self.assertEqual(len(convs_filtered), 1)
        self.assertEqual(convs_filtered[0]["conversation_id"], "conv_keep_123")
        
        # 3. Check annotator load_conversations
        annotator = ConversationAnnotator(self.input_dir, self.output_dir)
        annotator_convs = annotator.load_conversations()
        self.assertEqual(len(annotator_convs), 1)
        self.assertEqual(annotator_convs[0]["conversation_id"], "conv_keep_123")
        
        # 4. Check RAG generator load_conversations
        rag = RAGGenerator(self.input_dir, self.output_dir)
        rag_convs = rag.load_conversations()
        self.assertEqual(len(rag_convs), 1)
        self.assertEqual(rag_convs[0]["conversation_id"], "conv_keep_123")

if __name__ == '__main__':
    unittest.main()
