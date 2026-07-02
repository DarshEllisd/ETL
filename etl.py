#!/usr/bin/env python
import os
import sys
import argparse
import yaml
import logging
import json
from datetime import datetime, timezone
from storage import RawStorage
from connectors import GmailConnector, WhatsAppConnector
from pipeline import (
    GmailNormalizer, WhatsAppNormalizer, ConversationMerger,
    ThreadBuilder, ConversationValidator, ConversationCleaner,
    PrivacyScrubber, DatasetGenerator
)

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ"),
            "name": record.name,
            "level": record.levelname,
            "message": record.getMessage()
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)

def setup_logging(config_log: dict, verbose: bool):
    """
    Setup logging according to configuration.
    """
    level_str = "DEBUG" if verbose else config_log.get("level", "INFO").upper()
    level = getattr(logging, level_str, logging.INFO)
    
    format_style = config_log.get("format_style", "text").lower()
    
    handlers = []
    
    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    if format_style == "json":
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
    handlers.append(console_handler)
    
    # File Handler
    if config_log.get("log_to_file", True):
        log_filename = config_log.get("log_filename", "etl_run.log")
        file_handler = logging.FileHandler(log_filename, encoding='utf-8')
        if format_style == "json":
            file_handler.setFormatter(JSONFormatter())
        else:
            file_handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            ))
        handlers.append(file_handler)
        
    logging.basicConfig(
        level=level,
        handlers=handlers,
        force=True  # Overwrites any existing config
    )

