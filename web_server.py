import os
import sys
import json
import yaml
import shutil
import http.server
import socketserver
import urllib.parse
from etl import run_pipeline, diff_versions, setup_logging

def are_annotations_missing(project_root, version, approved_ids):
    version_dir = os.path.join(project_root, "datasets", version)
    intent_path = os.path.join(version_dir, "intent_labels.jsonl")
    sentiment_path = os.path.join(version_dir, "sentiment_labels.jsonl")
    summary_path = os.path.join(version_dir, "summaries.jsonl")
    languages_path = os.path.join(version_dir, "languages.jsonl")

    # If any file is missing, we are missing annotations
    for path in [intent_path, sentiment_path, summary_path, languages_path]:
        if not os.path.exists(path):
            return True

    # Check if all approved_ids are covered
    def get_annotated_cids(path):
        cids = set()
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        item = json.loads(line)
                        cid = item.get("conversation_id")
                        if cid:
                            cids.add(cid)
        except Exception:
            pass
        return cids

    for path in [intent_path, sentiment_path, summary_path, languages_path]:
        cids = get_annotated_cids(path)
        if not cids.issuperset(approved_ids):
            return True

    return False

class ETLDashboardHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        # Serve static files from the 'web' folder
        project_root = os.path.dirname(os.path.abspath(__file__))
        web_dir = os.path.join(project_root, "web")
        
        # Strip query parameters
        parsed_url = urllib.parse.urlparse(path)
        clean_path = parsed_url.path
        
        if clean_path == "/" or clean_path == "/index.html":
            return os.path.join(web_dir, "index.html")
        elif clean_path in ["/app.css", "/app.js"]:
            return os.path.join(web_dir, clean_path[1:])
            
        return super().translate_path(path)

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        if parsed_url.path == "/api/status":
            self.handle_api_status()
        elif parsed_url.path == "/api/dataset-details":
            self.handle_api_dataset_details(parsed_url.query)
        else:
            super().do_GET()

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        if parsed_url.path == "/api/run":
            self.handle_api_run()
        elif parsed_url.path == "/api/diff":
            self.handle_api_diff()
        elif parsed_url.path == "/api/exclude-conversation":
            self.handle_api_exclude_conversation()
        elif parsed_url.path == "/api/approve-conversation":
            self.handle_api_approve_conversation()
        elif parsed_url.path == "/api/approve-all-conversations":
            self.handle_api_approve_all_conversations()
        elif parsed_url.path == "/api/save-roles":
            self.handle_api_save_roles()
        elif parsed_url.path == "/api/approve-language":
            self.handle_api_approve_language()
        elif parsed_url.path == "/api/clean-slate":
            self.handle_api_clean_slate()
        else:
            self.send_error(404, "Endpoint not found")

    def handle_api_status(self):
        project_root = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(project_root, "configs", "config.yaml")
        
        config = {}
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                try:
                    config = yaml.safe_load(f)
                except Exception:
                    pass
                    
        # File counters
        def count_files(dir_path):
            if os.path.exists(dir_path):
                return len([f for f in os.listdir(dir_path) if os.path.isfile(os.path.join(dir_path, f))])
            return 0
            
        raw_gmail = count_files(os.path.join(project_root, "raw", "gmail"))
        raw_wa = count_files(os.path.join(project_root, "raw", "whatsapp"))
        norm_gmail = count_files(os.path.join(project_root, "normalized", "gmail"))
        norm_wa = count_files(os.path.join(project_root, "normalized", "whatsapp"))
        
        # Find available version folders under datasets
        versions = []
        datasets_base = os.path.join(project_root, "datasets")
        if os.path.exists(datasets_base):
            for d in os.listdir(datasets_base):
                if os.path.isdir(os.path.join(datasets_base, d)) and d.startswith("v"):
                    versions.append(d)
        versions.sort()
        
        status_data = {
            "config": config,
            "counts": {
                "raw_gmail": raw_gmail,
                "raw_whatsapp": raw_wa,
                "normalized_gmail": norm_gmail,
                "normalized_whatsapp": norm_wa,
            },
            "versions": versions
        }
        
        self.send_json_response(200, status_data)

    def handle_api_dataset_details(self, query_str):
        project_root = os.path.dirname(os.path.abspath(__file__))
        params = urllib.parse.parse_qs(query_str)
        version = params.get("version", [""])[0]
        
        if not version:
            self.send_json_response(400, {"error": "Missing 'version' parameter"})
            return
            
        version_dir = os.path.join(project_root, "datasets", version)
        if not os.path.exists(version_dir):
            self.send_json_response(404, {"error": f"Version directory {version} not found"})
            return
            
        # Load metadata and statistics
        def load_json(filename):
            path = os.path.join(version_dir, filename)
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    try:
                        return json.load(f)
                    except Exception:
                        pass
            return {}
            
        meta = load_json("metadata.json")
        stats = load_json("statistics.json")
        
        # Load preview of conversations.jsonl (first 50 rows)
        preview_rows = []
        jsonl_path = os.path.join(version_dir, "conversations.jsonl")
        if os.path.exists(jsonl_path):
            with open(jsonl_path, 'r', encoding='utf-8') as f:
                for _ in range(50):
                    line = f.readline()
                    if not line:
                        break
                    try:
                        preview_rows.append(json.loads(line))
                    except Exception:
                        pass

        # Load allowed languages whitelist
        allowed_langs_path = os.path.join(project_root, "allowed_languages.json")
        default_langs = ["en - English", "hi - Hindi", "ta - Tamil"]
        if not os.path.exists(allowed_langs_path):
            try:
                with open(allowed_langs_path, 'w', encoding='utf-8') as f:
                    json.dump(default_langs, f, indent=2)
            except Exception:
                pass
        allowed_langs = default_langs
        if os.path.exists(allowed_langs_path):
            try:
                with open(allowed_langs_path, 'r', encoding='utf-8') as f:
                    allowed_langs = json.load(f)
            except Exception:
                pass

        # Load languages annotations
        languages_path = os.path.join(version_dir, "languages.jsonl")
        conv_to_langs = {}
        conv_msg_langs = {}
        all_seen_languages = set(default_langs)
        if os.path.exists(languages_path):
            try:
                with open(languages_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            item = json.loads(line)
                            cid = item.get("conversation_id")
                            if cid:
                                raw_langs = item.get("detected_languages", [])
                                conv_langs_set = set()
                                msg_langs = {}
                                for entry in raw_langs:
                                    if isinstance(entry, dict):
                                        mid = entry.get("message_id")
                                        mlangs = entry.get("languages", [])
                                        if mid:
                                            msg_langs[mid] = mlangs
                                        for l in mlangs:
                                            conv_langs_set.add(l)
                                            all_seen_languages.add(l)
                                    else:
                                        conv_langs_set.add(str(entry))
                                        all_seen_languages.add(str(entry))
                                conv_to_langs[cid] = sorted(list(conv_langs_set))
                                conv_msg_langs[cid] = msg_langs
            except Exception:
                pass

        # Load pending review conversations (in normalized/anonymized/ but not in approved.json)
        approved = []
        approved_path = os.path.join(project_root, "approved.json")
        if os.path.exists(approved_path):
            try:
                with open(approved_path, 'r', encoding='utf-8') as f:
                    approved = json.load(f)
            except Exception:
                pass
                
        pending_rows = []
        approved_rows = []
        anonymized_dir = os.path.join(project_root, "normalized", "anonymized")
        
        if os.path.exists(anonymized_dir):
            for filename in sorted(os.listdir(anonymized_dir)):
                if filename.endswith(".json"):
                    path = os.path.join(anonymized_dir, filename)
                    try:
                        with open(path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            conv_id = data.get("conversation_id")
                            if not conv_id:
                                continue
                                
                            messages = []
                            cid_msg_langs = conv_msg_langs.get(conv_id, {})
                            for m in data.get("messages", []):
                                role = m.get("speaker", "user")
                                if role not in ["user", "assistant", "system"]:
                                    role = "user"
                                mid = m.get("message_id", "")
                                messages.append({
                                    "role": role,
                                    "content": m.get("text", ""),
                                    "message_id": mid,
                                    "detected_languages": cid_msg_langs.get(mid, ["en - English"])
                                })
                                
                            langs = conv_to_langs.get(conv_id, ["en - English"])
                            unapproved_langs = [l for l in langs if l not in allowed_langs]
                            is_flagged = len(unapproved_langs) > 0
                            
                            row_item = {
                                "conversation_id": conv_id,
                                "messages": messages,
                                "detected_languages": langs,
                                "flagged": is_flagged,
                                "flagged_languages": unapproved_langs
                            }
                            
                            if conv_id in approved and not is_flagged:
                                approved_rows.append(row_item)
                            else:
                                # For pending inbox, limit message preview count to 5 for frontend performance
                                row_item["messages"] = messages[:5]
                                pending_rows.append(row_item)
                    except Exception:
                        pass

        # Load unique participants from normalized messages in gmail and whatsapp folders
        participants = []
        unique_set = set()
        for folder in ["gmail", "whatsapp"]:
            folder_dir = os.path.join(project_root, "normalized", folder)
            if os.path.exists(folder_dir):
                for filename in os.listdir(folder_dir):
                    if filename.endswith(".json"):
                        path = os.path.join(folder_dir, filename)
                        try:
                            with open(path, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                                name = data.get("metadata", {}).get("raw_speaker_name")
                                if name:
                                    if "@" in name and ("<" in name or ">" in name):
                                        import email.utils
                                        parsed_name, parsed_email = email.utils.parseaddr(name)
                                        if parsed_name:
                                            unique_set.add(parsed_name)
                                        if parsed_email:
                                            unique_set.add(parsed_email)
                                    else:
                                        unique_set.add(name)
                        except Exception:
                            pass
        participants = sorted(list(unique_set))
            
        # Load currently assigned agents
        agents = []
        agents_path = os.path.join(project_root, "agents.json")
        if os.path.exists(agents_path):
            try:
                with open(agents_path, 'r', encoding='utf-8') as f:
                    agents = json.load(f)
            except Exception:
                pass
        else:
            # Fallback to defaults from config.yaml
            config_path = os.path.join(project_root, "configs", "config.yaml")
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = yaml.safe_load(f)
                        agents = config.get("connectors", {}).get("whatsapp", {}).get("agent_names", [])
                except Exception:
                    pass

        self.send_json_response(200, {
            "metadata": meta,
            "statistics": stats,
            "preview": preview_rows,
            "approved_conversations": approved_rows,
            "pending": pending_rows,
            "participants": participants,
            "agents": agents,
            "allowed_languages": allowed_langs,
            "all_seen_languages": sorted(list(all_seen_languages))
        })

    def handle_api_run(self):
        project_root = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(project_root, "configs", "config.yaml")
        
        if not os.path.exists(config_path):
            self.send_json_response(400, {"error": "Config file configs/config.yaml not found"})
            return
            
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            
        # Direct execution of run_pipeline
        # Clear log file first
        log_file = config.get("logging", {}).get("log_filename", "etl_run.log")
        log_path = os.path.join(project_root, log_file)
        if os.path.exists(log_path):
            try:
                os.remove(log_path)
            except Exception:
                pass
                
        # Run pipeline
        try:
            setup_logging(config.get("logging", {}), verbose=False)
            run_pipeline(config)
            
            # Read back generated logs
            logs = ""
            if os.path.exists(log_path):
                with open(log_path, 'r', encoding='utf-8') as f:
                    logs = f.read()
            self.send_json_response(200, {"status": "success", "logs": logs})
        except Exception as e:
            self.send_json_response(500, {"error": f"Pipeline failed: {str(e)}"})

    def handle_api_diff(self):
        project_root = os.path.dirname(os.path.abspath(__file__))
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        
        try:
            data = json.loads(post_data)
            v1 = data.get("v1")
            v2 = data.get("v2")
            if not v1 or not v2:
                self.send_json_response(400, {"error": "Missing parameters 'v1' or 'v2'"})
                return
                
            report = diff_versions(project_root, v1, v2, "json")
            self.send_json_response(200, report)
        except Exception as e:
            self.send_json_response(500, {"error": f"Comparison failed: {str(e)}"})

    def handle_api_exclude_conversation(self):
        project_root = os.path.dirname(os.path.abspath(__file__))
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        
        try:
            data = json.loads(post_data)
            version = data.get("version")
            conversation_id = data.get("conversation_id")
            
            if not version or not conversation_id:
                self.send_json_response(400, {"error": "Missing parameters 'version' or 'conversation_id'"})
                return
                
            exclusions_path = os.path.join(project_root, "exclusions.json")
            exclusions = []
            if os.path.exists(exclusions_path):
                try:
                    with open(exclusions_path, 'r', encoding='utf-8') as f:
                        exclusions = json.load(f)
                except Exception:
                    pass
            
            if conversation_id not in exclusions:
                exclusions.append(conversation_id)
                with open(exclusions_path, 'w', encoding='utf-8') as f:
                    json.dump(exclusions, f, indent=2)
            
            config_path = os.path.join(project_root, "configs", "config.yaml")
            if not os.path.exists(config_path):
                self.send_json_response(400, {"error": "Config file configs/config.yaml not found"})
                return
                
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            version_str = version[1:] if version.startswith("v") else version
            if "dataset" not in config:
                config["dataset"] = {}
            config["dataset"]["version"] = version_str
            
            setup_logging(config.get("logging", {}), verbose=False)
            
            annotator_conf = config.get("annotation", {})
            if annotator_conf.get("enabled", True):
                run_pipeline(config, "annotate")
                
            run_pipeline(config, "translate")
            run_pipeline(config, "export")
            
            rag_conf = config.get("rag", {})
            if rag_conf.get("enabled", True):
                run_pipeline(config, "rag")
            
            self.send_json_response(200, {"status": "success"})
        except Exception as e:
            self.send_json_response(500, {"error": f"Failed to exclude conversation: {str(e)}"})

    def handle_api_approve_conversation(self):
        project_root = os.path.dirname(os.path.abspath(__file__))
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        
        try:
            data = json.loads(post_data)
            version = data.get("version")
            conversation_id = data.get("conversation_id")
            
            if not version or not conversation_id:
                self.send_json_response(400, {"error": "Missing parameters 'version' or 'conversation_id'"})
                return
                
            approved_path = os.path.join(project_root, "approved.json")
            approved = []
            if os.path.exists(approved_path):
                try:
                    with open(approved_path, 'r', encoding='utf-8') as f:
                        approved = json.load(f)
                except Exception:
                    pass
            
            if conversation_id not in approved:
                approved.append(conversation_id)
                with open(approved_path, 'w', encoding='utf-8') as f:
                    json.dump(approved, f, indent=2)
            
            # Remove from exclusions if it is there
            exclusions_path = os.path.join(project_root, "exclusions.json")
            if os.path.exists(exclusions_path):
                try:
                    with open(exclusions_path, 'r', encoding='utf-8') as f:
                        exclusions = json.load(f)
                    if conversation_id in exclusions:
                        exclusions.remove(conversation_id)
                        with open(exclusions_path, 'w', encoding='utf-8') as f:
                            json.dump(exclusions, f, indent=2)
                except Exception:
                    pass
            
            config_path = os.path.join(project_root, "configs", "config.yaml")
            if not os.path.exists(config_path):
                self.send_json_response(400, {"error": "Config file configs/config.yaml not found"})
                return
                
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            version_str = version[1:] if version.startswith("v") else version
            if "dataset" not in config:
                config["dataset"] = {}
            config["dataset"]["version"] = version_str
            
            setup_logging(config.get("logging", {}), verbose=False)
            
            annotator_conf = config.get("annotation", {})
            if annotator_conf.get("enabled", True):
                version_dir_name = f"v{version_str}"
                if are_annotations_missing(project_root, version_dir_name, approved):
                    run_pipeline(config, "annotate")
                else:
                    print("All approved conversations are already annotated. Skipping annotation pipeline stage.")
                
            run_pipeline(config, "translate")
            run_pipeline(config, "export")
            
            rag_conf = config.get("rag", {})
            if rag_conf.get("enabled", True):
                run_pipeline(config, "rag")
            
            self.send_json_response(200, {"status": "success"})
        except Exception as e:
            self.send_json_response(500, {"error": f"Failed to approve conversation: {str(e)}"})

    def handle_api_approve_all_conversations(self):
        project_root = os.path.dirname(os.path.abspath(__file__))
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        
        try:
            data = json.loads(post_data)
            version = data.get("version")
            
            if not version:
                self.send_json_response(400, {"error": "Missing parameter 'version'"})
                return
                
            approved_path = os.path.join(project_root, "approved.json")
            approved = []
            if os.path.exists(approved_path):
                try:
                    with open(approved_path, 'r', encoding='utf-8') as f:
                        approved = json.load(f)
                except Exception:
                    pass
                    
            # Scan for all conversations in anonymized folder
            anonymized_dir = os.path.join(project_root, "normalized", "anonymized")
            added_any = False
            if os.path.exists(anonymized_dir):
                for filename in os.listdir(anonymized_dir):
                    if filename.endswith(".json"):
                        path = os.path.join(anonymized_dir, filename)
                        try:
                            with open(path, 'r', encoding='utf-8') as f:
                                conv_data = json.load(f)
                                conv_id = conv_data.get("conversation_id")
                                if conv_id and conv_id not in approved:
                                    approved.append(conv_id)
                                    added_any = True
                        except Exception:
                            pass
            
            if added_any:
                with open(approved_path, 'w', encoding='utf-8') as f:
                    json.dump(approved, f, indent=2)
            
            # Remove all from exclusions if present
            exclusions_path = os.path.join(project_root, "exclusions.json")
            if os.path.exists(exclusions_path):
                try:
                    with open(exclusions_path, 'r', encoding='utf-8') as f:
                        exclusions = json.load(f)
                    new_exclusions = [x for x in exclusions if x not in approved]
                    if len(new_exclusions) < len(exclusions):
                        with open(exclusions_path, 'w', encoding='utf-8') as f:
                            json.dump(new_exclusions, f, indent=2)
                except Exception:
                    pass
            
            config_path = os.path.join(project_root, "configs", "config.yaml")
            if not os.path.exists(config_path):
                self.send_json_response(400, {"error": "Config file configs/config.yaml not found"})
                return
                
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            version_str = version[1:] if version.startswith("v") else version
            if "dataset" not in config:
                config["dataset"] = {}
            config["dataset"]["version"] = version_str
            
            setup_logging(config.get("logging", {}), verbose=False)
            
            annotator_conf = config.get("annotation", {})
            if annotator_conf.get("enabled", True):
                version_dir_name = f"v{version_str}"
                if are_annotations_missing(project_root, version_dir_name, approved):
                    run_pipeline(config, "annotate")
                else:
                    print("All approved conversations are already annotated. Skipping annotation pipeline stage.")
                
            run_pipeline(config, "translate")
            run_pipeline(config, "export")
            
            rag_conf = config.get("rag", {})
            if rag_conf.get("enabled", True):
                run_pipeline(config, "rag")
            
            self.send_json_response(200, {"status": "success"})
        except Exception as e:
            self.send_json_response(500, {"error": f"Failed to approve all: {str(e)}"})

    def handle_api_save_roles(self):
        project_root = os.path.dirname(os.path.abspath(__file__))
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        
        try:
            data = json.loads(post_data)
            version = data.get("version", "v1.0.0")
            agents = data.get("agents", [])
            
            agents_path = os.path.join(project_root, "agents.json")
            with open(agents_path, 'w', encoding='utf-8') as f:
                json.dump(agents, f, indent=2)
                
            config_path = os.path.join(project_root, "configs", "config.yaml")
            if not os.path.exists(config_path):
                self.send_json_response(400, {"error": "Config file configs/config.yaml not found"})
                return
                
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            version_str = version[1:] if version.startswith("v") else version
            if "dataset" not in config:
                config["dataset"] = {}
            config["dataset"]["version"] = version_str
            
            # Optimize role updates by modifying speaker keys directly across all intermediate stages,
            # completely bypassing Groq LLM API calls (Stages 6 and 8).
            setup_logging(config.get("logging", {}), verbose=False)
            run_pipeline(config, "normalize")
            
            # Build message_id to speaker mapping
            msg_to_speaker = {}
            for folder in ["gmail", "whatsapp"]:
                folder_path = os.path.join(project_root, "normalized", folder)
                if os.path.exists(folder_path):
                    for filename in os.listdir(folder_path):
                        if filename.endswith(".json"):
                            p = os.path.join(folder_path, filename)
                            try:
                                with open(p, 'r', encoding='utf-8') as f:
                                    mdata = json.load(f)
                                    mid = mdata.get("message_id")
                                    spk = mdata.get("speaker")
                                    if mid and spk:
                                        msg_to_speaker[mid] = spk
                            except Exception:
                                pass
                                
            # Update speaker field in all intermediate folders directly
            for folder in ["unified", "reconstructed", "cleaned", "anonymized"]:
                folder_path = os.path.join(project_root, "normalized", folder)
                if os.path.exists(folder_path):
                    for filename in os.listdir(folder_path):
                        if filename.endswith(".json"):
                            p = os.path.join(folder_path, filename)
                            try:
                                with open(p, 'r', encoding='utf-8') as f:
                                    cdata = json.load(f)
                                updated = False
                                for msg in cdata.get("messages", []):
                                    mid = msg.get("message_id")
                                    if mid in msg_to_speaker:
                                        msg["speaker"] = msg_to_speaker[mid]
                                        updated = True
                                if updated:
                                    with open(p, 'w', encoding='utf-8') as f:
                                        json.dump(cdata, f, indent=2, ensure_ascii=False)
                            except Exception:
                                pass
                                
            # Rebuild dataset exports and statistics
            run_pipeline(config, "translate")
            run_pipeline(config, "export")
            
            # Rebuild RAG chunks
            rag_conf = config.get("rag", {})
            if rag_conf.get("enabled", True):
                run_pipeline(config, "rag")
                
            self.send_json_response(200, {"status": "success"})
        except Exception as e:
            self.send_json_response(500, {"error": f"Failed to save roles: {str(e)}"})

    def handle_api_clean_slate(self):
        project_root = os.path.dirname(os.path.abspath(__file__))
        try:
            # 0. Delete raw folder contents (which are temporary JSON files generated from mock_data)
            raw_dir = os.path.join(project_root, "raw")
            if os.path.exists(raw_dir):
                for item in os.listdir(raw_dir):
                    if item == ".gitkeep":
                        continue
                    item_path = os.path.join(raw_dir, item)
                    try:
                        if os.path.isdir(item_path):
                            shutil.rmtree(item_path)
                        else:
                            os.remove(item_path)
                    except Exception:
                        pass
                        
            # 1. Delete normalized folder contents
            normalized_dir = os.path.join(project_root, "normalized")
            if os.path.exists(normalized_dir):
                for item in os.listdir(normalized_dir):
                    item_path = os.path.join(normalized_dir, item)
                    try:
                        if os.path.isdir(item_path):
                            shutil.rmtree(item_path)
                        else:
                            os.remove(item_path)
                    except Exception:
                        pass
                        
            # 2. Delete datasets contents (excluding .gitkeep)
            datasets_dir = os.path.join(project_root, "datasets")
            if os.path.exists(datasets_dir):
                for item in os.listdir(datasets_dir):
                    if item == ".gitkeep":
                        continue
                    item_path = os.path.join(datasets_dir, item)
                    try:
                        if os.path.isdir(item_path):
                            shutil.rmtree(item_path)
                        else:
                            os.remove(item_path)
                    except Exception:
                        pass
            
            # 3. Reset approved.json to only contain baseline IDs
            approved_path = os.path.join(project_root, "approved.json")
            if os.path.exists(approved_path):
                try:
                    os.remove(approved_path)
                except Exception:
                    pass
            
            baseline_ids = [
                "email_thread_9275c84ee0b3ad4be861527e53e8c415_session_0",
                "email_thread_c594e1d3c87a01c7027e0e89377593de_session_0",
                "whatsapp_chat_58be2551518134d646da77ebdd1d6363_session_0",
                "whatsapp_chat_cd4fb49f9acb9d6bb54456e9774ce154_session_0",
                "whatsapp_chat_cd4fb49f9acb9d6bb54456e9774ce154_session_1"
            ]
            try:
                with open(approved_path, 'w', encoding='utf-8') as f:
                    json.dump(baseline_ids, f, indent=2)
            except Exception:
                pass
                
            # 4. Remove exclusions.json
            exclusions_path = os.path.join(project_root, "exclusions.json")
            if os.path.exists(exclusions_path):
                try:
                    os.remove(exclusions_path)
                except Exception:
                    pass
                
            # 5. Remove agents.json
            agents_path = os.path.join(project_root, "agents.json")
            if os.path.exists(agents_path):
                try:
                    os.remove(agents_path)
                except Exception:
                    pass
                
            # 6. Remove allowed_languages.json
            allowed_langs_path = os.path.join(project_root, "allowed_languages.json")
            if os.path.exists(allowed_langs_path):
                try:
                    os.remove(allowed_langs_path)
                except Exception:
                    pass

            # 7. Remove report files
            for report in ["validation_report.json", "privacy_report.json"]:
                p = os.path.join(project_root, report)
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
                    
            self.send_json_response(200, {"status": "success"})
        except Exception as e:
            self.send_json_response(500, {"error": f"Failed to clean slate: {str(e)}"})

    def handle_api_approve_language(self):
        project_root = os.path.dirname(os.path.abspath(__file__))
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        
        try:
            data = json.loads(post_data)
            version = data.get("version")
            language = data.get("language")
            
            replace_with = data.get("replace_with")
            
            if not version or not language:
                self.send_json_response(400, {"error": "Missing parameters 'version' or 'language'"})
                return
                
            version_str = version[1:] if version.startswith("v") else version
            version_dir = os.path.join(project_root, "datasets", f"v{version_str}")
            
            # If replace_with is specified, update languages.jsonl mapping
            if replace_with:
                languages_path = os.path.join(version_dir, "languages.jsonl")
                if os.path.exists(languages_path):
                    try:
                        updated_lines = []
                        with open(languages_path, 'r', encoding='utf-8') as f:
                            for line in f:
                                if line.strip():
                                    item = json.loads(line)
                                    raw_langs = item.get("detected_languages", [])
                                    new_langs = []
                                    for entry in raw_langs:
                                        if isinstance(entry, dict):
                                            mlangs = entry.get("languages", [])
                                            updated_mlangs = [replace_with if l == language else l for l in mlangs]
                                            entry["languages"] = updated_mlangs
                                            new_langs.append(entry)
                                        else:
                                            new_langs.append(replace_with if str(entry) == language else str(entry))
                                    item["detected_languages"] = new_langs
                                    updated_lines.append(json.dumps(item, ensure_ascii=False) + "\n")
                        with open(languages_path, 'w', encoding='utf-8') as f:
                            f.writelines(updated_lines)
                    except Exception as e:
                        print(f"Failed to update languages mapping: {e}")
                
                # Now the new language is what we want to authorize
                target_auth = replace_with
            else:
                target_auth = language

            allowed_langs_path = os.path.join(project_root, "allowed_languages.json")
            default_langs = ["en - English", "hi - Hindi", "ta - Tamil"]
            allowed = default_langs
            
            if os.path.exists(allowed_langs_path):
                try:
                    with open(allowed_langs_path, 'r', encoding='utf-8') as f:
                        allowed = json.load(f)
                except Exception:
                    pass
            
            if target_auth not in allowed:
                allowed.append(target_auth)
                with open(allowed_langs_path, 'w', encoding='utf-8') as f:
                    json.dump(allowed, f, indent=2)
                    
            config_path = os.path.join(project_root, "configs", "config.yaml")
            if not os.path.exists(config_path):
                self.send_json_response(400, {"error": "Config file configs/config.yaml not found"})
                return
                
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            config["dataset"] = config.get("dataset", {})
            config["dataset"]["version"] = version_str
            
            # Rebuild dataset exports and RAG in a background thread to prevent HTTP timeouts
            import threading
            def run_background_pipeline(cfg):
                try:
                    setup_logging(cfg.get("logging", {}), verbose=False)
                    run_pipeline(cfg, "translate")
                    run_pipeline(cfg, "export")
                    rag_conf = cfg.get("rag", {})
                    if rag_conf.get("enabled", True):
                        run_pipeline(cfg, "rag")
                except Exception as ex:
                    print(f"Background pipeline rebuild failed: {ex}")

            threading.Thread(target=run_background_pipeline, args=(config,), daemon=True).start()
            
            self.send_json_response(200, {"status": "success"})
        except Exception as e:
            self.send_json_response(500, {"error": f"Failed to approve language: {str(e)}"})

    def send_json_response(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

def run_server():
    project_root = os.path.dirname(os.path.abspath(__file__))
    approved_path = os.path.join(project_root, "approved.json")
    if not os.path.exists(approved_path):
        baseline_ids = [
            "email_thread_9275c84ee0b3ad4be861527e53e8c415_session_0",
            "email_thread_c594e1d3c87a01c7027e0e89377593de_session_0",
            "whatsapp_chat_58be2551518134d646da77ebdd1d6363_session_0",
            "whatsapp_chat_cd4fb49f9acb9d6bb54456e9774ce154_session_0",
            "whatsapp_chat_cd4fb49f9acb9d6bb54456e9774ce154_session_1"
        ]
        try:
            with open(approved_path, 'w', encoding='utf-8') as f:
                json.dump(baseline_ids, f, indent=2)
        except Exception as e:
            print(f"Failed to bootstrap approved.json: {e}")
            
    PORT = 8000
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), ETLDashboardHandler) as httpd:
        print(f"ETL Dashboard Server running on http://localhost:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")
            sys.exit(0)

if __name__ == "__main__":
    run_server()
