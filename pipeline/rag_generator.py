import os
import json
import re
import logging
from typing import Dict, Any, List

logger = logging.getLogger("etl_pipeline.rag_generator")

class RAGGenerator:
    def __init__(
        self,
        input_dir: str,
        output_dir: str,
        chunk_size_turns: int = 4,
        chunk_overlap_turns: int = 2,
        rag_filename: str = "rag_chunks.jsonl"
    ):
        """
        Initialize RAGGenerator.
        :param input_dir: Directory containing anonymized conversation records (normalized/anonymized/).
        :param output_dir: Directory to save the final RAG chunks (datasets/).
        :param chunk_size_turns: Number of message turns in each semantic chunk.
        :param chunk_overlap_turns: Overlap turns between consecutive chunks.
        :param rag_filename: Target filename for RAG chunks JSONL.
        """
        self.input_dir = os.path.abspath(input_dir)
        self.output_dir = os.path.abspath(output_dir)
        self.chunk_size_turns = chunk_size_turns
        self.chunk_overlap_turns = chunk_overlap_turns
        self.rag_filename = rag_filename
        os.makedirs(self.output_dir, exist_ok=True)

        if self.chunk_size_turns <= self.chunk_overlap_turns:
            raise ValueError("chunk_size_turns must be strictly greater than chunk_overlap_turns.")

    def load_conversations(self) -> List[Dict[str, Any]]:
        conversations = []
        if not os.path.exists(self.input_dir):
            return conversations
        for filename in sorted(os.listdir(self.input_dir)):
            if filename.endswith(".json"):
                path = os.path.join(self.input_dir, filename)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        conversations.append(data)
                except Exception as e:
                    logger.error(f"Failed to load conversation file {filename}: {e}")
        return conversations

    def chunk_conversation(self, conv: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Splits dialogue turns into chunks using a sliding window.
        """
        chunks = []
        messages = conv.get("messages", [])
        if not messages:
            return chunks

        conv_id = conv.get("conversation_id", "unknown")
        source = conv.get("source", "unknown")
        
        step = self.chunk_size_turns - self.chunk_overlap_turns
        chunk_idx = 0
        i = 0
        
        while i < len(messages):
            # Capture the subset slice of message objects
            window = messages[i : i + self.chunk_size_turns]
            
            # Format clean concatenated dialogue lines
            dialogue_lines = []
            for msg in window:
                speaker = msg.get("speaker", "user").capitalize()
                text = msg.get("text", "")
                dialogue_lines.append(f"{speaker}: {text}")
            content = "\n".join(dialogue_lines)
            
            start_msg_id = window[0].get("message_id", "")
            end_msg_id = window[-1].get("message_id", "")
            
            chunks.append({
                "chunk_id": f"{conv_id}_chunk_{chunk_idx}",
                "conversation_id": conv_id,
                "type": "conversation_segment",
                "content": content,
                "metadata": {
                    "source": source,
                    "message_range": [i, i + len(window) - 1],
                    "start_message_id": start_msg_id,
                    "end_message_id": end_msg_id
                }
            })
            
            chunk_idx += 1
            # Move the window
            i += step
            
            # If the remaining messages are smaller than the step size, we break to avoid duplicates
            if i >= len(messages) and len(window) < self.chunk_size_turns:
                break
                
        return chunks

    def extract_knowledge_nuggets(self, conv: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Rule-based knowledge extractor pulling facts from anonymized text tokens.
        """
        facts = []
        messages = conv.get("messages", [])
        if not messages:
            return facts

        conv_id = conv.get("conversation_id", "unknown")
        source = conv.get("source", "unknown")
        fact_idx = 0
        
        for msg in messages:
            text = msg.get("text", "")
            
            # 1. Check for order number references
            order_match = re.search(r'#(\d+)', text)
            if order_match:
                order_num = order_match.group(1)
                facts.append({
                    "chunk_id": f"{conv_id}_fact_{fact_idx}",
                    "conversation_id": conv_id,
                    "type": "knowledge_fact",
                    "content": f"Customer reference number / Order ID associated with this query is '#{order_num}'.",
                    "metadata": {
                        "source": source,
                        "reference_type": "order_id"
                    }
                })
                fact_idx += 1
                
            # 2. Check for anonymized address PII
            if "[ADDRESS]" in text:
                facts.append({
                    "chunk_id": f"{conv_id}_fact_{fact_idx}",
                    "conversation_id": conv_id,
                    "type": "knowledge_fact",
                    "content": f"Customer requested shipping or transaction address reference as '[ADDRESS]'.",
                    "metadata": {
                        "source": source,
                        "reference_type": "address"
                    }
                })
                fact_idx += 1
                
            # 3. Check for anonymized email PII
            if "[EMAIL]" in text:
                facts.append({
                    "chunk_id": f"{conv_id}_fact_{fact_idx}",
                    "conversation_id": conv_id,
                    "type": "knowledge_fact",
                    "content": f"Customer verified primary contact email address as '[EMAIL]'.",
                    "metadata": {
                        "source": source,
                        "reference_type": "email"
                    }
                })
                fact_idx += 1

            # 4. Check for anonymized phone PII
            if "[PHONE]" in text:
                facts.append({
                    "chunk_id": f"{conv_id}_fact_{fact_idx}",
                    "conversation_id": conv_id,
                    "type": "knowledge_fact",
                    "content": f"Customer verified primary contact phone number as '[PHONE]'.",
                    "metadata": {
                        "source": source,
                        "reference_type": "phone"
                    }
                })
                fact_idx += 1

            # 5. Check for credentials PII
            if "[PASSWORD]" in text:
                facts.append({
                    "chunk_id": f"{conv_id}_fact_{fact_idx}",
                    "conversation_id": conv_id,
                    "type": "knowledge_fact",
                    "content": f"Security credentials or password verification was logged as '[PASSWORD]'.",
                    "metadata": {
                        "source": source,
                        "reference_type": "credentials"
                    }
                })
                fact_idx += 1
                
        return facts

    def process_all(self) -> Dict[str, int]:
        conversations = self.load_conversations()
        
        output_path = os.path.join(self.output_dir, self.rag_filename)
        if os.path.exists(output_path):
            os.remove(output_path)
            
        counts = {
            "conversations_processed": 0,
            "segments_generated": 0,
            "facts_extracted": 0,
            "total_chunks_written": 0
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            for conv in conversations:
                # 1. Sliding window chunking
                segments = self.chunk_conversation(conv)
                counts["segments_generated"] += len(segments)
                
                # 2. Fact extraction
                facts = self.extract_knowledge_nuggets(conv)
                counts["facts_extracted"] += len(facts)
                
                # Write segments
                for chunk in segments:
                    f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                    counts["total_chunks_written"] += 1
                    
                # Write facts
                for chunk in facts:
                    f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                    counts["total_chunks_written"] += 1
                    
                counts["conversations_processed"] += 1
                
        return counts
