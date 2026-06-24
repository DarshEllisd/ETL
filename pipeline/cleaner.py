import os
import json
import re
from typing import Dict, Any, List

class ConversationCleaner:
    def __init__(
        self, 
        input_dir: str, 
        output_dir: str, 
        autoreply_keywords: List[str] = None,
        low_quality_blacklist: List[str] = None,
        remove_duplicates: bool = True
    ):
        """
        Initialize ConversationCleaner.
        :param input_dir: Directory containing reconstructed conversation records.
        :param output_dir: Target directory to write cleaned conversation records.
        :param autoreply_keywords: Words to trigger discarding a message as an auto-reply.
        :param low_quality_blacklist: Words to trigger discarding a message as low-quality.
        :param remove_duplicates: Whether to drop consecutive identical messages from the same sender.
        """
        self.input_dir = os.path.abspath(input_dir)
        self.output_dir = os.path.abspath(output_dir)
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Configure filters
        self.autoreply_keywords = [k.lower() for k in (autoreply_keywords or ["out of office", "automatic reply", "do-not-reply", "auto-reply"])]
        self.low_quality_blacklist = [b.lower().strip() for b in (low_quality_blacklist or ["ok", "thanks", "👍", "hello", "hi", "thank you", "k"])]
        self.remove_duplicates = remove_duplicates
        
        # Signature patterns
        # 1. Matches common "Sent from my..." lines
        # 2. Matches common email signature closers like "Best regards,", "Thanks," followed by name/empty space at the end of the text
        self.signature_regexes = [
            re.compile(r'^sent\s+from\s+(?:my\s+)?(iphone|android|ipad|samsung|mobile|mail|phone).*$', re.IGNORECASE),
            re.compile(r'^(best\s+regards|sincerely|thanks|regards|warm\s+regards|thank\s+you),?\s*$', re.IGNORECASE)
        ]

    def is_autoreply(self, text: str) -> bool:
        lower_text = text.lower()
        for kw in self.autoreply_keywords:
            if kw in lower_text:
                return True
        return False

    def is_low_quality(self, text: str) -> bool:
        clean_text = text.lower().strip().strip('.').strip('!')
        return clean_text in self.low_quality_blacklist

    def clean_signatures(self, text: str) -> str:
        """
        Strips signatures and closing lines from the bottom of the text body.
        """
        lines = text.splitlines()
        if not lines:
            return ""
            
        # We start checking lines from the bottom up to strip trailing signatures
        last_valid_idx = len(lines)
        
        for i in range(len(lines) - 1, -1, -1):
            line_str = lines[i].strip()
            if not line_str:
                continue
                
            # Check if this line matches any signature pattern
            matched = False
            for regex in self.signature_regexes:
                if regex.match(line_str):
                    matched = True
                    break
                    
            if matched:
                # If matched, we truncate everything from this line downwards
                last_valid_idx = i
            else:
                # If we encounter a normal text line and we are checking from bottom-up,
                # we stop stripping. (Signatures are always at the bottom)
                # But wait: if there's a trailing name after a closer line, e.g. "Thanks,\nJohn Doe"
                # If we check John Doe, it won't match "regards" regex.
                # However, if we check "Thanks," it will match.
                # So we can keep searching up a few lines to catch closures even if followed by short name blocks.
                # To prevent false positives, we check if the line is very short (less than 20 chars).
                if len(line_str) < 20:
                    continue
                else:
                    break
                    
        cleaned_lines = lines[:last_valid_idx]
        return "\n".join(cleaned_lines).strip()

    def clean_conversation_data(self, conv_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Applies cleaning rules to a single conversation record.
        """
        cleaned_messages = []
        prev_msg = None
        
        for msg in conv_data.get("messages", []):
            text = msg.get("text", "")
            
            # 1. Filter out Auto-Replies
            if self.is_autoreply(text):
                continue
                
            # 2. Strip signatures
            cleaned_text = self.clean_signatures(text)
            
            # 3. Filter out consecutive duplicates from same speaker based on cleaned text
            if self.remove_duplicates and prev_msg:
                if prev_msg["speaker"] == msg["speaker"] and prev_msg["text"] == cleaned_text:
                    continue
            
            # 4. Filter out Low Quality Messages
            if self.is_low_quality(cleaned_text):
                continue
                
            if not cleaned_text:
                continue
                
            # Build cleaned message object
            msg_copy = msg.copy()
            msg_copy["text"] = cleaned_text
            cleaned_messages.append(msg_copy)
            
            # Track as previous valid message
            prev_msg = msg_copy
            
        # Rebuild conversation data with cleaned messages
        cleaned_conv = conv_data.copy()
        cleaned_conv["messages"] = cleaned_messages
        
        # Recalculate timestamps and lengths if messages exist
        if cleaned_messages:
            cleaned_conv["start_timestamp"] = cleaned_messages[0]["timestamp"]
            cleaned_conv["end_timestamp"] = cleaned_messages[-1]["timestamp"]
            cleaned_conv["metadata"] = conv_data.get("metadata", {}).copy()
            cleaned_conv["metadata"]["total_messages"] = len(cleaned_messages)
            cleaned_conv["metadata"]["cleaned"] = True
            # Store count of messages removed
            removed_count = len(conv_data.get("messages", [])) - len(cleaned_messages)
            cleaned_conv["metadata"]["messages_removed"] = removed_count
        else:
            cleaned_conv["start_timestamp"] = ""
            cleaned_conv["end_timestamp"] = ""
            cleaned_conv["metadata"] = conv_data.get("metadata", {}).copy()
            cleaned_conv["metadata"]["total_messages"] = 0
            cleaned_conv["metadata"]["cleaned"] = True
            cleaned_conv["metadata"]["messages_removed"] = len(conv_data.get("messages", []))
            
        return cleaned_conv

    def process_file(self, filename: str) -> str:
        input_path = os.path.join(self.input_dir, filename)
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        cleaned_data = self.clean_conversation_data(data)
        
        output_path = os.path.join(self.output_dir, filename)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(cleaned_data, f, indent=2, ensure_ascii=False)
            
        return output_path

    def process_all(self) -> List[str]:
        output_files = []
        if not os.path.exists(self.input_dir):
            return output_files
        for filename in os.listdir(self.input_dir):
            if filename.endswith(".json"):
                output_files.append(self.process_file(filename))
        return output_files
