import os
import unittest
import tempfile
import shutil
import json
from pipeline import RAGGenerator

class TestRAGGenerator(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.input_dir = os.path.join(self.test_dir, "input")
        self.output_dir = os.path.join(self.test_dir, "output")
        os.makedirs(self.input_dir)
        os.makedirs(self.output_dir)

        # sample conversation
        self.conv = {
            "conversation_id": "test_conv_1",
            "source": "gmail",
            "messages": [
                {
                    "message_id": "msg_1",
                    "speaker": "user",
                    "text": "Hello support, I have a billing issue with invoice #12345."
                },
                {
                    "message_id": "msg_2",
                    "speaker": "assistant",
                    "text": "Hi, I can help. Can you provide verify password details '[PASSWORD]'? I will update your shipping to '[ADDRESS]'."
                },
                {
                    "message_id": "msg_3",
                    "speaker": "user",
                    "text": "Sure, here's my details: phone [PHONE], email [EMAIL]."
                },
                {
                    "message_id": "msg_4",
                    "speaker": "assistant",
                    "text": "Perfect, done."
                }
            ]
        }
        with open(os.path.join(self.input_dir, "conv_1.json"), 'w', encoding='utf-8') as f:
            json.dump(self.conv, f)

        # 3 turn size, 1 turn overlap
        self.generator = RAGGenerator(
            input_dir=self.input_dir,
            output_dir=self.output_dir,
            chunk_size_turns=3,
            chunk_overlap_turns=1
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_chunk_conversation(self):
        chunks = self.generator.chunk_conversation(self.conv)
        # Size=3, Overlap=1, Total Messages=4
        # Window 1: msg_1, msg_2, msg_3 (range [0, 2])
        # Window 2: msg_3, msg_4 (range [2, 3])
        self.assertEqual(len(chunks), 2)
        
        self.assertEqual(chunks[0]["chunk_id"], "test_conv_1_chunk_0")
        self.assertEqual(chunks[0]["metadata"]["message_range"], [0, 2])
        self.assertIn("User: Hello support", chunks[0]["content"])
        self.assertIn("Assistant: Hi, I can help", chunks[0]["content"])
        
        self.assertEqual(chunks[1]["chunk_id"], "test_conv_1_chunk_1")
        self.assertEqual(chunks[1]["metadata"]["message_range"], [2, 3])
        self.assertIn("User: Sure, here's my details", chunks[1]["content"])

    def test_extract_knowledge_nuggets(self):
        facts = self.generator.extract_knowledge_nuggets(self.conv)
        self.assertEqual(len(facts), 5)
        
        ref_types = [f["metadata"]["reference_type"] for f in facts]
        self.assertIn("order_id", ref_types)
        self.assertIn("credentials", ref_types)
        self.assertIn("address", ref_types)
        self.assertIn("phone", ref_types)
        self.assertIn("email", ref_types)

        # Check content match
        order_fact = [f for f in facts if f["metadata"]["reference_type"] == "order_id"][0]
        self.assertIn("#12345", order_fact["content"])

    def test_process_all_writes_rag_file(self):
        counts = self.generator.process_all()
        
        self.assertEqual(counts["conversations_processed"], 1)
        self.assertEqual(counts["segments_generated"], 2)
        self.assertEqual(counts["facts_extracted"], 5)
        self.assertEqual(counts["total_chunks_written"], 7)

        rag_file = os.path.join(self.output_dir, "rag_chunks.jsonl")
        self.assertTrue(os.path.exists(rag_file))

        with open(rag_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 7)
        
        first_chunk = json.loads(lines[0])
        self.assertEqual(first_chunk["type"], "conversation_segment")
        self.assertEqual(first_chunk["chunk_id"], "test_conv_1_chunk_0")

if __name__ == '__main__':
    unittest.main()
