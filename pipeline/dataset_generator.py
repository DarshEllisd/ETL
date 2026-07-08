import os
import json
from datetime import datetime, timezone
import re
from typing import Dict, Any, List, Set

class DatasetGenerator:
    def __init__(
        self,
        input_dir: str,
        output_dir: str,
        version: str = "1.0.0",
        system_prompt: str = None,
        approved_path: str = None
    ):
        """
        Initialize DatasetGenerator.
        :param input_dir: Directory containing anonymized conversation records (usually 'normalized/anonymized/').
        :param output_dir: Directory to save the final dataset artifacts (usually 'datasets/').
        :param version: Version string for the generated dataset (e.g. '1.0.0').
        :param system_prompt: Optional system prompt to prepend to every message history list.
        :param approved_path: Optional path to approved.json whitelist file.
        """
        self.input_dir = os.path.abspath(input_dir)
        self.output_dir = os.path.abspath(output_dir)
        self.version = version
        self.system_prompt = system_prompt
        self.approved_path = approved_path
        os.makedirs(self.output_dir, exist_ok=True)

    def load_conversations(self) -> List[Dict[str, Any]]:
        """
        Load all conversation JSON files from the input directory.
        """
        conversations = []
        if not os.path.exists(self.input_dir):
            return conversations
            
        approved = []
        if self.approved_path and os.path.exists(self.approved_path):
            try:
                with open(self.approved_path, 'r', encoding='utf-8') as f:
                    approved = json.load(f)
            except Exception:
                pass

        exclusions = []
        if os.path.exists("exclusions.json"):
            try:
                with open("exclusions.json", 'r', encoding='utf-8') as f:
                    exclusions = json.load(f)
            except Exception:
                pass

        for filename in sorted(os.listdir(self.input_dir)):
            if filename.endswith(".json"):
                path = os.path.join(self.input_dir, filename)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        conv_id = data.get("conversation_id")
                        if conv_id:
                            if conv_id in exclusions:
                                continue
                            if self.approved_path and os.path.exists(self.approved_path) and conv_id not in approved:
                                continue
                        conversations.append(data)
                except Exception as e:
                    # Ignore corrupted or invalid JSON files
                    pass
        return conversations

    def generate_jsonl(self, filename: str = "conversations.jsonl") -> str:
        """
        Generates the conversations.jsonl dataset in standard OpenAI Chat format.
        """
        conversations = self.load_conversations()
        output_path = os.path.join(self.output_dir, filename)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            for conv in conversations:
                conv_id = conv.get("conversation_id", "unknown")
                messages = conv.get("messages", [])
                if not messages:
                    continue
                    
                formatted_messages = []
                if self.system_prompt:
                    formatted_messages.append({
                        "role": "system",
                        "content": self.system_prompt
                    })
                    
                for msg in messages:
                    role = msg.get("speaker", "user")
                    # Map speaker to standard openai chat roles
                    if role not in ["user", "assistant", "system"]:
                        role = "user" # default fallback
                    formatted_messages.append({
                        "role": role,
                        "content": msg.get("text", "")
                    })
                    
                payload = {
                    "conversation_id": conv_id,
                    "messages": formatted_messages
                }
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
                
        return output_path

    def generate_metadata(self, filename: str = "metadata.json") -> str:
        """
        Generates version and aggregate PII metadata metrics file.
        """
        conversations = self.load_conversations()
        output_path = os.path.join(self.output_dir, filename)
        
        total_convs = len(conversations)
        total_msgs = 0
        source_distribution = {}
        
        # PII aggregates
        pii_totals = {
            "emails_scrubbed": 0,
            "phones_scrubbed": 0,
            "passwords_scrubbed": 0,
            "addresses_scrubbed": 0,
            "names_scrubbed": 0
        }
        
        for conv in conversations:
            source = conv.get("source", "unknown")
            source_distribution[source] = source_distribution.get(source, 0) + 1
            total_msgs += len(conv.get("messages", []))
            
            # Sum up scrub metadata if present
            meta = conv.get("metadata", {})
            pii_totals["emails_scrubbed"] += meta.get("pii_emails_scrubbed", 0)
            pii_totals["phones_scrubbed"] += meta.get("pii_phones_scrubbed", 0)
            pii_totals["passwords_scrubbed"] += meta.get("pii_passwords_scrubbed", 0)
            pii_totals["addresses_scrubbed"] += meta.get("pii_addresses_scrubbed", 0)
            pii_totals["names_scrubbed"] += meta.get("pii_names_scrubbed", 0)
            
        metadata = {
            "version": self.version,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total_conversations": total_convs,
            "total_messages": total_msgs,
            "source_distribution": source_distribution,
            "anonymization_summary": pii_totals
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
            
        return output_path

    def generate_statistics(self, filename: str = "statistics.json") -> str:
        """
        Generates dataset statistics and diagnostics file.
        """
        conversations = self.load_conversations()
        output_path = os.path.join(self.output_dir, filename)
        
        conv_lengths = []
        msg_char_lengths = []
        msg_word_counts = []
        speaker_counts = {}
        unique_words = set()
        
        for conv in conversations:
            messages = conv.get("messages", [])
            conv_lengths.append(len(messages))
            
            for msg in messages:
                text = msg.get("text", "")
                msg_char_lengths.append(len(text))
                
                # Simple word splitting (strip punctuation for words)
                words = re.findall(r"\b\w+\b", text.lower())
                msg_word_counts.append(len(words))
                unique_words.update(words)
                
                speaker = msg.get("speaker", "user")
                speaker_counts[speaker] = speaker_counts.get(speaker, 0) + 1
                
        total_msgs = len(msg_char_lengths)
        total_convs = len(conv_lengths)
        
        # Calculate summaries safely
        def get_stats(data: List[int]) -> Dict[str, Any]:
            if not data:
                return {"min": 0, "max": 0, "average": 0.0}
            return {
                "min": min(data),
                "max": max(data),
                "average": round(sum(data) / len(data), 2)
            }
            
        conv_len_stats = get_stats(conv_lengths)
        char_len_stats = get_stats(msg_char_lengths)
        word_count_stats = get_stats(msg_word_counts)
        
        # Calculate speaker ratios
        speaker_ratios = {}
        if total_msgs > 0:
            for speaker, count in speaker_counts.items():
                speaker_ratios[speaker] = round(count / total_msgs, 4)
                
        # Total words
        total_words = sum(msg_word_counts)
        # Token estimation (1 word = 1.3 tokens)
        estimated_tokens = int(round(total_words * 1.3))
        
        stats_data = {
            "conversation_count": total_convs,
            "message_count": total_msgs,
            "conversation_length_stats": conv_len_stats,
            "message_char_length_stats": char_len_stats,
            "message_word_count_stats": word_count_stats,
            "speaker_ratios": speaker_ratios,
            "vocabulary_size": len(unique_words),
            "estimated_total_tokens": estimated_tokens
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(stats_data, f, indent=2, ensure_ascii=False)
            
        return output_path

    def run_all(self) -> Dict[str, str]:
        """
        Executes all generation steps.
        """
        jsonl_path = self.generate_jsonl()
        meta_path = self.generate_metadata()
        stats_path = self.generate_statistics()
        
        return {
            "jsonl": jsonl_path,
            "metadata": meta_path,
            "statistics": stats_path
        }
