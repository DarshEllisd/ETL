import os
import json
import re
import hashlib
from datetime import datetime, timezone
import email.utils
from typing import Dict, Any, List

class BaseNormalizer:
    def __init__(self, raw_dir: str, normalized_dir: str):
        self.raw_dir = os.path.abspath(raw_dir)
        self.normalized_dir = os.path.abspath(normalized_dir)
        os.makedirs(self.normalized_dir, exist_ok=True)

    def _hash_string(self, text: str) -> str:
        return hashlib.md5(text.encode('utf-8')).hexdigest()

class GmailNormalizer(BaseNormalizer):
    def __init__(self, raw_dir: str, normalized_dir: str, company_domains: List[str] = None, agent_names: List[str] = None):
        super().__init__(raw_dir, normalized_dir)
        self.company_domains = company_domains or ['shop.com']
        self.agent_names = [name.lower().strip() for name in (agent_names or [])]

    def normalize_speaker(self, from_header: str) -> str:
        """
        Determines the role of the sender.
        If sender email or name matches agent_names, or if domain is in company_domains, it's 'assistant', else 'user'.
        """
        name, email_address = email.utils.parseaddr(from_header)
        email_address = email_address.lower().strip()
        name = name.lower().strip()
        
        if email_address in self.agent_names or name in self.agent_names:
            return "assistant"
            
        # Check if the domain matches any company domain
        for domain in self.company_domains:
            if email_address.endswith(f"@{domain}") or email_address.endswith(f".{domain}"):
                return "assistant"
        return "user"

    def normalize_timestamp(self, date_header: str) -> str:
        """
        Parses RFC 2822 date header into ISO 8601 UTC format.
        """
        if not date_header:
            return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            dt = email.utils.parsedate_to_datetime(date_header)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            # Fallback
            return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def normalize_conversation_id(self, subject: str) -> str:
        """
        Groups emails by normalizing the subject line (stripping Re:, Fwd:, etc.).
        """
        clean_subject = subject.lower()
        # Regex to strip leading Re:, Fwd:, Fw:, etc.
        clean_subject = re.sub(r'^(re|fwd|fw|reply|forward):\s*', '', clean_subject, flags=re.IGNORECASE)
        clean_subject = clean_subject.strip()
        
        if not clean_subject:
            clean_subject = "no-subject"
            
        return f"email_thread_{self._hash_string(clean_subject)}"

    def normalize_file(self, filename: str) -> str:
        """
        Normalizes a single raw Gmail JSON file and writes the canonical message JSON.
        """
        raw_path = os.path.join(self.raw_dir, filename)
        with open(raw_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
            
        headers = raw_data.get("headers", {})
        body = raw_data.get("body", "")
        
        raw_msg_id = headers.get("Message-ID", "")
        if raw_msg_id:
            message_id = f"gmail_msg_{self._hash_string(raw_msg_id)}"
        else:
            # Fallback based on filename hash
            message_id = f"gmail_msg_{self._hash_string(filename)}"
            
        conv_id = self.normalize_conversation_id(headers.get("Subject", ""))
        speaker = self.normalize_speaker(headers.get("From", ""))
        timestamp = self.normalize_timestamp(headers.get("Date", ""))
        
        canonical_msg = {
            "message_id": message_id,
            "conversation_id": conv_id,
            "timestamp": timestamp,
            "speaker": speaker,
            "text": body,
            "metadata": {
                "raw_speaker_name": headers.get("From", ""),
                "subject": headers.get("Subject", ""),
                "raw_message_id": raw_msg_id
            }
        }
        
        out_path = os.path.join(self.normalized_dir, f"{message_id}.json")
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(canonical_msg, f, indent=2, ensure_ascii=False)
            
        return out_path

    def normalize_all(self) -> List[str]:
        output_files = []
        if not os.path.exists(self.raw_dir):
            return output_files
        for filename in os.listdir(self.raw_dir):
            if filename.endswith(".json"):
                output_files.append(self.normalize_file(filename))
        return output_files


class WhatsAppNormalizer(BaseNormalizer):
    def __init__(self, raw_dir: str, normalized_dir: str, agent_names: List[str] = None):
        super().__init__(raw_dir, normalized_dir)
        self.agent_names = [name.lower().strip() for name in (agent_names or ["Jane Doe"])]

    def normalize_speaker(self, sender: str) -> str:
        """
        Determines the role of the sender.
        If sender name is in agent_names, it is 'assistant', else 'user'.
        """
        if sender.lower().strip() in self.agent_names:
            return "assistant"
        return "user"

    def normalize_timestamp(self, date_str: str, time_str: str) -> str:
        """
        Parses WhatsApp date and time parts into ISO 8601 UTC format.
        """
        combined = f"{date_str} {time_str}".strip()
        # Common format patterns in exports
        patterns = [
            "%d/%m/%Y %H:%M:%S",  # iOS 24h
            "%d/%m/%y %H:%M:%S",   # iOS 2h
            "%d/%m/%Y %H:%M",     # Android 24h
            "%d/%m/%y %H:%M",      # Android 2h
            "%d/%m/%Y %I:%M:%S %p",# iOS 12h
            "%d/%m/%y %I:%M:%S %p",# iOS 12h
            "%d/%m/%Y %I:%M %p",   # Android 12h
            "%d/%m/%y %I:%M %p",    # Android 12h
            # US styles
            "%m/%d/%Y %H:%M:%S",
            "%m/%d/%y %H:%M:%S",
            "%m/%d/%Y %I:%M %p",
            "%m/%d/%y %I:%M %p"
        ]
        
        for pattern in patterns:
            try:
                dt = datetime.strptime(combined, pattern)
                dt = dt.replace(tzinfo=timezone.utc)
                return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                continue
                
        # Fallback if no patterns match
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def normalize_file(self, filename: str) -> List[str]:
        """
        Normalizes a raw WhatsApp JSON log (contains message array) and writes individual canonical messages.
        """
        raw_path = os.path.join(self.raw_dir, filename)
        with open(raw_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
            
        messages = raw_data.get("messages", [])
        output_files = []
        
        # Use filename hash as conversation ID base
        conv_id = f"whatsapp_chat_{self._hash_string(filename)}"
        
        for idx, msg in enumerate(messages):
            sender = msg.get("sender", "")
            text = msg.get("text", "")
            raw_date = msg.get("raw_date", "")
            raw_time = msg.get("raw_time", "")
            
            # Message ID deterministic hash
            hash_input = f"{sender}_{raw_date}_{raw_time}_{text[:100]}_{idx}"
            message_id = f"whatsapp_msg_{self._hash_string(hash_input)}"
            
            speaker = self.normalize_speaker(sender)
            timestamp = self.normalize_timestamp(raw_date, raw_time)
            
            canonical_msg = {
                "message_id": message_id,
                "conversation_id": conv_id,
                "timestamp": timestamp,
                "speaker": speaker,
                "text": text,
                "metadata": {
                    "raw_speaker_name": sender
                }
            }
            
            out_path = os.path.join(self.normalized_dir, f"{message_id}.json")
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(canonical_msg, f, indent=2, ensure_ascii=False)
                
            output_files.append(out_path)
            
        return output_files

    def normalize_all(self) -> List[str]:
        output_files = []
        if not os.path.exists(self.raw_dir):
            return output_files
        for filename in os.listdir(self.raw_dir):
            if filename.endswith(".json"):
                output_files.extend(self.normalize_file(filename))
        return output_files
