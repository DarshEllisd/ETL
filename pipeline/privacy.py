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
        # e.g., +1 (555) 019-9234, +91 98765-43210, 555-019-9234, 5550199234, +44 20 7946 0958
        # We put \+? before \b because + is a non-word character and \b doesn't match before it if preceded by a space.
        self.phone_regex = re.compile(
            r'\+?\b(?:\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b|' # US/Intl 3-3-4
            r'\+?\b(?:\d{1,3}[-.\s]?)?\d{2}[-.\s]?\d{4}[-.\s]?\d{4}\b|'       # UK 2-4-4
            r'\+?\b(?:44\s?|0)7\d{3}[-.\s]?\d{6}\b|'                          # UK Mobile 5-6
            r'\+?\b(?:\d{1,3}[-.\s]?)?\d{5}[-.\s]?\d{5}\b'                    # India/others 5-5
        )

        # Matches passwords and credentials with optional helper verbs:
        # e.g., password: mySecretKey, credential is: Secret_Key, PIN = 1234
        self.password_regex = re.compile(
            r'\b(password|pass|pin|passwd|credential|secret\s+key|secret|key)\b(\s*(is|are|of|to)?\s*[:=]\s*)([A-Za-z0-9_#$@\-]+)', re.IGNORECASE
        )

        # Matches standard street addresses and postal zip codes:
        # e.g., 123 Main St, 456 Maple Avenue, 10001
        self.address_regex = re.compile(
            r'\b\d+\s+[A-Za-z0-9\s,\.]+?\s+(Street|St|Avenue|Ave|Road|Rd|Lane|Ln|Boulevard|Blvd|Drive|Dr|Way|Court|Ct|Parkway|Pkwy|Plaza|Plz|Place|Pl|Square|Sq|Terrace|Ter|Highway|Hwy)\b|'
            r'(?<![#$€£])\b\d{5}(-\d{4})?\b', re.IGNORECASE
        )

    def scrub_text(self, text: str, participant_names: List[str] = None) -> Dict[str, Any]:
        """
        Scrubs email addresses, phone numbers, passwords, addresses, and participant names.
        Returns a dictionary containing the scrubbed text and counts of replacements.
        """
        if not text:
            return {
                "text": "",
                "emails": 0,
                "phones": 0,
                "passwords": 0,
                "addresses": 0,
                "names": 0
            }
            
        # 1. Scrub emails
        scrubbed, email_count = self.email_regex.subn('[EMAIL]', text)
        
        # 2. Scrub phones
        scrubbed, phone_count = self.phone_regex.subn('[PHONE]', scrubbed)
        
        # 3. Scrub physical addresses / zips
        scrubbed, address_count = self.address_regex.subn('[ADDRESS]', scrubbed)
        
        # 4. Scrub passwords/secrets (using custom replacement to normalize separators)
        def replace_password(match):
            label = match.group(1)
            connector = match.group(2)
            if ':' in connector or any(w in connector.lower() for w in ['is', 'are', 'of', 'to']):
                return f"{label}{connector}[PASSWORD]"
            else:
                return f"{label}: [PASSWORD]"
                
        scrubbed, password_count = self.password_regex.subn(replace_password, scrubbed)
        
        # 5. Scrub participant names if provided
        name_count = 0
        if participant_names:
            # Sort names by length descending to replace longer matches first
            sorted_names = sorted(list(set(participant_names)), key=len, reverse=True)
            for name in sorted_names:
                if len(name) < 3:
                    continue
                # Use word boundaries to prevent matching names inside other words
                pattern = re.compile(rf'\b{re.escape(name)}\b', re.IGNORECASE)
                scrubbed, sub_count = pattern.subn('[NAME]', scrubbed)
                name_count += sub_count
                
        return {
            "text": scrubbed,
            "emails": email_count,
            "phones": phone_count,
            "passwords": password_count,
            "addresses": address_count,
            "names": name_count
        }

    def extract_participants(self, conv_data: Dict[str, Any]) -> List[str]:
        """
        Helper to gather participant names from email headers, WhatsApp senders,
        and conversation metadata.
        """
        participants = set()
        
        # Check top-level metadata
        conv_meta = conv_data.get("metadata", {})
        for key in ["raw_speaker_name", "agent_name", "customer_name"]:
            val = conv_meta.get(key, "")
            if val and not re.match(r'^\+?[\d\s\-\(\)]+$', val):
                participants.add(val)
                parts = [p.strip() for p in re.split(r'[\s,]+', val) if p.strip()]
                for p in parts:
                    if len(p) >= 3:
                        participants.add(p)
                        
        # Check individual messages
        for msg in conv_data.get("messages", []):
            sender = msg.get("metadata", {}).get("raw_speaker_name", "")
            if not sender:
                sender = msg.get("sender", "")
            if not sender:
                sender = msg.get("speaker", "")
                
            # If email format like "Jane Doe <jane@mail.com>", extract "Jane Doe"
            if "<" in sender and ">" in sender:
                sender = sender.split("<")[0].strip()
                
            # Exclude raw phone numbers or numeric identifiers from being names
            if sender and not re.match(r'^\+?[\d\s\-\(\)]+$', sender):
                participants.add(sender)
                # Split into first/last name parts
                parts = [p.strip() for p in re.split(r'[\s,]+', sender) if p.strip()]
                for p in parts:
                    if len(p) >= 3:
                        participants.add(p)
                        
        return list(participants)

    def scrub_conversation_data(self, conv_data: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, int]]:
        """
        Scrubs a single conversation record.
        """
        participant_names = self.extract_participants(conv_data)
        
        anonymized_messages = []
        counts = {
            "emails": 0,
            "phones": 0,
            "passwords": 0,
            "addresses": 0,
            "names": 0
        }
        
        for msg in conv_data.get("messages", []):
            text = msg.get("text", "")
            res = self.scrub_text(text, participant_names)
            
            for key in counts:
                counts[key] += res[key]
                
            msg_copy = msg.copy()
            msg_copy["text"] = res["text"]
            anonymized_messages.append(msg_copy)
            
        anonymized_conv = conv_data.copy()
        anonymized_conv["messages"] = anonymized_messages
        
        # Save scrub counts in metadata
        anonymized_conv["metadata"] = conv_data.get("metadata", {}).copy()
        anonymized_conv["metadata"]["anonymized"] = True
        anonymized_conv["metadata"]["pii_emails_scrubbed"] = counts["emails"]
        anonymized_conv["metadata"]["pii_phones_scrubbed"] = counts["phones"]
        anonymized_conv["metadata"]["pii_passwords_scrubbed"] = counts["passwords"]
        anonymized_conv["metadata"]["pii_addresses_scrubbed"] = counts["addresses"]
        anonymized_conv["metadata"]["pii_names_scrubbed"] = counts["names"]
        
        return anonymized_conv, counts

    def process_file(self, filename: str) -> Tuple[str, Dict[str, int]]:
        input_path = os.path.join(self.input_dir, filename)
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        anonymized_data, counts = self.scrub_conversation_data(data)
        
        output_path = os.path.join(self.output_dir, filename)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(anonymized_data, f, indent=2, ensure_ascii=False)
            
        return output_path, counts

    def process_all(self) -> Dict[str, Any]:
        """
        Scrubs all conversation records and writes privacy_report.json.
        """
        report_data = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "stats": {
                "total_files_anonymized": 0,
                "total_emails_scrubbed": 0,
                "total_phones_scrubbed": 0,
                "total_passwords_scrubbed": 0,
                "total_addresses_scrubbed": 0,
                "total_names_scrubbed": 0
            },
            "scrubbed_details": []
        }
        
        if not os.path.exists(self.input_dir):
            return report_data
            
        total_files = 0
        totals = {
            "emails": 0,
            "phones": 0,
            "passwords": 0,
            "addresses": 0,
            "names": 0
        }
        
        for filename in os.listdir(self.input_dir):
            if filename.endswith(".json"):
                total_files += 1
                out_path, counts = self.process_file(filename)
                
                has_pii = any(val > 0 for val in counts.values())
                if has_pii:
                    conv_id = filename.split('.')[0]
                    report_data["scrubbed_details"].append({
                        "conversation_id": conv_id,
                        "file": filename,
                        "emails_scrubbed": counts["emails"],
                        "phones_scrubbed": counts["phones"],
                        "passwords_scrubbed": counts["passwords"],
                        "addresses_scrubbed": counts["addresses"],
                        "names_scrubbed": counts["names"]
                    })
                    
                for key in totals:
                    totals[key] += counts[key]
                
        report_data["stats"]["total_files_anonymized"] = total_files
        report_data["stats"]["total_emails_scrubbed"] = totals["emails"]
        report_data["stats"]["total_phones_scrubbed"] = totals["phones"]
        report_data["stats"]["total_passwords_scrubbed"] = totals["passwords"]
        report_data["stats"]["total_addresses_scrubbed"] = totals["addresses"]
        report_data["stats"]["total_names_scrubbed"] = totals["names"]
        
        # Write report
        report_dir = os.path.dirname(self.report_path)
        if report_dir:
            os.makedirs(report_dir, exist_ok=True)
            
        with open(self.report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
            
        return report_data
