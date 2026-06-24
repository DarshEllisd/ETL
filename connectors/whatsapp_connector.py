import os
import re
import json
from typing import Dict, Any, List
from storage import RawStorage

class WhatsAppConnector:
    def __init__(self, storage: RawStorage):
        """
        Initialize WhatsAppConnector.
        :param storage: RawStorage instance to save parsed messages.
        """
        self.storage = storage

        # Compile regexes for standard WhatsApp formats:
        # Pattern 1 (Android-style or similar): e.g., "19/06/2026, 12:30 - Name: Hello"
        # Pattern 2 (iOS-style): e.g., "[19/06/26, 12:30:15] Name: Hello"
        # We capture: Group 1 = Date, Group 2 = Time, Group 3 = Sender, Group 4 = Message text
        self.android_pattern = re.compile(
            r'^(\d{1,2}[/\.-]\d{1,2}[/\.-]\d{2,4}),\s+(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[aApP][mM])?)\s+-\s+([^:]+):\s*(.*)$'
        )
        self.ios_pattern = re.compile(
            r'^\[(\d{1,2}[/\.-]\d{1,2}[/\.-]\d{2,4}),\s+(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[aApP][mM])?)\]\s+([^:]+):\s*(.*)$'
        )

    def parse_log(self, log_content: str) -> List[Dict[str, Any]]:
        """
        Parses raw WhatsApp chat export text into a list of message dictionaries.
        Handles multi-line messages correctly.
        """
        parsed_messages = []
        current_msg = None

        lines = log_content.splitlines()
        for line in lines:
            line_str = line.strip()
            if not line_str:
                # If there's an empty line, append it to the current message if it exists
                if current_msg:
                    current_msg["text"] += "\n"
                continue

            # Try to match Android or iOS patterns
            match = self.android_pattern.match(line) or self.ios_pattern.match(line)

            if match:
                # Save previous message before starting the new one
                if current_msg:
                    parsed_messages.append(current_msg)
                
                date_part = match.group(1)
                time_part = match.group(2)
                sender = match.group(3).strip()
                message_text = match.group(4)

                current_msg = {
                    "source": "whatsapp",
                    "raw_date": date_part,
                    "raw_time": time_part,
                    "sender": sender,
                    "text": message_text
                }
            else:
                # Line does not match the timestamp pattern - it's either a multi-line continuation or a system log
                if current_msg:
                    current_msg["text"] += "\n" + line
                # If there is no current message, it's probably system headers at the very start of the chat log; ignore them.

        # Add the last message
        if current_msg:
            parsed_messages.append(current_msg)

        return parsed_messages

    def ingest_chat_file(self, file_path: str) -> str:
        """
        Ingests a WhatsApp chat log file (.txt) and saves the parsed raw JSON array to storage.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"WhatsApp log file not found at {file_path}")
            
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
            
        parsed_list = self.parse_log(content)
        
        base = os.path.basename(file_path)
        name, _ = os.path.splitext(base)
        filename = f"whatsapp_{name}.json"
        
        # Save the list of parsed messages directly as raw JSON
        payload = {
            "source": "whatsapp",
            "messages": parsed_list
        }
        
        return self.storage.save_raw("whatsapp", filename, payload)
