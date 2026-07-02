import os
import unittest
import tempfile
import shutil
import json
from pipeline import DatasetGenerator

class TestDatasetGenerator(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.input_dir = os.path.join(self.test_dir, "input")
        self.output_dir = os.path.join(self.test_dir, "output")
        os.makedirs(self.input_dir)
        os.makedirs(self.output_dir)
        
        # Write some sample anonymized conversations
        self.conv1 = {
            "conversation_id": "conv_1",
            "source": "gmail",
            "messages": [
                {
                    "message_id": "msg_1",
                    "speaker": "user",
                    "text": "Hello support, I need help with code."
                },
                {
                    "message_id": "msg_2",
                    "speaker": "assistant",
                    "text": "Sure, let me check."
                }
            ],
            "metadata": {
                "pii_emails_scrubbed": 1,
                "pii_phones_scrubbed": 0,
                "pii_passwords_scrubbed": 0,
                "pii_addresses_scrubbed": 2,
                "pii_names_scrubbed": 1
            }
        }
        
        self.conv2 = {
            "conversation_id": "conv_2",
            "source": "whatsapp",
            "messages": [
                {
                    "message_id": "msg_3",
                    "speaker": "user",
                    "text": "Is it working?"
                }
            ],
            "metadata": {
                "pii_emails_scrubbed": 0,
                "pii_phones_scrubbed": 1,
                "pii_passwords_scrubbed": 0,
                "pii_addresses_scrubbed": 0,
                "pii_names_scrubbed": 0
            }
        }
        
        with open(os.path.join(self.input_dir, "conv_1.json"), 'w', encoding='utf-8') as f:
            json.dump(self.conv1, f)
        with open(os.path.join(self.input_dir, "conv_2.json"), 'w', encoding='utf-8') as f:
            json.dump(self.conv2, f)
            
        self.generator = DatasetGenerator(
            input_dir=self.input_dir,
            output_dir=self.output_dir,
            version="1.2.3",
            system_prompt="Test System Prompt"
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_generate_jsonl(self):
        output_path = self.generator.generate_jsonl()
        self.assertTrue(os.path.exists(output_path))
        
        with open(output_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        self.assertEqual(len(lines), 2)
        
        # Verify first conversation format
        data1 = json.loads(lines[0])
        msgs1 = data1["messages"]
        self.assertEqual(len(msgs1), 3) # System prompt + 2 messages
        self.assertEqual(msgs1[0]["role"], "system")
        self.assertEqual(msgs1[0]["content"], "Test System Prompt")
        self.assertEqual(msgs1[1]["role"], "user")
        self.assertEqual(msgs1[1]["content"], "Hello support, I need help with code.")
        self.assertEqual(msgs1[2]["role"], "assistant")
        self.assertEqual(msgs1[2]["content"], "Sure, let me check.")

    def test_generate_metadata(self):
        output_path = self.generator.generate_metadata()
        self.assertTrue(os.path.exists(output_path))
        
        with open(output_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        self.assertEqual(data["version"], "1.2.3")
        self.assertEqual(data["total_conversations"], 2)
        self.assertEqual(data["total_messages"], 3)
        self.assertEqual(data["source_distribution"]["gmail"], 1)
        self.assertEqual(data["source_distribution"]["whatsapp"], 1)
        
        # PII counts
        self.assertEqual(data["anonymization_summary"]["emails_scrubbed"], 1)
        self.assertEqual(data["anonymization_summary"]["phones_scrubbed"], 1)
        self.assertEqual(data["anonymization_summary"]["addresses_scrubbed"], 2)
        self.assertEqual(data["anonymization_summary"]["names_scrubbed"], 1)

    def test_generate_statistics(self):
        output_path = self.generator.generate_statistics()
        self.assertTrue(os.path.exists(output_path))
        
        with open(output_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        self.assertEqual(data["conversation_count"], 2)
        self.assertEqual(data["message_count"], 3)
        
        # Conversation length stats
        self.assertEqual(data["conversation_length_stats"]["min"], 1)
        self.assertEqual(data["conversation_length_stats"]["max"], 2)
        self.assertEqual(data["conversation_length_stats"]["average"], 1.5)
        
        # Ratios
        self.assertEqual(data["speaker_ratios"]["user"], round(2/3, 4))
        self.assertEqual(data["speaker_ratios"]["assistant"], round(1/3, 4))
        
        # Vocab: "hello", "support", "i", "need", "help", "with", "code", "sure", "let", "me", "check", "is", "it", "working"
        # 14 unique words
        self.assertEqual(data["vocabulary_size"], 14)
        
        # Estimated tokens: 14 words total * 1.3 = 18.2 -> 18
        self.assertEqual(data["estimated_total_tokens"], 18)

    def test_run_all(self):
        paths = self.generator.run_all()
        self.assertTrue(os.path.exists(paths["jsonl"]))
        self.assertTrue(os.path.exists(paths["metadata"]))
        self.assertTrue(os.path.exists(paths["statistics"]))

if __name__ == '__main__':
    unittest.main()
