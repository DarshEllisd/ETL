import os
import shutil
from storage import RawStorage
from connectors import GmailConnector, WhatsAppConnector

def main():
    print("--- ETL Ingestion Manual Verification ---")
    
    # 1. Initialize storage and connectors
    # Base directory relative to project root
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    storage = RawStorage(base_dir=os.path.join(project_root, 'raw'))
    
    gmail_connector = GmailConnector(storage)
    whatsapp_connector = WhatsAppConnector(storage)
    
    # 2. Setup mock data files
    print("\nCreating mock data files...")
    mock_data_dir = os.path.join(project_root, 'tests', 'mock_data')
    os.makedirs(mock_data_dir, exist_ok=True)
    
    # Mock Email (.eml)
    mock_eml_path = os.path.join(mock_data_dir, 'sample_customer_email.eml')
    with open(mock_eml_path, 'w', encoding='utf-8') as f:
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
            "I placed order #12345 on Monday, but I haven't received shipping confirmation yet. Can you please check the status?\n"
            "\n"
            "Thanks,\n"
            "Jane Doe\n"
        )
        
    # Mock WhatsApp (.txt)
    mock_wa_path = os.path.join(mock_data_dir, 'sample_whatsapp_chat.txt')
    with open(mock_wa_path, 'w', encoding='utf-8') as f:
        f.write(
            "[24/06/2026, 10:15:30] +1 (555) 019-9234: Hey Jane, did you hear back from support about the order?\n"
            "[24/06/2026, 10:16:12] Jane Doe: Not yet. I emailed them this morning.\n"
            "Hopefully they reply soon.\n"
            "[24/06/2026, 10:17:01] +1 (555) 019-9234: Let me know when they do!\n"
        )
        
    print(f"Mock email created at: {mock_eml_path}")
    print(f"Mock WhatsApp log created at: {mock_wa_path}")
    
    # 3. Ingest files using connectors
    print("\nRunning ingestion connectors...")
    saved_email = gmail_connector.ingest_eml_file(mock_eml_path)
    saved_whatsapp = whatsapp_connector.ingest_chat_file(mock_wa_path)
    
    print(f"Ingested Gmail output saved to: {saved_email}")
    print(f"Ingested WhatsApp output saved to: {saved_whatsapp}")
    
    # 4. Check folder contents
    raw_dir = os.path.join(project_root, 'raw')
    print(f"\nVerifying folder structure in '{raw_dir}':")
    for root, dirs, files in os.walk(raw_dir):
        rel_path = os.path.relpath(root, project_root)
        print(f"  {rel_path}/")
        for file in files:
            print(f"    - {file}")
            
    print("\nIngestion verification completed successfully!")

if __name__ == '__main__':
    main()
