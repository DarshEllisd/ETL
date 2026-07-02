import os
import unittest
import tempfile
import shutil
import json
from etl import diff_versions

class TestDatasetVersioning(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.datasets_base = os.path.join(self.test_dir, "datasets")
        os.makedirs(self.datasets_base)
        
        # Create mock dataset folders
        self.v1_dir = os.path.join(self.datasets_base, "v1.0.0")
        self.v2_dir = os.path.join(self.datasets_base, "v1.1.0")
        os.makedirs(self.v1_dir)
        os.makedirs(self.v2_dir)
        
        # v1 metadata & stats
        v1_meta = {
            "version": "1.0.0",
            "timestamp": "2026-07-02T12:00:00Z",
            "total_conversations": 5,
            "total_messages": 10,
            "anonymization_summary": {
                "emails_scrubbed": 2,
                "phones_scrubbed": 3,
                "passwords_scrubbed": 1,
                "addresses_scrubbed": 1
            }
        }
        v1_stats = {
            "vocabulary_size": 100,
            "estimated_total_tokens": 200
        }
        with open(os.path.join(self.v1_dir, "metadata.json"), 'w', encoding='utf-8') as f:
            json.dump(v1_meta, f)
        with open(os.path.join(self.v1_dir, "statistics.json"), 'w', encoding='utf-8') as f:
            json.dump(v1_stats, f)
            
        # v2 metadata & stats
        v2_meta = {
            "version": "1.1.0",
            "timestamp": "2026-07-02T13:00:00Z",
            "total_conversations": 7,
            "total_messages": 15,
            "anonymization_summary": {
                "emails_scrubbed": 4,
                "phones_scrubbed": 5,
                "passwords_scrubbed": 1,
                "addresses_scrubbed": 3
            }
        }
        v2_stats = {
            "vocabulary_size": 120,
            "estimated_total_tokens": 300
        }
        with open(os.path.join(self.v2_dir, "metadata.json"), 'w', encoding='utf-8') as f:
            json.dump(v2_meta, f)
        with open(os.path.join(self.v2_dir, "statistics.json"), 'w', encoding='utf-8') as f:
            json.dump(v2_stats, f)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_diff_versions_report_calculations(self):
        report = diff_versions(self.test_dir, "1.0.0", "1.1.0", "json")
        
        self.assertEqual(report["version1"], "v1.0.0")
        self.assertEqual(report["version2"], "v1.1.0")
        
        # Check metrics deltas
        self.assertEqual(report["metrics"]["total_conversations"]["delta"], 2)
        self.assertEqual(report["metrics"]["total_messages"]["delta"], 5)
        self.assertEqual(report["metrics"]["vocabulary_size"]["delta"], 20)
        self.assertEqual(report["metrics"]["estimated_total_tokens"]["delta"], 100)
        
        # Check PII deltas
        self.assertEqual(report["anonymization"]["emails_scrubbed"]["delta"], 2)
        self.assertEqual(report["anonymization"]["phones_scrubbed"]["delta"], 2)
        self.assertEqual(report["anonymization"]["passwords_scrubbed"]["delta"], 0)
        self.assertEqual(report["anonymization"]["addresses_scrubbed"]["delta"], 2)

    def test_diff_versions_missing_error(self):
        with self.assertRaises(FileNotFoundError):
            diff_versions(self.test_dir, "1.0.0", "1.2.0", "json")

if __name__ == '__main__':
    unittest.main()
