import os
import json
import re
import time
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
        summary_filename: str = "summaries.jsonl",
        languages_filename: str = "languages.jsonl",
        approved_path: str = None
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
        :param languages_filename: Target filename for language annotations JSONL.
        :param approved_path: Optional path to approved.json whitelist file.
        """
        self.input_dir = os.path.abspath(input_dir)
        self.output_dir = os.path.abspath(output_dir)
        self.api_key_env = api_key_env
        self.model = model
        self.intent_filename = intent_filename
        self.sentiment_filename = sentiment_filename
        self.summary_filename = summary_filename
        self.languages_filename = languages_filename
        self.approved_path = approved_path
        os.makedirs(self.output_dir, exist_ok=True)

    def load_conversations(self) -> List[Dict[str, Any]]:
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
                    logger.error(f"Failed to load conversation file {filename}: {e}")
        return conversations

    def get_api_key(self) -> str:
        if os.environ.get("ETL_TESTING") == "true":
            return ""
        api_key = os.environ.get(self.api_key_env, "").strip()
        if not api_key:
            # Try to read .env from project root (one level up from pipeline/)
            env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
            if os.path.exists(env_path):
                content = ""
                try:
                    with open(env_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                except UnicodeDecodeError:
                    try:
                        with open(env_path, 'r', encoding='utf-16') as f:
                            content = f.read()
                    except Exception:
                        pass
                except Exception:
                    pass
                
                if content:
                    for line in content.splitlines():
                        if line.strip() and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            if k.strip() == self.api_key_env:
                                api_key = v.strip().strip('"').strip("'")
                                break
        return api_key

    def call_groq_api(self, batch_conversations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Performs direct HTTP request to the Groq API using urllib, passing a batch of conversations.
        """
        api_key = self.get_api_key()
        if not api_key:
            raise ValueError("Groq API key not found in environment or .env file.")

        url = "https://api.groq.com/openai/v1/chat/completions"
        
        system_instruction = (
            "You are a structured data extraction assistant. "
            "Analyze the batch of conversations and output ONLY valid JSON matching this schema:\n"
            "{\n"
            '  "conversations": [\n'
            "    {\n"
            '      "conversation_id": "string",\n'
            '      "intents": [\n'
            '        {"message_id": "string", "label": "billing_inquiry|order_status|general_greeting|technical_support|provide_information|execute_action|request_details|other"}\n'
            '      ],\n'
            '      "sentiments": [\n'
            '        {"message_id": "string", "label": "positive|neutral|negative", "score": float}\n'
            '      ],\n'
            '      "summary": {\n'
            '        "issue": "string",\n'
            '        "resolution": "string"\n'
            '      },\n'
            '      "detected_languages": [\n'
            '        {"message_id": "string", "languages": ["string"]}\n'
            '      ]\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            "Guidelines for detected_languages:\n"
            "- For each message in each conversation, list its detected languages in standard 'code - Proper Name' format (e.g., 'en - English', 'hi - Hindi', 'ta - Tamil', 'te - Telugu', 'ur - Urdu', 'gu - Gujarati', 'mr - Marathi').\n"
            "- If Hinglish (Hindi written in Roman/English script or mixed with English) is used in a message, classify its languages as BOTH ['hi - Hindi', 'en - English'].\n"
            "- If Tamil (Unicode or Romanized script) is used in a message, detect it as 'ta - Tamil'.\n"
            "- If you do not recognize the language or cannot identify it, classify it as 'no lang found - No Language Found'.\n"
            "- A message containing pure English words must only be labeled as ['en - English']."
        )

        prompt_lines = []
        for conv in batch_conversations:
            conv_id = conv.get("conversation_id", "unknown")
            prompt_lines.append(f"=== START OF CONVERSATION: {conv_id} ===")
            prompt_lines.append(self.format_conversation_text(conv))
            prompt_lines.append(f"=== END OF CONVERSATION: {conv_id} ===\n")
            
        user_content = "\n".join(prompt_lines)

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_content}
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

        max_retries = 5
        backoff = 5.0
        for attempt in range(max_retries):
            try:
                # Add delay between calls to stay below 30 RPM
                time.sleep(2.2)
                with urllib.request.urlopen(req, timeout=30) as response:
                    res_body = response.read().decode("utf-8")
                    res_json = json.loads(res_body)
                    content = res_json["choices"][0]["message"]["content"]
                    parsed = json.loads(content)
                    
                    # Sleep proportionally to tokens consumed to stay below 6k TPM
                    usage = res_json.get("usage", {})
                    total_tokens = usage.get("total_tokens", 1500)
                    sleep_time = max(2.2, (total_tokens / 6000.0) * 60.0)
                    logger.info(f"Groq API call consumed {total_tokens} tokens. Spacing next call by sleeping {sleep_time:.2f}s...")
                    time.sleep(sleep_time)
                    
                    return parsed.get("conversations", [])
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < max_retries - 1:
                    retry_after = e.headers.get("retry-after") or e.headers.get("Retry-After")
                    if retry_after:
                        try:
                            sleep_time = float(retry_after) + 0.5
                        except Exception:
                            sleep_time = 60.0
                    else:
                        sleep_time = 60.0
                    logger.warning(f"Groq API 429 Rate Limit hit. Retrying in {sleep_time}s...")
                    time.sleep(sleep_time)
                    backoff *= 2
                    continue
                logger.warning(f"Groq API batch call failed: {e}. Falling back to rule-based annotator.")
                raise e
            except Exception as e:
                logger.warning(f"Groq API batch call failed: {e}. Falling back to rule-based annotator.")
                raise e
        raise ValueError("Failed to get response after retries")

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

        # Offline language identification
        detected_languages = []
        
        # Hinglish Roman script keywords (removed ambiguous short words: me, h, se, ne, aa, ab, ko)
        hinglish_words = {
            "nai", "rahe", "khelna", "abhi", "bhi", "toh", "karo", "kro", "rha", "raha", "meri", "mera", 
            "hai", "kya", "aur", "aap", "aaj", "aao", "jao", "kar", "lekin", "isme", "usse",
            "haan", "nahi", "accha", "theek", "sahi", "galat", "samjha", "batao", "dekho", "chalo",
            "kaise", "kyun", "kahan", "kidhar", "kaisa", "kitna", "tumhara", "apna", "unka",
            "wala", "wali", "hoga", "hogi", "karenge", "karega", "karegi", "milega"
        }
        HINGLISH_MIN_MATCHES = 2
        
        # Romanized Tamil common keywords
        romanized_tamil_words = {
            "vanakkam", "enaku", "udhavi", "romba", "nandri", "kandippa", "panrom", "naanga", "vanga", "ponga", "iruku",
            "enna", "epdi", "pannunga", "theriyum", "theriyathu", "sollunga", "vaanga", "poanga"
        }
        
        # Romanized Gujarati keywords
        romanized_gujarati_words = {
            "kem", "chho", "majama", "tamne", "aabhar", "bhai", "bahen", "tamaru", "karo", "karjo",
            "shu", "haa", "tyare", "pachhi", "kem cho", "su", "tamaro"
        }
        
        # Romanized Marathi keywords
        romanized_marathi_words = {
            "namaskar", "kasa", "aahe", "tumhi", "mala", "dhanyavad", "kiti", "kaay",
            "honar", "aahes", "sagla", "mhanun", "kela", "keli", "tumcha", "amhi", "tyacha"
        }
        
        # English indicators (expanded)
        english_words = {
            "the", "and", "was", "were", "have", "has", "had", "been", "would", "could", "should",
            "with", "from", "that", "this", "they", "them", "their", "there", "about", "which",
            "will", "some", "told", "asked", "said", "because", "before", "after", "while",
            "office", "unprofessional", "mobile", "games", "against", "such", "things",
            "didn", "doesn", "don", "can", "help", "need", "want", "know", "think",
            "please", "thanks", "thank", "sorry", "okay", "hello", "work", "send", "sent"
        }

        for msg in conv.get("messages", []):
            msg_id = msg.get("message_id", "")
            text = msg.get("text", "")
            langs = set()
            
            # Check Tamil characters (Tamil Unicode block: \u0b80 - \u0bff)
            if any('\u0b80' <= c <= '\u0bff' for c in text):
                langs.add("ta - Tamil")
                
            # Check Devanagari characters (Devanagari Unicode block: \u0900 - \u097f) — Hindi/Marathi
            if any('\u0900' <= c <= '\u097f' for c in text):
                langs.add("hi - Hindi")
                
            # Check Gujarati characters (Gujarati Unicode block: \u0a80 - \u0aff)
            if any('\u0a80' <= c <= '\u0aff' for c in text):
                langs.add("gu - Gujarati")
                
            # Check Bengali characters (Bengali Unicode block: \u0980 - \u09ff)
            if any('\u0980' <= c <= '\u09ff' for c in text):
                langs.add("bn - Bengali")
                
            # Check Telugu characters (Telugu Unicode block: \u0c00 - \u0c7f)
            if any('\u0c00' <= c <= '\u0c7f' for c in text):
                langs.add("te - Telugu")
                
            # Check Kannada characters (Kannada Unicode block: \u0c80 - \u0cff)
            if any('\u0c80' <= c <= '\u0cff' for c in text):
                langs.add("kn - Kannada")
                
            # Check Malayalam characters (Malayalam Unicode block: \u0d00 - \u0d7f)
            if any('\u0d00' <= c <= '\u0d7f' for c in text):
                langs.add("ml - Malayalam")
            
            text_words = set(re.findall(r"\b\w+\b", text.lower()))
            
            # Require minimum 2 hinglish matches to avoid false positives
            if len(text_words.intersection(hinglish_words)) >= HINGLISH_MIN_MATCHES:
                langs.add("hi - Hindi")
            if text_words.intersection(romanized_tamil_words):
                langs.add("ta - Tamil")
            if text_words.intersection(romanized_gujarati_words):
                langs.add("gu - Gujarati")
            if text_words.intersection(romanized_marathi_words):
                langs.add("mr - Marathi")
                
            if not langs:
                has_non_ascii = any(ord(c) > 127 for c in text)
                if has_non_ascii:
                    langs.add("no lang found - No Language Found")
                else:
                    langs.add("en - English")
            elif text_words.intersection(english_words):
                langs.add("en - English")
                
            detected_languages.append({
                "message_id": msg_id,
                "languages": sorted(list(langs))
            })

        return {
            "intents": intents,
            "sentiments": sentiments,
            "summary": summary,
            "detected_languages": detected_languages
        }

    def process_all(self) -> Dict[str, int]:
        conversations = self.load_conversations()
        intent_path = os.path.join(self.output_dir, self.intent_filename)
        sentiment_path = os.path.join(self.output_dir, self.sentiment_filename)
        summary_path = os.path.join(self.output_dir, self.summary_filename)
        languages_path = os.path.join(self.output_dir, self.languages_filename)

        # 1. Load existing cached annotations
        cached_intents = {}
        cached_sentiments = {}
        cached_summaries = {}
        cached_languages = {}

        if os.path.exists(intent_path):
            try:
                with open(intent_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            item = json.loads(line)
                            cid = item.get("conversation_id")
                            if cid:
                                if cid not in cached_intents:
                                    cached_intents[cid] = []
                                cached_intents[cid].append(item)
            except Exception:
                pass

        if os.path.exists(sentiment_path):
            try:
                with open(sentiment_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            item = json.loads(line)
                            cid = item.get("conversation_id")
                            if cid:
                                if cid not in cached_sentiments:
                                    cached_sentiments[cid] = []
                                cached_sentiments[cid].append(item)
            except Exception:
                pass

        if os.path.exists(summary_path):
            try:
                with open(summary_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            item = json.loads(line)
                            cid = item.get("conversation_id")
                            if cid:
                                cached_summaries[cid] = item.get("summary")
            except Exception:
                pass

        if os.path.exists(languages_path):
            try:
                with open(languages_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            item = json.loads(line)
                            cid = item.get("conversation_id")
                            if cid:
                                cached_languages[cid] = item.get("detected_languages")
            except Exception:
                pass

        # Identify uncached or incomplete conversations
        uncached_conversations = []
        for conv in conversations:
            cid = conv.get("conversation_id")
            num_msgs = len(conv.get("messages", []))
            if (cid in cached_intents and len(cached_intents[cid]) == num_msgs and
                cid in cached_sentiments and len(cached_sentiments[cid]) == num_msgs and
                cid in cached_summaries and 
                cid in cached_languages and len(cached_languages[cid]) == num_msgs):
                continue
            uncached_conversations.append(conv)

        api_key = self.get_api_key()
        
        counts = {
            "conversations_processed": 0,
            "intent_labels_written": 0,
            "sentiment_labels_written": 0,
            "summaries_written": 0,
            "languages_written": 0,
            "llm_calls_succeeded": 0,
            "fallbacks_executed": 0
        }

        # Build batches (of at most 6 messages per batch) ONLY for uncached conversations
        batches = []
        current_batch = []
        current_msg_count = 0
        for conv in uncached_conversations:
            msg_count = len(conv.get("messages", []))
            if current_msg_count + msg_count > 6 and current_batch:
                batches.append(current_batch)
                current_batch = [conv]
                current_msg_count = msg_count
            else:
                current_batch.append(conv)
                current_msg_count += msg_count
        if current_batch:
            batches.append(current_batch)

        # Call the batch API and populate the cache maps
        for batch in batches:
            batch_annotations = {}
            if api_key:
                try:
                    results = self.call_groq_api(batch)
                    for item in results:
                        cid = item.get("conversation_id")
                        if cid:
                            batch_annotations[cid] = item
                    counts["llm_calls_succeeded"] += 1
                    logger.info(f"Successfully annotated batch of {len(batch)} conversation(s) using Groq LLM.")
                except Exception as e:
                    logger.warning(f"Groq API batch call failed: {e}. Falling back to offline annotator for this batch.")
            
            for conv in batch:
                conv_id = conv.get("conversation_id", "unknown")
                annotations = batch_annotations.get(conv_id)
                
                # Verify completeness of the annotations returned by LLM
                msg_ids = [m.get("message_id") for m in conv.get("messages", []) if m.get("message_id")]
                
                is_complete = False
                if annotations:
                    annotated_intent_msg_ids = {i.get("message_id") for i in annotations.get("intents", []) if i.get("message_id")}
                    annotated_lang_msg_ids = {l.get("message_id") for l in annotations.get("detected_languages", []) if l.get("message_id")}
                    if annotated_intent_msg_ids.issuperset(msg_ids) and annotated_lang_msg_ids.issuperset(msg_ids):
                        is_complete = True
                        
                if not is_complete:
                    annotations = self.fallback_annotate(conv)
                    counts["fallbacks_executed"] += 1
                    logger.info(f"Annotated conversation '{conv_id}' using offline fallback classifier.")

                # Write intents to cache
                cached_intents[conv_id] = []
                for item in annotations.get("intents", []):
                    cached_intents[conv_id].append({
                        "conversation_id": conv_id,
                        "message_id": item["message_id"],
                        "label": item["label"]
                    })

                # Write sentiments to cache
                cached_sentiments[conv_id] = []
                for item in annotations.get("sentiments", []):
                    cached_sentiments[conv_id].append({
                        "conversation_id": conv_id,
                        "message_id": item["message_id"],
                        "sentiment": item["label"],
                        "score": item.get("score", 1.0)
                    })

                # Write summary to cache
                sum_obj = annotations.get("summary", {})
                cached_summaries[conv_id] = {
                    "issue": sum_obj.get("issue", ""),
                    "resolution": sum_obj.get("resolution", "")
                }

                # Write languages to cache
                langs = annotations.get("detected_languages", [])
                if isinstance(langs, list):
                    all_dicts = True
                    for item in langs:
                        if not isinstance(item, dict):
                            all_dicts = False
                            break
                    if not all_dicts:
                        converted = []
                        for mid in msg_ids:
                            converted.append({
                                "message_id": mid,
                                "languages": langs
                            })
                        langs = converted
                        
                if not langs:
                    langs = [{"message_id": mid, "languages": ["en - English"]} for mid in msg_ids]
                cached_languages[conv_id] = langs

        # Clear existing output files if they exist and write all cached annotations
        for path in [intent_path, sentiment_path, summary_path, languages_path]:
            if os.path.exists(path):
                os.remove(path)

        with open(intent_path, 'w', encoding='utf-8') as f_intent, \
             open(sentiment_path, 'w', encoding='utf-8') as f_sent, \
             open(summary_path, 'w', encoding='utf-8') as f_sum, \
             open(languages_path, 'w', encoding='utf-8') as f_lang:
             
            for conv in conversations:
                conv_id = conv.get("conversation_id", "unknown")
                
                # Write intents
                for item in cached_intents.get(conv_id, []):
                    f_intent.write(json.dumps(item, ensure_ascii=False) + "\n")
                    counts["intent_labels_written"] += 1

                # Write sentiments
                for item in cached_sentiments.get(conv_id, []):
                    f_sent.write(json.dumps(item, ensure_ascii=False) + "\n")
                    counts["sentiment_labels_written"] += 1

                # Write summary
                sum_obj = cached_summaries.get(conv_id, {"issue": "", "resolution": ""})
                f_sum.write(json.dumps({
                    "conversation_id": conv_id,
                    "summary": sum_obj
                }, ensure_ascii=False) + "\n")
                counts["summaries_written"] += 1

                # Write languages
                langs = cached_languages.get(conv_id, [])
                f_lang.write(json.dumps({
                    "conversation_id": conv_id,
                    "detected_languages": langs
                }, ensure_ascii=False) + "\n")
                counts["languages_written"] += 1
                
                counts["conversations_processed"] += 1

        return counts
