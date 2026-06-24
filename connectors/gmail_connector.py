import os
import email
from email.message import Message
import mailbox
import json
from typing import Dict, Any, List
from storage import RawStorage

class GmailConnector:
    def __init__(self, storage: RawStorage):
        """
        Initialize GmailConnector.
        :param storage: RawStorage instance to save parsed messages.
        """
        self.storage = storage

    def parse_message(self, msg: Message) -> Dict[str, Any]:
        """
        Parses a standard email Message object into a clean dictionary payload.
        """
        headers = {}
        for header in ['Message-ID', 'From', 'To', 'Subject', 'Date', 'Cc', 'Bcc']:
            headers[header] = msg.get(header, "")
            
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    payload = part.get_payload(decode=True)
                    if payload:
                        body += payload.decode(part.get_content_charset() or 'utf-8', errors='replace')
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode(msg.get_content_charset() or 'utf-8', errors='replace')
                
        return {
            "source": "gmail",
            "headers": headers,
            "body": body.strip()
        }

    def ingest_eml_file(self, file_path: str) -> str:
        """
        Ingests a single .eml file and saves the parsed raw JSON representation to storage.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"EML file not found at {file_path}")
            
        with open(file_path, 'rb') as f:
            msg = email.message_from_binary_file(f)
            
        parsed = self.parse_message(msg)
        
        # Use Message-ID to construct a unique filename, otherwise use the basename
        msg_id = parsed["headers"].get("Message-ID", "")
        if msg_id:
            # clean up message ID for safe filename
            safe_id = "".join([c if c.isalnum() else "_" for c in msg_id]).strip("_")
            filename = f"email_{safe_id}.json"
        else:
            base = os.path.basename(file_path)
            name, _ = os.path.splitext(base)
            filename = f"email_{name}.json"
            
        return self.storage.save_raw("gmail", filename, parsed)

    def ingest_mbox_file(self, file_path: str) -> List[str]:
        """
        Ingests an MBOX mailbox file (Google Takeout format) and saves all messages to raw storage.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"MBOX file not found at {file_path}")
            
        saved_paths = []
        mbox = mailbox.mbox(file_path)
        
        for idx, msg in enumerate(mbox):
            parsed = self.parse_message(msg)
            msg_id = parsed["headers"].get("Message-ID", "")
            if msg_id:
                safe_id = "".join([c if c.isalnum() else "_" for c in msg_id]).strip("_")
                filename = f"email_{safe_id}.json"
            else:
                filename = f"email_mbox_{idx}.json"
                
            saved_path = self.storage.save_raw("gmail", filename, parsed)
            saved_paths.append(saved_path)
            
        return saved_paths
