import os
import json
import time
import urllib.request
import urllib.error
import logging
import hashlib
from typing import Dict, Any, List

logger = logging.getLogger("etl_pipeline.translator")

class ConversationTranslator:
    def __init__(
        self,
        input_dir: str,
        output_dir: str,
        api_key_env: str = "GROQ_API_KEY",
        model: str = "llama-3.1-8b-instant",
        languages_filename: str = "languages.jsonl",
        status_filename: str = "translation_status.jsonl"
    ):
        self.input_dir = os.path.abspath(input_dir)
        self.output_dir = os.path.abspath(output_dir)
        self.api_key_env = api_key_env
        self.model = model
        self.languages_filename = languages_filename
        self.status_filename = status_filename

    def compute_hash(self, messages: List[Dict[str, str]]) -> str:
        combined = "|".join(m.get("text", "") for m in messages)
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    def get_api_key(self) -> str:
        if os.environ.get("ETL_TESTING") == "true":
            return ""
        api_key = os.environ.get(self.api_key_env, "").strip()
        if not api_key:
            env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
            if os.path.exists(env_path):
                content = ""
                try:
                    with open(env_path, 'r', encoding='utf-8') as f:
                        content = f.read()
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

    def load_conversations(self) -> List[Dict[str, Any]]:
        conversations = []
        if not os.path.exists(self.input_dir):
            return conversations
        for filename in sorted(os.listdir(self.input_dir)):
            if filename.endswith(".json"):
                path = os.path.join(self.input_dir, filename)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        conversations.append(json.load(f))
                except Exception as e:
                    logger.error(f"Failed to load conversation file {filename}: {e}")
        return conversations

    def call_groq_translation(self, messages_to_translate: List[Dict[str, str]]) -> Dict[str, str]:
        api_key = self.get_api_key()
        if not api_key:
            raise ValueError("Groq API key not found for translation.")

        url = "https://api.groq.com/openai/v1/chat/completions"
        system_instruction = (
            "You are a professional translator. Translate the following batch of user/assistant messages into natural, standard English.\n"
            "Keep name placeholders (e.g. [PRIVATE], [NSFW]), emojis, punctuation, and markdown markup exactly.\n"
            "If a message is already in English, keep it unchanged.\n"
            "Output ONLY a valid JSON object matching this schema:\n"
            "{\n"
            '  "translations": [\n'
            '    {"message_id": "string", "translated_text": "string"}\n'
            '  ]\n'
            "}"
        )

        user_content = json.dumps(messages_to_translate, ensure_ascii=False)
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
        for attempt in range(max_retries):
            try:
                # Spacing to keep below 30 RPM
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

                    mapping = {}
                    for item in parsed.get("translations", []):
                        mid = item.get("message_id")
                        text = item.get("translated_text")
                        if mid and text:
                            mapping[mid] = text
                    return mapping
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < max_retries - 1:
                    retry_after = e.headers.get("retry-after") or e.headers.get("Retry-After")
                    sleep_time = float(retry_after) + 0.5 if retry_after else 60.0
                    logger.warning(f"Groq API 429 Rate Limit hit. Retrying in {sleep_time}s...")
                    time.sleep(sleep_time)
                else:
                    raise e
            except Exception as e:
                raise e
        raise ValueError("Failed to get response after retries")

    def process_all(self) -> int:
        conversations = self.load_conversations()
        languages_path = os.path.join(self.output_dir, self.languages_filename)
        status_path = os.path.join(self.output_dir, self.status_filename)

        # 1. Load translated status (map cid -> text_hash)
        translated_cids = {}
        if os.path.exists(status_path):
            try:
                with open(status_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            item = json.loads(line)
                            cid = item.get("conversation_id")
                            text_hash = item.get("text_hash")
                            if cid and text_hash:
                                translated_cids[cid] = text_hash
            except Exception:
                pass

        # 2. Build message-level language mappings
        msg_langs = {}
        if os.path.exists(languages_path):
            try:
                with open(languages_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            item = json.loads(line)
                            for entry in item.get("detected_languages", []):
                                if isinstance(entry, dict):
                                    mid = entry.get("message_id")
                                    langs = entry.get("languages", [])
                                    if mid:
                                        msg_langs[mid] = langs
            except Exception as e:
                logger.error(f"Failed to load language annotations: {e}")

        # 3. Filter messages that need translation and check hash
        messages_to_translate = []
        conversations_to_translate = []
        for conv in conversations:
            cid = conv.get("conversation_id")
            regional_msgs = []
            for msg in conv.get("messages", []):
                mid = msg.get("message_id")
                if not mid:
                    continue
                langs = msg_langs.get(mid, [])
                non_english = [l for l in langs if l != "en - English"]
                if len(non_english) > 0:
                    regional_msgs.append({
                        "message_id": mid,
                        "text": msg.get("text", "")
                    })
            if not regional_msgs:
                continue

            current_hash = self.compute_hash(regional_msgs)
            if cid in translated_cids and translated_cids[cid] == current_hash:
                continue

            conversations_to_translate.append((conv, regional_msgs))
            messages_to_translate.extend(regional_msgs)

        # 4. Batch translate using Groq (up to 10 messages per request)
        translation_map = {}
        batch_size = 10
        if messages_to_translate:
            if self.get_api_key() or os.environ.get("ETL_TESTING") == "true":
                logger.info(f"Translating {len(messages_to_translate)} regional language message(s) to English...")
                for i in range(0, len(messages_to_translate), batch_size):
                    batch = messages_to_translate[i : i + batch_size]
                    try:
                        res = self.call_groq_translation(batch)
                        translation_map.update(res)
                    except Exception as e:
                        logger.error(f"Batch translation failed: {e}. Skipping this batch.")
            else:
                logger.warning("No API key found for translation. Skipping translation step.")

        # 5. Apply translations in-place and save
        translated_count = 0
        for conv, regional_msgs in conversations_to_translate:
            cid = conv.get("conversation_id")
            modified = False
            for msg in conv.get("messages", []):
                mid = msg.get("message_id")
                if mid in translation_map:
                    msg["text"] = translation_map[mid]
                    modified = True
                    translated_count += 1
            
            if modified:
                # Save back to input_dir
                path = os.path.join(self.input_dir, f"{cid}.json")
                try:
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump(conv, f, indent=2, ensure_ascii=False)
                except Exception as e:
                    logger.error(f"Failed to save translated conversation {cid}: {e}")

            # Recalculate hash of translated regional messages
            translated_regional = []
            for msg in conv.get("messages", []):
                mid = msg.get("message_id")
                langs = msg_langs.get(mid, [])
                non_english = [l for l in langs if l != "en - English"]
                if len(non_english) > 0:
                    translated_regional.append({
                        "message_id": mid,
                        "text": msg.get("text", "")
                    })
            translated_hash = self.compute_hash(translated_regional)
            translated_cids[cid] = translated_hash

        # 6. Save translation status tracking file
        try:
            with open(status_path, 'w', encoding='utf-8') as f:
                for cid in sorted(list(translated_cids.keys())):
                    f.write(json.dumps({"conversation_id": cid, "text_hash": translated_cids[cid]}) + "\n")
        except Exception as e:
            logger.error(f"Failed to save translation status: {e}")

        return translated_count
