import os
import json
from storage import RawStorage
from connectors import GmailConnector, WhatsAppConnector
from pipeline import (
    GmailNormalizer, WhatsAppNormalizer, ConversationMerger, 
    ThreadBuilder, ConversationCleaner, PrivacyScrubber
)

def main():
    print("--- ETL Cleaning & Privacy Manual Verification ---")
    
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Directories
    raw_dir = os.path.join(project_root, 'raw')
    norm_dir = os.path.join(project_root, 'normalized')
    
    # 1. Setup mock directories & inputs
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
    
    # Normalize & Merge
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
    
    unified_dir = os.path.join(norm_dir, 'unified')
    merger = ConversationMerger(normalized_dirs=[gmail_norm, whatsapp_norm], unified_dir=unified_dir)
    merger.merge_all()
    
    # Reconstruct/Sessionize
    reconstructed_dir = os.path.join(norm_dir, 'reconstructed')
    builder = ThreadBuilder(input_dir=unified_dir, output_dir=reconstructed_dir, gap_threshold_seconds=86400)
    builder.process_all()
    
    # 2. Run Cleaning
    print("\nRunning ConversationCleaner...")
    cleaned_dir = os.path.join(norm_dir, 'cleaned')
    cleaner = ConversationCleaner(input_dir=reconstructed_dir, output_dir=cleaned_dir)
    cleaner.process_all()
    print("Cleaning completed.")
    
    # 3. Run Privacy Scrubber
    print("\nRunning PrivacyScrubber...")
    anonymized_dir = os.path.join(norm_dir, 'anonymized')
    report_path = os.path.join(project_root, 'privacy_report.json')
    scrubber = PrivacyScrubber(
        input_dir=cleaned_dir,
        output_dir=anonymized_dir,
        report_path=report_path
    )
    report = scrubber.process_all()
    print("Privacy scrubbing completed.")
    
    # 4. Display Outputs
    print("\nAnonymized output files:")
    for f_name in os.listdir(anonymized_dir):
        if f_name.endswith('.json'):
            print(f"\n--- File: {f_name} ---")
            with open(os.path.join(anonymized_dir, f_name), 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(json.dumps(data, indent=2, ensure_ascii=False))
            
    print("\n--- privacy_report.json ---")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    
    print("\nCleaning & Privacy verification completed successfully!")

if __name__ == '__main__':
    main()
