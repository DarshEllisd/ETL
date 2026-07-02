import os
import json
from storage import RawStorage
from connectors import GmailConnector, WhatsAppConnector
from pipeline import (
    GmailNormalizer, WhatsAppNormalizer, ConversationMerger, 
    ThreadBuilder, ConversationCleaner, PrivacyScrubber,
    DatasetGenerator
)

def main():
    print("--- ETL Dataset Generation & Diagnostics Manual Verification ---")
    
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Directories
    raw_dir = os.path.join(project_root, 'raw')
    norm_dir = os.path.join(project_root, 'normalized')
    datasets_dir = os.path.join(project_root, 'datasets')
    
    # 1. Setup raw storage & mock connectors
    storage = RawStorage(base_dir=raw_dir)
    gmail_connector = GmailConnector(storage)
    whatsapp_connector = WhatsAppConnector(storage)
    
    # Ingest mock files from tests/mock_data
    print("\nIngesting mock log files from tests/mock_data...")
    mock_data_dir = os.path.join(project_root, 'tests', 'mock_data')
    
    if not os.path.exists(mock_data_dir):
        print(f"Error: Mock data directory not found at {mock_data_dir}")
        return
        
    for filename in sorted(os.listdir(mock_data_dir)):
        filepath = os.path.join(mock_data_dir, filename)
        if filename.endswith('.eml'):
            gmail_connector.ingest_eml_file(filepath)
        elif filename.endswith('.txt'):
            whatsapp_connector.ingest_chat_file(filepath)
    
    # Normalize
    gmail_norm = os.path.join(norm_dir, 'gmail')
    gmail_normalizer = GmailNormalizer(raw_dir=os.path.join(raw_dir, 'gmail'), normalized_dir=gmail_norm)
    gmail_normalizer.normalize_all()
    
    whatsapp_norm = os.path.join(norm_dir, 'whatsapp')
    whatsapp_normalizer = WhatsAppNormalizer(
        raw_dir=os.path.join(raw_dir, 'whatsapp'),
        normalized_dir=whatsapp_norm,
        agent_names=['Jane Doe', 'Agent Bob']
    )
    whatsapp_normalizer.normalize_all()
    
    # Merge
    unified_dir = os.path.join(norm_dir, 'unified')
    merger = ConversationMerger(normalized_dirs=[gmail_norm, whatsapp_norm], unified_dir=unified_dir)
    merger.merge_all()
    
    # Sessionize (Thread Builder)
    reconstructed_dir = os.path.join(norm_dir, 'reconstructed')
    builder = ThreadBuilder(input_dir=unified_dir, output_dir=reconstructed_dir, gap_threshold_seconds=86400)
    builder.process_all()
    
    # Clean
    cleaned_dir = os.path.join(norm_dir, 'cleaned')
    cleaner = ConversationCleaner(input_dir=reconstructed_dir, output_dir=cleaned_dir)
    cleaner.process_all()
    
    # Scrub Privacy PII
    anonymized_dir = os.path.join(norm_dir, 'anonymized')
    report_path = os.path.join(project_root, 'privacy_report.json')
    scrubber = PrivacyScrubber(input_dir=cleaned_dir, output_dir=anonymized_dir, report_path=report_path)
    scrubber.process_all()
    
    # 2. Run Dataset Generator
    print("\nRunning DatasetGenerator...")
    generator = DatasetGenerator(
        input_dir=anonymized_dir,
        output_dir=datasets_dir,
        version="1.0.0",
        system_prompt="You are a helpful customer support agent."
    )
    generator.run_all()
    print("Dataset generation completed.")
    
    # 3. Print Results
    print("\n--- generated datasets/conversations.jsonl ---")
    jsonl_file = os.path.join(datasets_dir, "conversations.jsonl")
    if os.path.exists(jsonl_file):
        with open(jsonl_file, 'r', encoding='utf-8') as f:
            for line in f:
                print(line.strip())
                
    print("\n--- generated datasets/metadata.json ---")
    meta_file = os.path.join(datasets_dir, "metadata.json")
    if os.path.exists(meta_file):
        with open(meta_file, 'r', encoding='utf-8') as f:
            print(json.dumps(json.load(f), indent=2, ensure_ascii=False))
            
    print("\n--- generated datasets/statistics.json ---")
    stats_file = os.path.join(datasets_dir, "statistics.json")
    if os.path.exists(stats_file):
        with open(stats_file, 'r', encoding='utf-8') as f:
            print(json.dumps(json.load(f), indent=2, ensure_ascii=False))
            
    print("\nETL Dataset Generation & Diagnostics Verification completed successfully!")

if __name__ == '__main__':
    main()