def run_pipeline(config: dict, step: str = None):
    logger = logging.getLogger("etl_pipeline")
    logger.info("Starting ETL Pipeline execution...")
    
    # Directory setup
    project_root = os.path.dirname(os.path.abspath(__file__))
    dirs = config.get("directories", {})
    raw_dir = os.path.join(project_root, dirs.get("raw_dir", "raw"))
    norm_dir = os.path.join(project_root, dirs.get("normalized_dir", "normalized"))
    datasets_dir = os.path.join(project_root, dirs.get("datasets_dir", "datasets"))
    
    # Step flags
    run_all = step is None
    
    # 1. Ingest Step
    if run_all or step == "ingest":
        logger.info("Stage 1: Ingesting raw logs...")
        storage = RawStorage(base_dir=raw_dir)
        
        # Gmail
        gmail_conf = config.get("connectors", {}).get("gmail", {})
        if gmail_conf.get("enabled", True):
            src = os.path.join(project_root, gmail_conf.get("source_dir", "tests/mock_data"))
            if os.path.exists(src):
                connector = GmailConnector(storage)
                count = 0
                for f_name in sorted(os.listdir(src)):
                    if f_name.endswith(".eml"):
                        connector.ingest_eml_file(os.path.join(src, f_name))
                        count += 1
                logger.info(f"Ingested {count} Gmail EML file(s) into raw storage.")
            else:
                logger.warning(f"Gmail source directory not found: {src}")
                
        # WhatsApp
        whatsapp_conf = config.get("connectors", {}).get("whatsapp", {})
        if whatsapp_conf.get("enabled", True):
            src = os.path.join(project_root, whatsapp_conf.get("source_dir", "tests/mock_data"))
            if os.path.exists(src):
                connector = WhatsAppConnector(storage)
                count = 0
                for f_name in sorted(os.listdir(src)):
                    if f_name.endswith(".txt"):
                        connector.ingest_chat_file(os.path.join(src, f_name))
                        count += 1
                logger.info(f"Ingested {count} WhatsApp chat file(s) into raw storage.")
            else:
                logger.warning(f"WhatsApp source directory not found: {src}")
                
    # 2. Normalize Step
    if run_all or step == "normalize":
        logger.info("Stage 2: Normalizing raw data...")
        
        # Gmail normalizer
        gmail_conf = config.get("connectors", {}).get("gmail", {})
        if gmail_conf.get("enabled", True):
            norm_gmail_dir = os.path.join(norm_dir, "gmail")
            norm_config = config.get("normalizer", {})
            normalizer = GmailNormalizer(
                raw_dir=os.path.join(raw_dir, "gmail"),
                normalized_dir=norm_gmail_dir,
                company_domains=norm_config.get("company_domains", [])
            )
            count = len(normalizer.normalize_all())
            logger.info(f"Normalized {count} Gmail files.")
            
        # WhatsApp normalizer
        whatsapp_conf = config.get("connectors", {}).get("whatsapp", {})
        if whatsapp_conf.get("enabled", True):
            norm_wa_dir = os.path.join(norm_dir, "whatsapp")
            normalizer = WhatsAppNormalizer(
                raw_dir=os.path.join(raw_dir, "whatsapp"),
                normalized_dir=norm_wa_dir,
                agent_names=whatsapp_conf.get("agent_names", [])
            )
            count = len(normalizer.normalize_all())
            logger.info(f"Normalized {count} WhatsApp files.")
            
    # 3. Merge Step
    if run_all or step == "merge":
        logger.info("Stage 3: Merging normalized messages...")
        gmail_norm = os.path.join(norm_dir, "gmail")
        whatsapp_norm = os.path.join(norm_dir, "whatsapp")
        unified_dir = os.path.join(norm_dir, "unified")
        
        normalized_dirs = []
        if os.path.exists(gmail_norm):
            normalized_dirs.append(gmail_norm)
        if os.path.exists(whatsapp_norm):
            normalized_dirs.append(whatsapp_norm)
            
        merger = ConversationMerger(
            normalized_dirs=normalized_dirs,
            unified_dir=unified_dir
        )
        count = len(merger.merge_all())
        logger.info(f"Merged unified conversations: {count}.")
        
    # 4. Reconstruct Step
    if run_all or step == "reconstruct":
        logger.info("Stage 4: Reconstructing threads and validating...")
        unified_dir = os.path.join(norm_dir, "unified")
        reconstructed_dir = os.path.join(norm_dir, "reconstructed")
        
        # Thread builder
        tb_conf = config.get("thread_builder", {})
        builder = ThreadBuilder(
            input_dir=unified_dir,
            output_dir=reconstructed_dir,
            gap_threshold_seconds=tb_conf.get("gap_threshold_seconds", 86400)
        )
        count = len(builder.process_all())
        logger.info(f"Reconstructed conversations into {count} sessions.")
        
        # Validation audit
        val_report = os.path.join(project_root, tb_conf.get("validator_report", "validation_report.json"))
        validator = ConversationValidator(
            input_dir=reconstructed_dir,
            report_path=val_report
        )
        report = validator.validate_all()
        logger.info(f"Validation complete. Status: {report['stats']['status']}, Total Errors: {report['stats']['total_errors']}.")
        
    # 5. Clean Step
    if run_all or step == "clean":
        logger.info("Stage 5: Stripping signatures, auto-replies, and duplicates...")
        reconstructed_dir = os.path.join(norm_dir, "reconstructed")
        cleaned_dir = os.path.join(norm_dir, "cleaned")
        
        cleaner_conf = config.get("cleaner", {})
        cleaner = ConversationCleaner(
            input_dir=reconstructed_dir,
            output_dir=cleaned_dir,
            autoreply_keywords=cleaner_conf.get("autoreply_keywords", []),
            low_quality_blacklist=cleaner_conf.get("low_quality_blacklist", []),
            remove_duplicates=cleaner_conf.get("remove_duplicates", True)
        )
        count = len(cleaner.process_all())
        logger.info(f"Sanitized and cleaned {count} conversation records.")
        
    # 6. Anonymize Step
    if run_all or step == "anonymize":
        logger.info("Stage 6: Scrubbing PII (emails, phone numbers, credentials, addresses)...")
        cleaned_dir = os.path.join(norm_dir, "cleaned")
        anonymized_dir = os.path.join(norm_dir, "anonymized")
        
        privacy_conf = config.get("privacy", {})
        report_path = os.path.join(project_root, privacy_conf.get("report_filename", "privacy_report.json"))
        
        scrubber = PrivacyScrubber(
            input_dir=cleaned_dir,
            output_dir=anonymized_dir,
            report_path=report_path
        )
        report = scrubber.process_all()
        logger.info(f"Privacy scrubbing completed. Anonymized files: {report['stats']['total_files_anonymized']}.")
        
    # 7. Export Step
    if run_all or step == "export":
        logger.info("Stage 7: Exporting final instruction datasets and diagnostics statistics...")
        anonymized_dir = os.path.join(norm_dir, "anonymized")
        
        dataset_conf = config.get("dataset", {})
        generator = DatasetGenerator(
            input_dir=anonymized_dir,
            output_dir=datasets_dir,
            version=dataset_conf.get("version", "1.0.0"),
            system_prompt=dataset_conf.get("system_prompt", None)
        )
        # Configure file outputs dynamically
        jsonl_fn = dataset_conf.get("jsonl_filename", "conversations.jsonl")
        meta_fn = dataset_conf.get("metadata_filename", "metadata.json")
        stats_fn = dataset_conf.get("statistics_filename", "statistics.json")
        
        generator.generate_jsonl(jsonl_fn)
        generator.generate_metadata(meta_fn)
        generator.generate_statistics(stats_fn)
        logger.info(f"Exported dataset JSONL, metadata summary, and statistics report to '{datasets_dir}'.")
        
    logger.info("ETL Pipeline execution completed successfully.")

def main():
    parser = argparse.ArgumentParser(description="Unified Conversation ETL Pipeline Runner CLI")
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # 'run' command
    run_parser = subparsers.add_parser("run", help="Run the full pipeline or individual stages")
    run_parser.add_argument(
        "--config",
        default="configs/config.yaml",
        help="Path to YAML configuration file (default: configs/config.yaml)"
    )
    run_parser.add_argument(
        "--step",
        choices=["ingest", "normalize", "merge", "reconstruct", "clean", "anonymize", "export"],
        default=None,
        help="Run only a specific stage of the ETL pipeline"
    )
    run_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose DEBUG logging"
    )
    
    args = parser.parse_args()
    
    if args.command == "run":
        # Load configuration
        if not os.path.exists(args.config):
            print(f"Error: Config file not found at {args.config}", file=sys.stderr)
            sys.exit(1)
            
        with open(args.config, 'r', encoding='utf-8') as f:
            try:
                config = yaml.safe_load(f)
            except Exception as e:
                print(f"Error: Failed to parse YAML config: {e}", file=sys.stderr)
                sys.exit(1)
                
        # Setup logging
        setup_logging(config.get("logging", {}), args.verbose)
        
        try:
            run_pipeline(config, args.step)
        except Exception as e:
            logging.getLogger("etl_pipeline").exception("Pipeline failed with exception:")
            sys.exit(1)

if __name__ == "__main__":
    main()
