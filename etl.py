#!/usr/bin/env python
import os
import sys
import argparse
import yaml
import logging
import json
from datetime import datetime, timezone
from typing import Dict, Any
from storage import RawStorage
from connectors import GmailConnector, WhatsAppConnector
from pipeline import (
    GmailNormalizer, WhatsAppNormalizer, ConversationMerger,
    ThreadBuilder, ConversationValidator, ConversationCleaner,
    PrivacyScrubber, DatasetGenerator, ConversationAnnotator, RAGGenerator
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
    
    # Version subfolder setup
    version = config.get("dataset", {}).get("version")
    base_datasets_dir = os.path.join(project_root, dirs.get("datasets_dir", "datasets"))
    if version:
        datasets_dir = os.path.join(base_datasets_dir, f"v{version}")
    else:
        datasets_dir = base_datasets_dir
        
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
        
        agent_names = config.get("connectors", {}).get("whatsapp", {}).get("agent_names", [])
        agents_json_path = os.path.join(project_root, "agents.json")
        if os.path.exists(agents_json_path):
            try:
                with open(agents_json_path, 'r', encoding='utf-8') as f:
                    agent_names = json.load(f)
            except Exception:
                pass
        
        # Gmail normalizer
        gmail_conf = config.get("connectors", {}).get("gmail", {})
        if gmail_conf.get("enabled", True):
            norm_gmail_dir = os.path.join(norm_dir, "gmail")
            norm_config = config.get("normalizer", {})
            normalizer = GmailNormalizer(
                raw_dir=os.path.join(raw_dir, "gmail"),
                normalized_dir=norm_gmail_dir,
                company_domains=norm_config.get("company_domains", []),
                agent_names=agent_names
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
                agent_names=agent_names
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
            system_prompt=dataset_conf.get("system_prompt", None),
            approved_path=os.path.join(project_root, "approved.json")
        )
        # Configure file outputs dynamically
        jsonl_fn = dataset_conf.get("jsonl_filename", "conversations.jsonl")
        meta_fn = dataset_conf.get("metadata_filename", "metadata.json")
        stats_fn = dataset_conf.get("statistics_filename", "statistics.json")
        
        generator.generate_jsonl(jsonl_fn)
        generator.generate_metadata(meta_fn)
        generator.generate_statistics(stats_fn)
        logger.info(f"Exported dataset JSONL, metadata summary, and statistics report to '{datasets_dir}'.")
        
    # 8. Annotate Step
    if run_all or step == "annotate":
        logger.info("Stage 8: Generating LLM-assisted advanced annotations (intents, sentiment, summaries)...")
        anonymized_dir = os.path.join(norm_dir, "anonymized")
        
        annotator_conf = config.get("annotation", {})
        if annotator_conf.get("enabled", True):
            annotator = ConversationAnnotator(
                input_dir=anonymized_dir,
                output_dir=datasets_dir,
                api_key_env=annotator_conf.get("api_key_env", "GROQ_API_KEY"),
                model=annotator_conf.get("model", "llama-3.1-8b-instant"),
                intent_filename=annotator_conf.get("intent_filename", "intent_labels.jsonl"),
                sentiment_filename=annotator_conf.get("sentiment_filename", "sentiment_labels.jsonl"),
                summary_filename=annotator_conf.get("summary_filename", "summaries.jsonl"),
                approved_path=os.path.join(project_root, "approved.json")
            )
            counts = annotator.process_all()
            logger.info(
                f"Annotation completed: {counts['conversations_processed']} conversations annotated. "
                f"Intents: {counts['intent_labels_written']}, Sentiments: {counts['sentiment_labels_written']}, "
                f"Summaries: {counts['summaries_written']}. LLM Succeeded: {counts['llm_calls_succeeded']}, Fallbacks: {counts['fallbacks_executed']}."
            )
        else:
            logger.info("Advanced annotation stage is disabled in configuration.")
            
    # 9. RAG Step
    if run_all or step == "rag":
        logger.info("Stage 9: Creating semantic dialogue segments and knowledge nuggets for RAG...")
        anonymized_dir = os.path.join(norm_dir, "anonymized")
        
        rag_conf = config.get("rag", {})
        if rag_conf.get("enabled", True):
            generator = RAGGenerator(
                input_dir=anonymized_dir,
                output_dir=datasets_dir,
                chunk_size_turns=rag_conf.get("chunk_size_turns", 4),
                chunk_overlap_turns=rag_conf.get("chunk_overlap_turns", 2),
                rag_filename=rag_conf.get("rag_filename", "rag_chunks.jsonl"),
                approved_path=os.path.join(project_root, "approved.json")
            )
            counts = generator.process_all()
            logger.info(
                f"RAG dataset generated: {counts['conversations_processed']} conversations processed. "
                f"Chunks generated: {counts['total_chunks_written']} (Segments: {counts['segments_generated']}, Facts: {counts['facts_extracted']})."
            )
        else:
            logger.info("RAG generation stage is disabled in configuration.")
        
def load_dotenv(project_root: str):
    """
    Manually load environment variables from a .env file in project_root.
    """
    dotenv_path = os.path.join(project_root, ".env")
    if os.path.exists(dotenv_path):
        with open(dotenv_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, val = line.split('=', 1)
                    key = key.strip()
                    val = val.strip().strip("'").strip('"')
                    os.environ[key] = val

def diff_versions(project_root: str, v1: str, v2: str, output_format: str = "text") -> Dict[str, Any]:
    v1_dir_name = v1 if v1.startswith("v") else f"v{v1}"
    v2_dir_name = v2 if v2.startswith("v") else f"v{v2}"
    
    datasets_base = os.path.join(project_root, "datasets")
    dir1 = os.path.join(datasets_base, v1_dir_name)
    dir2 = os.path.join(datasets_base, v2_dir_name)
    
    if not os.path.exists(dir1):
        raise FileNotFoundError(f"Version directory not found: {dir1}")
    if not os.path.exists(dir2):
        raise FileNotFoundError(f"Version directory not found: {dir2}")
        
    meta1_path = os.path.join(dir1, "metadata.json")
    meta2_path = os.path.join(dir2, "metadata.json")
    stats1_path = os.path.join(dir1, "statistics.json")
    stats2_path = os.path.join(dir2, "statistics.json")
    
    def load_json(path):
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                try:
                    return json.load(f)
                except Exception:
                    pass
        return {}
        
    meta1 = load_json(meta1_path)
    meta2 = load_json(meta2_path)
    stats1 = load_json(stats1_path)
    stats2 = load_json(stats2_path)
    
    diff_report = {
        "version1": v1_dir_name,
        "version2": v2_dir_name,
        "timestamp1": meta1.get("timestamp"),
        "timestamp2": meta2.get("timestamp"),
        "metrics": {
            "total_conversations": {
                "v1": meta1.get("total_conversations", 0),
                "v2": meta2.get("total_conversations", 0),
                "delta": meta2.get("total_conversations", 0) - meta1.get("total_conversations", 0)
            },
            "total_messages": {
                "v1": meta1.get("total_messages", 0),
                "v2": meta2.get("total_messages", 0),
                "delta": meta2.get("total_messages", 0) - meta1.get("total_messages", 0)
            },
            "vocabulary_size": {
                "v1": stats1.get("vocabulary_size", 0),
                "v2": stats2.get("vocabulary_size", 0),
                "delta": stats2.get("vocabulary_size", 0) - stats1.get("vocabulary_size", 0)
            },
            "estimated_total_tokens": {
                "v1": stats1.get("estimated_total_tokens", 0),
                "v2": stats2.get("estimated_total_tokens", 0),
                "delta": stats2.get("estimated_total_tokens", 0) - stats1.get("estimated_total_tokens", 0)
            }
        },
        "anonymization": {
            "emails_scrubbed": {
                "v1": meta1.get("anonymization_summary", {}).get("emails_scrubbed", 0),
                "v2": meta2.get("anonymization_summary", {}).get("emails_scrubbed", 0),
                "delta": meta2.get("anonymization_summary", {}).get("emails_scrubbed", 0) - meta1.get("anonymization_summary", {}).get("emails_scrubbed", 0)
            },
            "phones_scrubbed": {
                "v1": meta1.get("anonymization_summary", {}).get("phones_scrubbed", 0),
                "v2": meta2.get("anonymization_summary", {}).get("phones_scrubbed", 0),
                "delta": meta2.get("anonymization_summary", {}).get("phones_scrubbed", 0) - meta1.get("anonymization_summary", {}).get("phones_scrubbed", 0)
            },
            "passwords_scrubbed": {
                "v1": meta1.get("anonymization_summary", {}).get("passwords_scrubbed", 0),
                "v2": meta2.get("anonymization_summary", {}).get("passwords_scrubbed", 0),
                "delta": meta2.get("anonymization_summary", {}).get("passwords_scrubbed", 0) - meta1.get("anonymization_summary", {}).get("passwords_scrubbed", 0)
            },
            "addresses_scrubbed": {
                "v1": meta1.get("anonymization_summary", {}).get("addresses_scrubbed", 0),
                "v2": meta2.get("anonymization_summary", {}).get("addresses_scrubbed", 0),
                "delta": meta2.get("anonymization_summary", {}).get("addresses_scrubbed", 0) - meta1.get("anonymization_summary", {}).get("addresses_scrubbed", 0)
            }
        }
    }
    
    if output_format == "text":
        lines = []
        lines.append(f"# Dataset Comparison Report: {v1_dir_name} vs {v2_dir_name}")
        lines.append("")
        lines.append(f"| Metric | {v1_dir_name} | {v2_dir_name} | Delta |")
        lines.append("| --- | --- | --- | --- |")
        
        def add_row(name, data):
            d_val = data["delta"]
            delta_str = f"+{d_val}" if d_val > 0 else str(d_val)
            lines.append(f"| {name} | {data['v1']} | {data['v2']} | {delta_str} |")
            
        add_row("Total Conversations", diff_report["metrics"]["total_conversations"])
        add_row("Total Messages", diff_report["metrics"]["total_messages"])
        add_row("Unique Vocabulary Size", diff_report["metrics"]["vocabulary_size"])
        add_row("Estimated Total Tokens", diff_report["metrics"]["estimated_total_tokens"])
        
        lines.append("")
        lines.append("### PII Redaction Audit Comparison")
        lines.append("")
        lines.append(f"| PII Entity Category | {v1_dir_name} | {v2_dir_name} | Delta |")
        lines.append("| --- | --- | --- | --- |")
        add_row("Emails Scrubbed", diff_report["anonymization"]["emails_scrubbed"])
        add_row("Phones Scrubbed", diff_report["anonymization"]["phones_scrubbed"])
        add_row("Passwords/PINs Scrubbed", diff_report["anonymization"]["passwords_scrubbed"])
        add_row("Addresses Scrubbed", diff_report["anonymization"]["addresses_scrubbed"])
        
        print("\n".join(lines))
        
    return diff_report

def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(project_root)
    
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
        choices=["ingest", "normalize", "merge", "reconstruct", "clean", "anonymize", "export", "annotate", "rag"],
        default=None,
        help="Run only a specific stage of the ETL pipeline"
    )
    run_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose DEBUG logging"
    )
    
    # 'diff' command
    diff_parser = subparsers.add_parser("diff", help="Compare two dataset versions")
    diff_parser.add_argument("--v1", required=True, help="First version (e.g. 1.0.0)")
    diff_parser.add_argument("--v2", required=True, help="Second version (e.g. 1.1.0)")
    diff_parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output comparison report format"
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
            
    elif args.command == "diff":
        try:
            diff_report = diff_versions(project_root, args.v1, args.v2, args.format)
            if args.format == "json":
                print(json.dumps(diff_report, indent=2))
        except Exception as e:
            print(f"Error comparing versions: {e}", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    main()
