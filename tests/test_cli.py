import os
import unittest
import tempfile
import shutil
import yaml
import logging
from etl import setup_logging, run_pipeline

class TestETLCLI(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.test_dir, "config.yaml")
        
        # Define mock configuration pointing to temp folders
        self.mock_config = {
            "directories": {
                "raw_dir": os.path.join(self.test_dir, "raw"),
                "normalized_dir": os.path.join(self.test_dir, "normalized"),
                "datasets_dir": os.path.join(self.test_dir, "datasets")
            },
            "connectors": {
                "gmail": {
                    "enabled": True,
                    "source_dir": os.path.join(self.test_dir, "mock_data")
                },
                "whatsapp": {
                    "enabled": True,
                    "source_dir": os.path.join(self.test_dir, "mock_data"),
                    "agent_names": ["Jane Doe"]
                }
            },
            "normalizer": {
                "company_domains": ["shop.com"]
            },
            "thread_builder": {
                "gap_threshold_seconds": 86400,
                "validator_report": os.path.join(self.test_dir, "validation_report.json")
            },
            "cleaner": {
                "remove_duplicates": True,
                "autoreply_keywords": ["out of office"],
                "low_quality_blacklist": ["ok"],
            },
            "privacy": {
                "report_filename": os.path.join(self.test_dir, "privacy_report.json")
            },
            "dataset": {
                "version": "1.0.0",
                "system_prompt": "You are a helpful customer support agent.",
                "jsonl_filename": "conversations.jsonl",
                "metadata_filename": "metadata.json",
                "statistics_filename": "statistics.json"
            },
            "logging": {
                "level": "DEBUG",
                "format_style": "text",
                "log_to_file": True,
                "log_filename": os.path.join(self.test_dir, "etl_run.log")
            }
        }
        
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(self.mock_config, f)
            
        # Create temp source directory and mock data
        self.mock_src_dir = os.path.join(self.test_dir, "mock_data")
        os.makedirs(self.mock_src_dir)
        
        # sample email
        with open(os.path.join(self.mock_src_dir, "email.eml"), "w", encoding='utf-8') as f:
            f.write(
                "Message-ID: <order-123@shop.com>\n"
                "From: client@gmail.com\n"
                "To: support@shop.com\n"
                "Subject: Order Query\n"
                "\n"
                "Help please.\n"
                "Sent from my iPhone"
            )
            
        # sample whatsapp
        with open(os.path.join(self.mock_src_dir, "chat.txt"), "w", encoding='utf-8') as f:
            f.write(
                "[24/06/2026, 10:15:30] Client: Hello\n"
                "[24/06/2026, 10:16:00] Jane Doe: Hi support here\n"
            )

    def tearDown(self):
        logging.shutdown()
        shutil.rmtree(self.test_dir)

    def test_setup_logging_text(self):
        log_config = self.mock_config["logging"]
        setup_logging(log_config, verbose=False)
        
        logger = logging.getLogger("etl_pipeline")
        self.assertEqual(logger.getEffectiveLevel(), logging.DEBUG)
        
        # Verify etl_run.log file handler is created
        self.assertTrue(os.path.exists(log_config["log_filename"]))

    def test_setup_logging_json(self):
        log_config = self.mock_config["logging"].copy()
        log_config["format_style"] = "json"
        setup_logging(log_config, verbose=False)
        
        logger = logging.getLogger("etl_pipeline")
        self.assertEqual(logger.getEffectiveLevel(), logging.DEBUG)

    def test_run_pipeline_full(self):
        run_pipeline(self.mock_config)
        
        # Verify intermediate and final folders exist
        raw_gmail = os.path.join(self.mock_config["directories"]["raw_dir"], "gmail")
        self.assertTrue(os.path.exists(raw_gmail))
        self.assertEqual(len(os.listdir(raw_gmail)), 1)
        
        norm_gmail = os.path.join(self.mock_config["directories"]["normalized_dir"], "gmail")
        self.assertTrue(os.path.exists(norm_gmail))
        
        export_dir = os.path.join(self.mock_config["directories"]["datasets_dir"], "v1.0.0")
        self.assertTrue(os.path.exists(os.path.join(export_dir, "conversations.jsonl")))
        self.assertTrue(os.path.exists(os.path.join(export_dir, "metadata.json")))
        self.assertTrue(os.path.exists(os.path.join(export_dir, "statistics.json")))

    def test_run_pipeline_single_step(self):
        # run only ingest
        run_pipeline(self.mock_config, step="ingest")
        
        raw_gmail = os.path.join(self.mock_config["directories"]["raw_dir"], "gmail")
        self.assertTrue(os.path.exists(raw_gmail))
        self.assertEqual(len(os.listdir(raw_gmail)), 1)
        
        # normalize folder should NOT exist yet
        norm_gmail = os.path.join(self.mock_config["directories"]["normalized_dir"], "gmail")
        self.assertFalse(os.path.exists(norm_gmail))

if __name__ == '__main__':
    unittest.main()
