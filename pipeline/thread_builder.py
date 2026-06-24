import os
import json
from datetime import datetime, timezone
from typing import Dict, Any, List

class ThreadBuilder:
    def __init__(self, input_dir: str, output_dir: str, gap_threshold_seconds: int = 86400):
        """
        Initialize ThreadBuilder.
        :param input_dir: Directory containing unified conversation records.
        :param output_dir: Directory to save reconstructed conversation sessions.
        :param gap_threshold_seconds: Time gap in seconds to split conversations (default 24 hours).
        """
        self.input_dir = os.path.abspath(input_dir)
        self.output_dir = os.path.abspath(output_dir)
        self.gap_threshold_seconds = gap_threshold_seconds
        os.makedirs(self.output_dir, exist_ok=True)

    def _parse_iso_timestamp(self, ts_str: str) -> datetime:
        """
        Parses ISO 8601 UTC timestamp string (e.g. YYYY-MM-DDTHH:MM:SSZ) to timezone-aware datetime.
        """
        # Convert trailing Z to +00:00 to support fromisoformat in Python < 3.11
        if ts_str.endswith('Z'):
            ts_str = ts_str[:-1] + '+00:00'
        return datetime.fromisoformat(ts_str)

    def process_conversation(self, file_path: str) -> List[str]:
        """
        Processes a single unified conversation file, splits it by inactivity gap,
        and saves separate session logs.
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            conv_data = json.load(f)
            
        orig_id = conv_data["conversation_id"]
        source = conv_data["source"]
        messages = conv_data.get("messages", [])
        
        if not messages:
            # Empty conversation, just save as-is
            out_path = os.path.join(self.output_dir, f"{orig_id}.json")
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(conv_data, f, indent=2, ensure_ascii=False)
            return [out_path]

        # Ensure messages are sorted chronologically
        messages.sort(key=lambda m: m.get("timestamp", ""))
        
        sessions: List[List[Dict[str, Any]]] = []
        current_session: List[Dict[str, Any]] = [messages[0]]
        
        for i in range(1, len(messages)):
            prev_msg = messages[i - 1]
            curr_msg = messages[i]
            
            try:
                prev_time = self._parse_iso_timestamp(prev_msg.get("timestamp", ""))
                curr_time = self._parse_iso_timestamp(curr_msg.get("timestamp", ""))
                time_gap = (curr_time - prev_time).total_seconds()
            except Exception:
                # If date parsing fails, do not split
                time_gap = 0
                
            if time_gap > self.gap_threshold_seconds:
                # Split and start new session
                sessions.append(current_session)
                current_session = [curr_msg]
            else:
                current_session.append(curr_msg)
                
        sessions.append(current_session)
        
        saved_paths = []
        for idx, session_messages in enumerate(sessions):
            # If split into multiple parts, name them conv_id_session_0, etc.
            # If only one session, we can name it conv_id_session_0 as well to maintain consistency.
            session_id = f"{orig_id}_session_{idx}"
            
            start_ts = session_messages[0].get("timestamp", "")
            end_ts = session_messages[-1].get("timestamp", "")
            
            # Update conversation_id reference within each message
            clean_session_messages = []
            for msg in session_messages:
                msg_copy = msg.copy()
                # If there's no conversation_id, set it. Otherwise update it.
                msg_copy["conversation_id"] = session_id
                clean_session_messages.append(msg_copy)
                
            session_conv = {
                "conversation_id": session_id,
                "source": source,
                "start_timestamp": start_ts,
                "end_timestamp": end_ts,
                "messages": clean_session_messages,
                "metadata": {
                    "total_messages": len(session_messages),
                    "original_conversation_id": orig_id,
                    "session_index": idx,
                    "total_sessions": len(sessions)
                }
            }
            
            out_path = os.path.join(self.output_dir, f"{session_id}.json")
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(session_conv, f, indent=2, ensure_ascii=False)
            saved_paths.append(out_path)
            
        return saved_paths

    def process_all(self) -> List[str]:
        output_files = []
        if not os.path.exists(self.input_dir):
            return output_files
        for filename in os.listdir(self.input_dir):
            if filename.endswith(".json"):
                file_path = os.path.join(self.input_dir, filename)
                output_files.extend(self.process_conversation(file_path))
        return output_files
