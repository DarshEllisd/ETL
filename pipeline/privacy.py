import os
import json
import re
import time
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple

logger = logging.getLogger("etl_pipeline.privacy")

class PrivacyScrubber:
    def __init__(self, input_dir: str, output_dir: str, report_path: str, api_key_env: str = "GROQ_API_KEY_SCRUBBING", model: str = "llama-3.1-8b-instant"):
        """
        Initialize PrivacyScrubber.
        :param input_dir: Directory containing cleaned conversation records.
        :param output_dir: Directory to save anonymized conversation records.
        :param report_path: File path to save the final validation report (e.g. 'privacy_report.json').
        """
        self.input_dir = os.path.abspath(input_dir)
        self.output_dir = os.path.abspath(output_dir)
        self.report_path = os.path.abspath(report_path)
        self.api_key_env = api_key_env
        self.model = model
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Regex compiled patterns
        self.email_regex = re.compile(
            r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        )
        
        # Matches common phone number formats:
        # e.g., +1 (555) 019-9234, +91 98765-43210, 555-019-9234, 5550199234, +44 20 7946 0958
        # We put \+? before \b because + is a non-word character and \b doesn't match before it if preceded by a space.
        self.phone_regex = re.compile(
            r'\+?\b(?:\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b|' # US/Intl 3-3-4
            r'\+?\b(?:\d{1,3}[-.\s]?)?\d{2}[-.\s]?\d{4}[-.\s]?\d{4}\b|'       # UK 2-4-4
            r'\+?\b(?:44\s?|0)7\d{3}[-.\s]?\d{6}\b|'                          # UK Mobile 5-6
            r'\+?\b(?:\d{1,3}[-.\s]?)?\d{5}[-.\s]?\d{5}\b'                    # India/others 5-5
        )

        # Matches passwords and credentials with optional helper verbs:
        # e.g., password: mySecretKey, credential is: Secret_Key, PIN = 1234
        self.password_regex = re.compile(
            r'\b(password|pass|pin|passwd|credential|secret\s+key|secret|key)\b(\s*(is|are|of|to)?\s*[:=]\s*)([A-Za-z0-9_#$@\-]+)', re.IGNORECASE
        )

        # Matches standard street addresses and postal zip codes:
        # e.g., 123 Main St, 456 Maple Avenue, 10001
        self.address_regex = re.compile(
            r'\b\d+\s+[A-Za-z0-9\s,\.]+?\s+(Street|St|Avenue|Ave|Road|Rd|Lane|Ln|Boulevard|Blvd|Drive|Dr|Way|Court|Ct|Parkway|Pkwy|Plaza|Plz|Place|Pl|Square|Sq|Terrace|Ter|Highway|Hwy)\b|'
            r'(?<![#$€£])\b\d{5}(-\d{4})?\b', re.IGNORECASE
        )

    def scrub_text(self, text: str, participant_names: List[str] = None) -> Dict[str, Any]:
        """
        Scrubs email addresses, phone numbers, passwords, addresses, and participant names.
        Returns a dictionary containing the scrubbed text and counts of replacements.
        """
        if not text:
            return {
                "text": "",
                "emails": 0,
                "phones": 0,
                "passwords": 0,
                "addresses": 0,
                "names": 0
            }
            
        # 1. Scrub emails
        scrubbed, email_count = self.email_regex.subn('[EMAIL]', text)
        
        # 2. Scrub phones
        scrubbed, phone_count = self.phone_regex.subn('[PHONE]', scrubbed)
        
        # 3. Scrub physical addresses / zips
        scrubbed, address_count = self.address_regex.subn('[ADDRESS]', scrubbed)
        
        # 4. Scrub passwords/secrets (using custom replacement to normalize separators)
        def replace_password(match):
            label = match.group(1)
            connector = match.group(2)
            if ':' in connector or any(w in connector.lower() for w in ['is', 'are', 'of', 'to']):
                return f"{label}{connector}[PASSWORD]"
            else:
                return f"{label}: [PASSWORD]"
                
        scrubbed, password_count = self.password_regex.subn(replace_password, scrubbed)
        
        # 5. Scrub participant names if provided
        name_count = 0
        if participant_names:
            # Sort names by length descending to replace longer matches first
            sorted_names = sorted(list(set(participant_names)), key=len, reverse=True)
            for name in sorted_names:
                if len(name) < 3:
                    continue
                # Use word boundaries to prevent matching names inside other words
                pattern = re.compile(rf'\b{re.escape(name)}\b', re.IGNORECASE)
                scrubbed, sub_count = pattern.subn('[NAME]', scrubbed)
                name_count += sub_count
                
        return {
            "text": scrubbed,
            "emails": email_count,
            "phones": phone_count,
            "passwords": password_count,
            "addresses": address_count,
            "names": name_count
        }

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

    def llm_scrub_conversation(self, conv_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sends the conversation turns to the Groq API to scrub NSFW and private messages.
        Outputs a JSON list of mapping message IDs to clean/redacted texts.
        """
        api_key = self.get_api_key()
        if not api_key:
            return {}

        url = "https://api.groq.com/openai/v1/chat/completions"
        
        system_instruction = (
            "You are a content filtering and privacy protection assistant. "
            "Analyze the following conversation messages. For each message:\n"
            "1. Detect NSFW/offensive/inappropriate/profane content. Replace NSFW words or phrases with '[NSFW]'. Set 'is_nsfw' to true.\n"
            "2. Detect private/confidential/sensitive details (such as internal office warnings, HR warning notices, corporate secrets, confidential keys, personal life details). Replace those sentences or details with '[PRIVATE]'. Set 'is_private' to true.\n"
            "3. Keep normal, clean customer/support chat text exactly unchanged.\n"
            "Return a JSON object matching this schema:\n"
            "{\n"
            '  "messages": [\n'
            '    {"message_id": "string", "is_nsfw": boolean, "is_private": boolean, "scrubbed_text": "string"}\n'
            "  ]\n"
            "}"
        )
        
        # Format the messages in the prompt
        formatted_messages = []
        for msg in conv_data.get("messages", []):
            formatted_messages.append({
                "message_id": msg.get("message_id", ""),
                "speaker": msg.get("speaker", ""),
                "text": msg.get("text", "")
            })
            
        prompt = json.dumps({"messages_to_classify": formatted_messages}, indent=2)
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
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
                "User-Agent": "Mozilla/5.0"
            },
            method="POST"
        )
        
        max_retries = 3
        backoff = 3.0
        for attempt in range(max_retries):
            try:
                # Add delay between calls to stay below 30 RPM
                time.sleep(2.2)
                with urllib.request.urlopen(req, timeout=30) as res:
                    res_body = res.read().decode("utf-8")
                    res_json = json.loads(res_body)
                    content_str = res_json["choices"][0]["message"]["content"]
                    return json.loads(content_str)
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < max_retries - 1:
                    logger.warning(f"Groq API 429 Rate Limit hit. Retrying in {backoff}s...")
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                logger.warning(f"Groq LLM Privacy scrubbing failed for conversation '{conv_data.get('conversation_id')}': {e}. Falling back to pattern-only scrubbing.")
                return {}
            except Exception as e:
                logger.warning(f"Groq LLM Privacy scrubbing failed for conversation '{conv_data.get('conversation_id')}': {e}. Falling back to pattern-only scrubbing.")
                return {}
        return {}

    def extract_participants(self, conv_data: Dict[str, Any]) -> List[str]:
        """
        Helper to gather participant names from email headers, WhatsApp senders,
        and conversation metadata.
        """
        participants = set()
        
        # Check top-level metadata
        conv_meta = conv_data.get("metadata", {})
        for key in ["raw_speaker_name", "agent_name", "customer_name"]:
            val = conv_meta.get(key, "")
            if val and not re.match(r'^\+?[\d\s\-\(\)]+$', val):
                participants.add(val)
                parts = [p.strip() for p in re.split(r'[\s,]+', val) if p.strip()]
                for p in parts:
                    if len(p) >= 3:
                        participants.add(p)
                        
        # Check individual messages
        for msg in conv_data.get("messages", []):
            sender = msg.get("metadata", {}).get("raw_speaker_name", "")
            if not sender:
                sender = msg.get("sender", "")
            if not sender:
                sender = msg.get("speaker", "")
                
            # If email format like "Jane Doe <jane@mail.com>", extract "Jane Doe"
            if "<" in sender and ">" in sender:
                sender = sender.split("<")[0].strip()
                
            # Exclude raw phone numbers or numeric identifiers from being names
            if sender and not re.match(r'^\+?[\d\s\-\(\)]+$', sender):
                participants.add(sender)
                # Split into first/last name parts
                parts = [p.strip() for p in re.split(r'[\s,]+', sender) if p.strip()]
                for p in parts:
                    if len(p) >= 3:
                        participants.add(p)
                        
        return list(participants)

    def scrub_conversation_data(self, conv_data: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, int]]:
        """
        Scrubs a single conversation record.
        """
        participant_names = self.extract_participants(conv_data)
        
        anonymized_messages = []
        counts = {
            "emails": 0,
            "phones": 0,
            "passwords": 0,
            "addresses": 0,
            "names": 0,
            "nsfw": 0,
            "private": 0
        }
        
        # 1. Deterministic pattern-based scrubbing
        for msg in conv_data.get("messages", []):
            text = msg.get("text", "")
            res = self.scrub_text(text, participant_names)
            
            for key in ["emails", "phones", "passwords", "addresses", "names"]:
                counts[key] += res[key]
                
            msg_copy = msg.copy()
            msg_copy["text"] = res["text"]
            anonymized_messages.append(msg_copy)
            
        anonymized_conv = conv_data.copy()
        anonymized_conv["messages"] = anonymized_messages

        # 2. LLM-based NSFW/private content scrubbing
        api_key = self.get_api_key()
        if api_key:
            llm_res = self.llm_scrub_conversation(anonymized_conv)
            if llm_res and "messages" in llm_res:
                scrub_map = {m["message_id"]: m for m in llm_res["messages"] if "message_id" in m}
                for msg in anonymized_conv["messages"]:
                    m_id = msg.get("message_id")
                    if m_id in scrub_map:
                        decision = scrub_map[m_id]
                        if decision.get("is_nsfw"):
                            counts["nsfw"] += 1
                        if decision.get("is_private"):
                            counts["private"] += 1
                        if decision.get("scrubbed_text"):
                            msg["text"] = decision["scrubbed_text"]
        
        # Save scrub counts in metadata
        anonymized_conv["metadata"] = conv_data.get("metadata", {}).copy()
        anonymized_conv["metadata"]["anonymized"] = True
        anonymized_conv["metadata"]["pii_emails_scrubbed"] = counts["emails"]
        anonymized_conv["metadata"]["pii_phones_scrubbed"] = counts["phones"]
        anonymized_conv["metadata"]["pii_passwords_scrubbed"] = counts["passwords"]
        anonymized_conv["metadata"]["pii_addresses_scrubbed"] = counts["addresses"]
        anonymized_conv["metadata"]["pii_names_scrubbed"] = counts["names"]
        anonymized_conv["metadata"]["nsfw_messages_scrubbed"] = counts["nsfw"]
        anonymized_conv["metadata"]["private_messages_scrubbed"] = counts["private"]
        
        return anonymized_conv, counts

    def process_file(self, filename: str) -> Tuple[str, Dict[str, int]]:
        input_path = os.path.join(self.input_dir, filename)
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        anonymized_data, counts = self.scrub_conversation_data(data)
        
        output_path = os.path.join(self.output_dir, filename)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(anonymized_data, f, indent=2, ensure_ascii=False)
            
        return output_path, counts

    def process_all(self) -> Dict[str, Any]:
        """
        Scrubs all conversation records and writes privacy_report.json.
        """
        report_data = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "stats": {
                "total_files_anonymized": 0,
                "total_emails_scrubbed": 0,
                "total_phones_scrubbed": 0,
                "total_passwords_scrubbed": 0,
                "total_addresses_scrubbed": 0,
                "total_names_scrubbed": 0,
                "total_nsfw_messages_scrubbed": 0,
                "total_private_messages_scrubbed": 0
            },
            "scrubbed_details": []
        }
        
        if not os.path.exists(self.input_dir):
            return report_data
            
        total_files = 0
        totals = {
            "emails": 0,
            "phones": 0,
            "passwords": 0,
            "addresses": 0,
            "names": 0,
            "nsfw": 0,
            "private": 0
        }
        
        for filename in os.listdir(self.input_dir):
            if filename.endswith(".json"):
                total_files += 1
                out_path, counts = self.process_file(filename)
                
                has_pii = any(val > 0 for val in counts.values())
                if has_pii:
                    conv_id = filename.split('.')[0]
                    report_data["scrubbed_details"].append({
                        "conversation_id": conv_id,
                        "file": filename,
                        "emails_scrubbed": counts["emails"],
                        "phones_scrubbed": counts["phones"],
                        "passwords_scrubbed": counts["passwords"],
                        "addresses_scrubbed": counts["addresses"],
                        "names_scrubbed": counts["names"],
                        "nsfw_scrubbed": counts["nsfw"],
                        "private_scrubbed": counts["private"]
                    })
                    
                for key in totals:
                    totals[key] += counts[key]
                
        report_data["stats"]["total_files_anonymized"] = total_files
        report_data["stats"]["total_emails_scrubbed"] = totals["emails"]
        report_data["stats"]["total_phones_scrubbed"] = totals["phones"]
        report_data["stats"]["total_passwords_scrubbed"] = totals["passwords"]
        report_data["stats"]["total_addresses_scrubbed"] = totals["addresses"]
        report_data["stats"]["total_names_scrubbed"] = totals["names"]
        report_data["stats"]["total_nsfw_messages_scrubbed"] = totals["nsfw"]
        report_data["stats"]["total_private_messages_scrubbed"] = totals["private"]
        
        # Write report
        report_dir = os.path.dirname(self.report_path)
        if report_dir:
            os.makedirs(report_dir, exist_ok=True)
            
        with open(self.report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
            
        return report_data
