import os
import unittest
import tempfile
import shutil
import json
from pipeline import ConversationAnnotator

class TestConversationAnnotator(unittest.TestCase):
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
                    "text": "Hello support, I have a billing issue with invoice #12345. It failed."
                },
                {
                    "message_id": "msg_2",
                    "speaker": "assistant",
                    "text": "Hi, I can help. Can you provide verify password details? I will refund you."
                },
                {
                    "message_id": "msg_3",
                    "speaker": "user",
                    "text": "thanks so much, great!"
                }
            ]
        }
        with open(os.path.join(self.input_dir, "conv_1.json"), 'w', encoding='utf-8') as f:
            json.dump(self.conv, f)

        self.annotator = ConversationAnnotator(
            input_dir=self.input_dir,
            output_dir=self.output_dir
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_fallback_annotate_turns(self):
        res = self.annotator.fallback_annotate(self.conv)
        
        # Verify Intents
        intents = res["intents"]
        self.assertEqual(len(intents), 3)
        self.assertEqual(intents[0]["label"], "billing_inquiry")
        self.assertEqual(intents[1]["label"], "execute_action")
        self.assertEqual(intents[2]["label"], "technical_support")
        
        # Verify Sentiments
        sentiments = res["sentiments"]
        self.assertEqual(len(sentiments), 3)
        self.assertEqual(sentiments[0]["label"], "negative")
        self.assertEqual(sentiments[1]["label"], "neutral")
        self.assertEqual(sentiments[2]["label"], "positive")

        # Verify Summary
        summary = res["summary"]
        self.assertIn("billing", summary["issue"])
        self.assertIn("execute", summary["resolution"])

    def test_process_all_creates_files(self):
        # Run process_all offline (no Groq key, triggers fallback)
        os.environ.pop("GROQ_API_KEY", None)
        counts = self.annotator.process_all()
        
        self.assertEqual(counts["conversations_processed"], 1)
        self.assertEqual(counts["fallbacks_executed"], 1)
        self.assertEqual(counts["llm_calls_succeeded"], 0)

        # Check files
        intent_file = os.path.join(self.output_dir, "intent_labels.jsonl")
        sentiment_file = os.path.join(self.output_dir, "sentiment_labels.jsonl")
        summary_file = os.path.join(self.output_dir, "summaries.jsonl")

        self.assertTrue(os.path.exists(intent_file))
        self.assertTrue(os.path.exists(sentiment_file))
        self.assertTrue(os.path.exists(summary_file))

        # Check intent labels content
        with open(intent_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 3)
        data = json.loads(lines[0])
        self.assertEqual(data["conversation_id"], "test_conv_1")
        self.assertEqual(data["message_id"], "msg_1")
        self.assertEqual(data["label"], "billing_inquiry")

if __name__ == '__main__':
    unittest.main()
