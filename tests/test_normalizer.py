import os
import unittest
import tempfile
import shutil
import json
from pipeline import GmailNormalizer, WhatsAppNormalizer

class TestNormalizers(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.raw_dir = os.path.join(self.test_dir, "raw")
        self.normalized_dir = os.path.join(self.test_dir, "normalized")
        os.makedirs(self.raw_dir)
        os.makedirs(self.normalized_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_gmail_normalizer_speaker_and_date(self):
        normalizer = GmailNormalizer(
            raw_dir=self.raw_dir, 
            normalized_dir=self.normalized_dir,
            company_domains=['shop.com', 'support.shop.com']
        )
        
        # Test speaker determination
        self.assertEqual(normalizer.normalize_speaker("Alice <alice@gmail.com>"), "user")
        self.assertEqual(normalizer.normalize_speaker("Bob <bob@shop.com>"), "assistant")
        self.assertEqual(normalizer.normalize_speaker("support@support.shop.com"), "assistant")
        
        # Test date parsing RFC 2822 -> ISO 8601 UTC
        self.assertEqual(
            normalizer.normalize_timestamp("Wed, 24 Jun 2026 10:00:00 +0000"),
            "2026-06-24T10:00:00Z"
        )
        self.assertEqual(
            normalizer.normalize_timestamp("Wed, 24 Jun 2026 15:30:00 +0530"),
            "2026-06-24T10:00:00Z"
        )

    def test_gmail_normalizer_conv_id_strip(self):
        normalizer = GmailNormalizer(self.raw_dir, self.normalized_dir)
        conv1 = normalizer.normalize_conversation_id("Re: Product question")
        conv2 = normalizer.normalize_conversation_id("Fwd: Product question")
        conv3 = normalizer.normalize_conversation_id("Product question")
        
        self.assertEqual(conv1, conv2)
        self.assertEqual(conv2, conv3)

    def test_whatsapp_normalizer_formats(self):
        normalizer = WhatsAppNormalizer(
            raw_dir=self.raw_dir,
            normalized_dir=self.normalized_dir,
            agent_names=["Jane Doe"]
        )
        
        # Test speaker
        self.assertEqual(normalizer.normalize_speaker("Jane Doe"), "assistant")
        self.assertEqual(normalizer.normalize_speaker("+15551234"), "user")
        
        # Test dates
        self.assertEqual(
            normalizer.normalize_timestamp("24/06/2026", "10:15:30"),
            "2026-06-24T10:15:30Z"
        )
        self.assertEqual(
            normalizer.normalize_timestamp("24/06/26", "10:15"),
            "2026-06-24T10:15:00Z"
        )
        self.assertEqual(
            normalizer.normalize_timestamp("06/24/2026", "10:15 AM"),
            "2026-06-24T10:15:00Z"
        )

    def test_normalize_file_gmail(self):
        # Create raw gmail mock file
        raw_msg = {
            "source": "gmail",
            "headers": {
                "Message-ID": "<unique-id-999@mail.com>",
                "From": "customer@gmail.com",
                "Subject": "Re: Help",
                "Date": "Wed, 24 Jun 2026 10:00:00 +0000"
            },
            "body": "Is anyone there?"
        }
        raw_filename = "email_test.json"
        with open(os.path.join(self.raw_dir, raw_filename), 'w', encoding='utf-8') as f:
            json.dump(raw_msg, f)
            
        normalizer = GmailNormalizer(self.raw_dir, self.normalized_dir)
        output_paths = normalizer.normalize_all()
        
        self.assertEqual(len(output_paths), 1)
        with open(output_paths[0], 'r', encoding='utf-8') as f:
            norm_msg = json.load(f)
            
        self.assertEqual(norm_msg["speaker"], "user")
        self.assertEqual(norm_msg["timestamp"], "2026-06-24T10:00:00Z")
        self.assertEqual(norm_msg["text"], "Is anyone there?")
        self.assertEqual(norm_msg["metadata"]["subject"], "Re: Help")

if __name__ == '__main__':
    unittest.main()
