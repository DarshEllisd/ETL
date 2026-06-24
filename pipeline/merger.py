import os
import json
from datetime import datetime
from typing import Dict, Any, List

class ConversationMerger:
    def __init__(self, normalized_dirs: List[str], unified_dir: str):
        """
        Initialize ConversationMerger.
        :param normalized_dirs: List of directories containing normalized messages (e.g. gmail, whatsapp).
        :param unified_dir: Target directory for storing unified conversation records.
        """
        self.normalized_dirs = [os.path.abspath(d) for d in normalized_dirs]
        self.unified_dir = os.path.abspath(unified_dir)
        os.makedirs(self.unified_dir, exist_ok=True)

    def merge_all(self) -> List[str]:
        """
        Reads all normalized message JSONs, groups them by conversation_id,
        sorts them chronologically, and saves unified conversation records.
        """
        conversations: Dict[str, List[Dict[str, Any]]] = {}
        
        # 1. Read all normalized messages
        for n_dir in self.normalized_dirs:
            if not os.path.exists(n_dir):
                continue
            for filename in os.listdir(n_dir):
                if filename.endswith(".json"):
                    file_path = os.path.join(n_dir, filename)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        msg = json.load(f)
                    
                    conv_id = msg.get("conversation_id")
                    if conv_id:
                        if conv_id not in conversations:
                            conversations[conv_id] = []
                        conversations[conv_id].append(msg)
                        
        output_files = []
        
        # 2. Process and merge each conversation group
        for conv_id, messages in conversations.items():
            # Sort messages chronologically by timestamp
            # ISO 8601 string sort is correct for YYYY-MM-DDTHH:MM:SSZ format,
            # but to be perfectly safe we can parse or sort by string.
            messages.sort(key=lambda m: m.get("timestamp", ""))
            
            # Determine source from the message ID prefixes (e.g. gmail_msg_... or whatsapp_msg_...)
            source = "unknown"
            if messages:
                sample_id = messages[0].get("message_id", "")
                if sample_id.startswith("gmail_"):
                    source = "gmail"
                elif sample_id.startswith("whatsapp_"):
                    source = "whatsapp"
                    
            start_ts = messages[0].get("timestamp", "") if messages else ""
            end_ts = messages[-1].get("timestamp", "") if messages else ""
            
            # Construct unified conversation record
            # We strip metadata fields from internal messages for a cleaner structure,
            # or keep them. Let's keep them so that down-stream threads have all info,
            # but structure the overall record matching Issue #8 and docs/schema.md
            clean_messages = []
            for msg in messages:
                clean_messages.append({
                    "message_id": msg["message_id"],
                    "timestamp": msg["timestamp"],
                    "speaker": msg["speaker"],
                    "text": msg["text"]
                })
                
            unified_conv = {
                "conversation_id": conv_id,
                "source": source,
                "start_timestamp": start_ts,
                "end_timestamp": end_ts,
                "messages": clean_messages,
                "metadata": {
                    "total_messages": len(messages)
                }
            }
            
            # Save unified record
            out_path = os.path.join(self.unified_dir, f"{conv_id}.json")
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(unified_conv, f, indent=2, ensure_ascii=False)
                
            output_files.append(out_path)
            
        return output_files
