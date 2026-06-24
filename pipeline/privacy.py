import os
import json
import re
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple

class PrivacyScrubber:
    def __init__(self, input_dir: str, output_dir: str, report_path: str):
        """
        Initialize PrivacyScrubber.
        :param input_dir: Directory containing cleaned conversation records.
        :param output_dir: Directory to save anonymized conversation records.
        :param report_path: File path to save the final validation report (e.g. 'privacy_report.json').
        """
        self.input_dir = os.path.abspath(input_dir)
        self.output_dir = os.path.abspath(output_dir)
        self.report_path = os.path.abspath(report_path)
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Regex compiled patterns
        self.email_regex = re.compile(
            r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        )
        # Matches common phone number formats:
        # e.g., +1 (555) 019-9234, +91 98765-43210, 555-019-9234, 5550199234
        self.phone_regex = re.compile(
            r'(\+?\d{1,4}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4,6}|'
            r'(\+?\d{1,4}[-.\s]?)?\d{5}[-.\s]?\d{5}|'
            r'\b\d{7,14}\b'
        )

    def scrub_text(self, text: str) -> Tuple[str, int, int]:
        """
        Scrubs email addresses and phone numbers from the text.
        Returns tuple of (scrubbed_text, email_scrub_count, phone_scrub_count).
        """
        if not text:
            return "", 0, 0
            
        # Scrub emails
        scrubbed, email_count = self.email_regex.subn('[EMAIL]', text)
        
        # Scrub phones
        scrubbed, phone_count = self.phone_regex.subn('[PHONE]', scrubbed)
        
        return scrubbed, email_count, phone_count

    def scrub_conversation_data(self, conv_data: Dict[str, Any]) -> Tuple[Dict[str, Any], int, int]:
        """
        Scrubs a single conversation record.
        """
        anonymized_messages = []
        total_emails = 0
        total_phones = 0
        
        for msg in conv_data.get("messages", []):
            text = msg.get("text", "")
            scrubbed_text, e_count, p_count = self.scrub_text(text)
            
            total_emails += e_count
            total_phones += p_count
            
            msg_copy = msg.copy()
            msg_copy["text"] = scrubbed_text
            anonymized_messages.append(msg_copy)
            
        anonymized_conv = conv_data.copy()
        anonymized_conv["messages"] = anonymized_messages
        
        # Save scrub counts in metadata
        anonymized_conv["metadata"] = conv_data.get("metadata", {}).copy()
        anonymized_conv["metadata"]["anonymized"] = True
        anonymized_conv["metadata"]["pii_emails_scrubbed"] = total_emails
        anonymized_conv["metadata"]["pii_phones_scrubbed"] = total_phones
        
        return anonymized_conv, total_emails, total_phones

    def process_file(self, filename: str) -> Tuple[str, int, int]:
        input_path = os.path.join(self.input_dir, filename)
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        anonymized_data, e_count, p_count = self.scrub_conversation_data(data)
        
        output_path = os.path.join(self.output_dir, filename)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(anonymized_data, f, indent=2, ensure_ascii=False)
            
        return output_path, e_count, p_count

    def process_all(self) -> Dict[str, Any]:
        """
        Scrubs all conversation records and writes privacy_report.json.
        """
        report_data = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "stats": {
                "total_files_anonymized": 0,
                "total_emails_scrubbed": 0,
                "total_phones_scrubbed": 0
            },
            "scrubbed_details": []
        }
        
        if not os.path.exists(self.input_dir):
            return report_data
            
        total_files = 0
        total_emails = 0
        total_phones = 0
        
        for filename in os.listdir(self.input_dir):
            if filename.endswith(".json"):
                total_files += 1
                out_path, e_count, p_count = self.process_file(filename)
                
                if e_count > 0 or p_count > 0:
                    conv_id = filename.split('.')[0]
                    report_data["scrubbed_details"].append({
                        "conversation_id": conv_id,
                        "file": filename,
                        "emails_scrubbed": e_count,
                        "phones_scrubbed": p_count
                    })
                total_emails += e_count
                total_phones += p_count
                
        report_data["stats"]["total_files_anonymized"] = total_files
        report_data["stats"]["total_emails_scrubbed"] = total_emails
        report_data["stats"]["total_phones_scrubbed"] = total_phones
        
        # Write report
        report_dir = os.path.dirname(self.report_path)
        if report_dir:
            os.makedirs(report_dir, exist_ok=True)
            
        with open(self.report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
            
        return report_data
