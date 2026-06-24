import os
import json
from storage import RawStorage
from connectors import GmailConnector, WhatsAppConnector
from pipeline import GmailNormalizer, WhatsAppNormalizer, ConversationMerger, ThreadBuilder, ConversationValidator

def main():
    print("--- ETL Reconstruction & Validation Manual Verification ---")
    
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Directories
    raw_dir = os.path.join(project_root, 'raw')
    norm_dir = os.path.join(project_root, 'normalized')
    unified_dir = os.path.join(norm_dir, 'unified')
    reconstructed_dir = os.path.join(norm_dir, 'reconstructed')
    report_path = os.path.join(project_root, 'validation_report.json')
    
    # 1. Setup mock data
    storage = RawStorage(base_dir=raw_dir)
    gmail_connector = GmailConnector(storage)
    whatsapp_connector = WhatsAppConnector(storage)
    
    mock_data_dir = os.path.join(project_root, 'tests', 'mock_data')
    mock_eml = os.path.join(mock_data_dir, 'sample_customer_email.eml')
    mock_wa = os.path.join(mock_data_dir, 'sample_whatsapp_chat.txt')
    
    if not os.path.exists(mock_eml) or not os.path.exists(mock_wa):
        print("Mock data files not found. Please run scripts/verify_ingestion.py first.")
        return
        
    print("\nIngesting and normalizing raw data...")
    gmail_connector.ingest_eml_file(mock_eml)
    whatsapp_connector.ingest_chat_file(mock_wa)
    
    gmail_norm = os.path.join(norm_dir, 'gmail')
    gmail_normalizer = GmailNormalizer(raw_dir=os.path.join(raw_dir, 'gmail'), normalized_dir=gmail_norm)
    gmail_normalizer.normalize_all()
    
    whatsapp_norm = os.path.join(norm_dir, 'whatsapp')
    whatsapp_normalizer = WhatsAppNormalizer(raw_dir=os.path.join(raw_dir, 'whatsapp'), normalized_dir=whatsapp_norm, agent_names=['Jane Doe'])
    whatsapp_normalizer.normalize_all()
    
    merger = ConversationMerger(normalized_dirs=[gmail_norm, whatsapp_norm], unified_dir=unified_dir)
    merger.merge_all()
    
    # 2. Run ThreadBuilder
    print("\nRunning ThreadBuilder (splitting chats)...")
    # We set a gap threshold of 45 seconds to force the mock WhatsApp log to split
    # Since message 2 -> message 3 gap is 49 seconds.
    builder = ThreadBuilder(
        input_dir=unified_dir,
        output_dir=reconstructed_dir,
        gap_threshold_seconds=45
    )
    reconstructed_files = builder.process_all()
    print(f"Reconstruction completed. Created {len(reconstructed_files)} session files.")
    
    # List files created in reconstructed
    print("\nFiles in normalized/reconstructed/:")
    for f_name in os.listdir(reconstructed_dir):
        if f_name.endswith('.json'):
            print(f"  - {f_name}")
            
    # 3. Run ConversationValidator
    print("\nRunning ConversationValidator...")
    validator = ConversationValidator(
        input_dir=reconstructed_dir,
        report_path=report_path
    )
    report = validator.validate_all()
    print("Validator completed. Generated report.")
    
    # 4. Display Report Details
    print("\n--- validation_report.json ---")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    
    print("\nReconstruction and Validation verification completed successfully!")

if __name__ == '__main__':
    main()
