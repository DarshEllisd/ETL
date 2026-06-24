import os
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple

class ConversationValidator:
    def __init__(self, input_dir: str, report_path: str):
        """
        Initialize ConversationValidator.
        :param input_dir: Directory containing reconstructed conversation records.
        :param report_path: File path to save the final validation report (e.g. 'validation_report.json').
        """
        self.input_dir = os.path.abspath(input_dir)
        self.report_path = os.path.abspath(report_path)

    def _is_valid_iso_timestamp(self, ts_str: str) -> bool:
        """
        Checks if a string is a valid ISO 8601 UTC timestamp.
        """
        if not ts_str:
            return False
        # Strip trailing Z
        if ts_str.endswith('Z'):
            ts_str = ts_str[:-1] + '+00:00'
        try:
            datetime.fromisoformat(ts_str)
            return True
        except ValueError:
            return False

    def validate_conversation(self, file_path: str) -> Tuple[List[str], List[str]]:
        """
        Validates a single conversation file.
        Returns a tuple of (errors, warnings).
        """
        errors = []
        warnings = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            errors.append(f"Failed to parse JSON file: {e}")
            return errors, warnings

        # 1. Check top-level fields
        required_fields = ["conversation_id", "source", "start_timestamp", "end_timestamp", "messages"]
        for field in required_fields:
            if field not in data:
                errors.append(f"Missing top-level field: '{field}'")
                
        if errors:
            # If basic schema is broken, return immediately
            return errors, warnings

        conv_id = data["conversation_id"]
        messages = data.get("messages", [])
        
        if not messages:
            warnings.append("Conversation thread contains no messages.")
            return errors, warnings

        # 2. Check each message
        prev_time = None
        consecutive_user = 0
        consecutive_assistant = 0
        
        for idx, msg in enumerate(messages):
            msg_desc = f"message[{idx}] (ID: {msg.get('message_id', 'unknown')})"
            
            # Check fields
            if "message_id" not in msg or not msg["message_id"]:
                errors.append(f"{msg_desc} is missing 'message_id'")
            if "timestamp" not in msg:
                errors.append(f"{msg_desc} is missing 'timestamp'")
            else:
                ts = msg["timestamp"]
                if not self._is_valid_iso_timestamp(ts):
                    errors.append(f"{msg_desc} has invalid ISO timestamp: '{ts}'")
                else:
                    curr_time = msg["timestamp"]
                    if prev_time and curr_time < prev_time:
                        errors.append(f"{msg_desc} has timestamp '{curr_time}' preceding previous message timestamp '{prev_time}'")
                    prev_time = curr_time

            # Check speaker role
            speaker = msg.get("speaker", "")
            if not speaker:
                errors.append(f"{msg_desc} is missing 'speaker'")
            elif speaker not in ["user", "assistant"]:
                errors.append(f"{msg_desc} has invalid speaker: '{speaker}' (must be 'user' or 'assistant')")
            else:
                # Count consecutive speakers
                if speaker == "user":
                    consecutive_user += 1
                    consecutive_assistant = 0
                else:
                    consecutive_assistant += 1
                    consecutive_user = 0
                    
                if consecutive_user > 3:
                    warnings.append(f"User sent {consecutive_user} consecutive messages without assistant reply (around idx {idx})")
                if consecutive_assistant > 3:
                    warnings.append(f"Assistant sent {consecutive_assistant} consecutive messages without user input (around idx {idx})")

            # Check text body
            text = msg.get("text", "")
            if "text" not in msg:
                errors.append(f"{msg_desc} is missing 'text'")
            elif not isinstance(text, str) or not text.strip():
                errors.append(f"{msg_desc} text body is empty or whitespace-only")
                
        return errors, warnings

    def validate_all(self) -> Dict[str, Any]:
        """
        Validates all conversation files and writes validation_report.json.
        """
        report_data = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "stats": {
                "total_files_checked": 0,
                "total_errors": 0,
                "total_warnings": 0,
                "status": "PASS"
            },
            "failures": []
        }
        
        if not os.path.exists(self.input_dir):
            return report_data
            
        total_errors = 0
        total_warnings = 0
        total_files = 0
        
        for filename in os.listdir(self.input_dir):
            if filename.endswith(".json"):
                total_files += 1
                file_path = os.path.join(self.input_dir, filename)
                errors, warnings = self.validate_conversation(file_path)
                
                if errors or warnings:
                    # Get conversation ID from filename if JSON loading failed
                    conv_id = filename.split('.')[0]
                    
                    report_data["failures"].append({
                        "conversation_id": conv_id,
                        "file": filename,
                        "errors": errors,
                        "warnings": warnings
                    })
                    total_errors += len(errors)
                    total_warnings += len(warnings)
                    
        report_data["stats"]["total_files_checked"] = total_files
        report_data["stats"]["total_errors"] = total_errors
        report_data["stats"]["total_warnings"] = total_warnings
        report_data["stats"]["status"] = "FAIL" if total_errors > 0 else "PASS"
        
        # Ensure target dir for report exists
        report_dir = os.path.dirname(self.report_path)
        if report_dir:
            os.makedirs(report_dir, exist_ok=True)
            
        with open(self.report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
            
        return report_data
