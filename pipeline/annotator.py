import os
import json
import re
import logging
import urllib.request
import urllib.error
from typing import Dict, Any, List

logger = logging.getLogger("etl_pipeline.annotator")

class ConversationAnnotator:
    def __init__(
        self,
        input_dir: str,
        output_dir: str,
        api_key_env: str = "GROQ_API_KEY",
        model: str = "llama-3.1-8b-instant",
        intent_filename: str = "intent_labels.jsonl",
        sentiment_filename: str = "sentiment_labels.jsonl",
        summary_filename: str = "summaries.jsonl"
    ):
        """
        Initialize ConversationAnnotator.
        :param input_dir: Directory containing anonymized conversation records (normalized/anonymized/).
        :param output_dir: Directory to save the final labels/datasets (datasets/).
        :param api_key_env: Environment variable name for the Groq API key.
        :param model: Groq model to use for completion.
        :param intent_filename: Target filename for intent labels JSONL.
        :param sentiment_filename: Target filename for sentiment labels JSONL.
        :param summary_filename: Target filename for summaries JSONL.
        """
        self.input_dir = os.path.abspath(input_dir)
        self.output_dir = os.path.abspath(output_dir)
        self.api_key_env = api_key_env
        self.model = model
        self.intent_filename = intent_filename
        self.sentiment_filename = sentiment_filename
        self.summary_filename = summary_filename
        os.makedirs(self.output_dir, exist_ok=True)

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

    def call_groq_api(self, conversation_text: str) -> Dict[str, Any]:
        """
        Performs direct HTTP request to the Groq API using urllib.
        """
        api_key = os.environ.get(self.api_key_env, "").strip()
        if not api_key:
            raise ValueError("Groq API key not found in environment.")

        url = "https://api.groq.com/openai/v1/chat/completions"
        
        system_instruction = (
            "You are a structured data extraction assistant. "
            "Analyze the conversation and output ONLY valid JSON matching this schema: "
            "{\n"
            '  "intents": [\n'
            '    {"message_id": "string", "label": "billing_inquiry|order_status|general_greeting|technical_support|provide_information|execute_action|request_details|other"}\n'
            "  ],\n"
            '  "sentiments": [\n'
            '    {"message_id": "string", "label": "positive|neutral|negative", "score": float}\n'
            "  ],\n"
            '  "summary": {\n'
            '    "issue": "string",\n'
            '    "resolution": "string"\n'
            "  }\n"
            "}"
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": f"Conversation Log:\n{conversation_text}"}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.0
        }

        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=req_data,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            },
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                res_body = response.read().decode("utf-8")
                res_json = json.loads(res_body)
                content = res_json["choices"][0]["message"]["content"]
                return json.loads(content)
        except Exception as e:
            logger.warning(f"Groq API call failed: {e}. Falling back to rule-based annotator.")
            raise e

    def format_conversation_text(self, conv: Dict[str, Any]) -> str:
        lines = []
        for msg in conv.get("messages", []):
            role = msg.get("speaker", "user").upper()
            text = msg.get("text", "")
            msg_id = msg.get("message_id", "")
            lines.append(f"[{msg_id}] {role}: {text}")
        return "\n".join(lines)

    def fallback_annotate(self, conv: Dict[str, Any]) -> Dict[str, Any]:
        """
        Rule-based classifier for fallback.
        """
        intents = []
        sentiments = []
        
        # Word dictionaries for sentiment
        pos_words = {"thanks", "thank", "great", "good", "perfect", "awesome", "👍", "love", "solved", "fixed"}
        neg_words = {"issue", "wrong", "error", "fail", "not", "delay", "double", "broken", "damaged", "wait", "charge"}

        for msg in conv.get("messages", []):
            msg_id = msg.get("message_id", "")
            speaker = msg.get("speaker", "user").lower()
            text = msg.get("text", "")
            text_lower = text.lower()

            # Rule-based Intent/Action classification
            if speaker == "user":
                if any(w in text_lower for w in ["billing", "charge", "invoice", "fee", "pay", "refund", "cost", "price"]):
                    label = "billing_inquiry"
                elif any(w in text_lower for w in ["order", "track", "ship", "deliver", "status", "cancel"]):
                    label = "order_status"
                elif any(w in text_lower for w in ["hi", "hello", "hey", "helpline"]):
                    label = "general_greeting"
                else:
                    label = "technical_support"
            else:
                # Assistant Actions
                if any(w in text_lower for w in ["refund", "update", "ship", "sent", "change", "address"]):
                    label = "execute_action"
                elif any(w in text_lower for w in ["what", "how", "provide", "verify", "password", "details"]):
                    label = "request_details"
                else:
                    label = "provide_information"

            intents.append({
                "message_id": msg_id,
                "label": label
            })

            # Rule-based Sentiment analysis
            words = re.findall(r"\b\w+\b", text_lower)
            pos_count = sum(1 for w in words if w in pos_words) + ("👍" in text_lower)
            neg_count = sum(1 for w in words if w in neg_words)

            if pos_count > neg_count:
                sentiment = "positive"
                score = 0.8
            elif neg_count > pos_count:
                sentiment = "negative"
                score = 0.8
            else:
                sentiment = "neutral"
                score = 0.5

            sentiments.append({
                "message_id": msg_id,
                "label": sentiment,
                "score": score
            })

        # Rule-based Summary construction
        all_text = " ".join([m.get("text", "") for m in conv.get("messages", [])]).lower()
        
        # Simple extraction rules
        issue = "Customer query/inquiry regarding services."
        if "billing" in all_text or "charge" in all_text:
            issue = "Customer raised billing inquiry regarding incorrect/double charge."
        elif "order" in all_text or "track" in all_text:
            issue = "Customer requested order status or shipping details update."

        resolution = "Agent provided assistance."
        if "execute_action" in [i["label"] for i in intents]:
            resolution = "Agent executed customer request successfully."
        elif "request_details" in [i["label"] for i in intents]:
            resolution = "Agent requested details to verify identity/account."

        summary = {
            "issue": issue,
            "resolution": resolution
        }

        return {
            "intents": intents,
            "sentiments": sentiments,
            "summary": summary
        }

    def process_all(self) -> Dict[str, int]:
        conversations = self.load_conversations()
        
        intent_path = os.path.join(self.output_dir, self.intent_filename)
        sentiment_path = os.path.join(self.output_dir, self.sentiment_filename)
        summary_path = os.path.join(self.output_dir, self.summary_filename)

        # Clear existing output files if they exist
        for path in [intent_path, sentiment_path, summary_path]:
            if os.path.exists(path):
                os.remove(path)

        api_key = os.environ.get(self.api_key_env, "").strip()
        
        counts = {
            "conversations_processed": 0,
            "intent_labels_written": 0,
            "sentiment_labels_written": 0,
            "summaries_written": 0,
            "llm_calls_succeeded": 0,
            "fallbacks_executed": 0
        }

        with open(intent_path, 'w', encoding='utf-8') as f_intent, \
             open(sentiment_path, 'w', encoding='utf-8') as f_sent, \
             open(summary_path, 'w', encoding='utf-8') as f_sum:
             
            for conv in conversations:
                conv_id = conv.get("conversation_id", "unknown")
                conv_text = self.format_conversation_text(conv)
                
                annotations = None
                if api_key:
                    try:
                        annotations = self.call_groq_api(conv_text)
                        counts["llm_calls_succeeded"] += 1
                        logger.info(f"Successfully annotated conversation '{conv_id}' using Groq LLM.")
                    except Exception:
                        pass
                        
                if not annotations:
                    annotations = self.fallback_annotate(conv)
                    counts["fallbacks_executed"] += 1
                    logger.info(f"Annotated conversation '{conv_id}' using offline fallback classifier.")

                # Write intents
                for item in annotations.get("intents", []):
                    f_intent.write(json.dumps({
                        "conversation_id": conv_id,
                        "message_id": item["message_id"],
                        "label": item["label"]
                    }, ensure_ascii=False) + "\n")
                    counts["intent_labels_written"] += 1

                # Write sentiments
                for item in annotations.get("sentiments", []):
                    f_sent.write(json.dumps({
                        "conversation_id": conv_id,
                        "message_id": item["message_id"],
                        "sentiment": item["label"],
                        "score": item.get("score", 1.0)
                    }, ensure_ascii=False) + "\n")
                    counts["sentiment_labels_written"] += 1

                # Write summary
                sum_obj = annotations.get("summary", {})
                f_sum.write(json.dumps({
                    "conversation_id": conv_id,
                    "summary": {
                        "issue": sum_obj.get("issue", ""),
                        "resolution": sum_obj.get("resolution", "")
                    }
                }, ensure_ascii=False) + "\n")
                counts["summaries_written"] += 1
                
                counts["conversations_processed"] += 1

        return counts
