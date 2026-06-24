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
    
    # Create mock inputs with signatures, duplicates, and PII
    print("\nCreating dirty mock logs with PII & signatures...")
    mock_data_dir = os.path.join(project_root, 'tests', 'mock_data')
    os.makedirs(mock_data_dir, exist_ok=True)
    
    # Mock Email (.eml) with PII and signatures
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
        
    # Mock WhatsApp (.txt) with auto-replies, duplicates, signatures, PII
    mock_wa = os.path.join(mock_data_dir, 'sample_whatsapp_chat.txt')
    with open(mock_wa, 'w', encoding='utf-8') as f:
        f.write(
            "[24/06/2026, 10:15:30] +1 (555) 019-9234: Hey Jane, did you hear back from support about the order?\n"
            "[24/06/2026, 10:16:12] Jane Doe: I am currently out of office and will reply later.\n" # Auto-reply keyword
            "[24/06/2026, 10:16:30] Jane Doe: Sorry for that. No support reply yet. Contact support@shop.com or call 555-019-9234.\n"
            "Best regards,\n"
            "Jane Doe\n" # Signature block
            "[24/06/2026, 10:16:30] Jane Doe: Sorry for that. No support reply yet. Contact support@shop.com or call 555-019-9234.\n"
            "Best regards,\n"
            "Jane Doe\n" # Consecutive duplicate message
            "[24/06/2026, 10:17:01] +1 (555) 019-9234: ok\n" # Low quality message
        )
        
    # Ingest
    gmail_connector.ingest_eml_file(mock_eml)
    whatsapp_connector.ingest_chat_file(mock_wa)
    
    # Normalize & Merge
    gmail_norm = os.path.join(norm_dir, 'gmail')
    gmail_normalizer = GmailNormalizer(raw_dir=os.path.join(raw_dir, 'gmail'), normalized_dir=gmail_norm)
    gmail_normalizer.normalize_all()
    
    whatsapp_norm = os.path.join(norm_dir, 'whatsapp')
    whatsapp_normalizer = WhatsAppNormalizer(raw_dir=os.path.join(raw_dir, 'whatsapp'), normalized_dir=whatsapp_norm, agent_names=['Jane Doe'])
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
