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
    
    print("\nCreating mock input files...")
    mock_data_dir = os.path.join(project_root, 'tests', 'mock_data')
    os.makedirs(mock_data_dir, exist_ok=True)
    
    # EML file
    mock_eml = os.path.join(mock_data_dir, 'sample_customer_email.eml')
    with open(mock_eml, 'w', encoding='utf-8') as f:
        f.write(
            "Message-ID: <order-12345-alert@shop.com>\n"
            "From: customer@gmail.com\n"
            "To: support@shop.com\n"
            "Subject: Order #12345 Has Not Arrived\n"
            "Date: Wed, 24 Jun 2026 09:30:00 +0000\n"
            "Content-Type: text/plain; charset=\"utf-8\"\n"
            "\n"
            "Hi Support team,\n"
            "\n"
            "I placed order #12345 on Monday, but I haven't received shipping confirmation yet. My phone number is +1 (555) 019-9234 and email is customer@gmail.com.\n"
            "\n"
            "Thanks,\n"
            "Jane Doe\n"
        )
        
    # WhatsApp file
    mock_wa = os.path.join(mock_data_dir, 'sample_whatsapp_chat.txt')
    with open(mock_wa, 'w', encoding='utf-8') as f:
        f.write(
            "[24/06/2026, 10:15:30] +1 (555) 019-9234: Hey Jane, did you hear back from support about the order?\n"
            "[24/06/2026, 10:16:12] Jane Doe: I am currently out of office and will reply later.\n"
            "[24/06/2026, 10:16:30] Jane Doe: Sorry for that. No support reply yet. Contact support@shop.com or call 555-019-9234.\n"
            "Best regards,\n"
            "Jane Doe\n"
            "[24/06/2026, 10:16:30] Jane Doe: Sorry for that. No support reply yet. Contact support@shop.com or call 555-019-9234.\n"
            "Best regards,\n"
            "Jane Doe\n"
            "[24/06/2026, 10:17:01] +1 (555) 019-9234: ok\n"
        )
        
    # Ingest
    gmail_connector.ingest_eml_file(mock_eml)
    whatsapp_connector.ingest_chat_file(mock_wa)
    
    # Normalize
    gmail_norm = os.path.join(norm_dir, 'gmail')
    gmail_normalizer = GmailNormalizer(raw_dir=os.path.join(raw_dir, 'gmail'), normalized_dir=gmail_norm)
    gmail_normalizer.normalize_all()
    
    whatsapp_norm = os.path.join(norm_dir, 'whatsapp')
    whatsapp_normalizer = WhatsAppNormalizer(raw_dir=os.path.join(raw_dir, 'whatsapp'), normalized_dir=whatsapp_norm, agent_names=['Jane Doe'])
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
