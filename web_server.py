import os
import sys
import json
import yaml
import http.server
import socketserver
import urllib.parse
from etl import run_pipeline, diff_versions, setup_logging

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
        
        # Load preview of conversations.jsonl (first 5 rows)
        preview_rows = []
        jsonl_path = os.path.join(version_dir, "conversations.jsonl")
        if os.path.exists(jsonl_path):
            with open(jsonl_path, 'r', encoding='utf-8') as f:
                for _ in range(5):
                    line = f.readline()
                    if not line:
                        break
                    try:
                        preview_rows.append(json.loads(line))
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
        anonymized_dir = os.path.join(project_root, "normalized", "anonymized")
        if os.path.exists(anonymized_dir):
            for filename in sorted(os.listdir(anonymized_dir)):
                if filename.endswith(".json"):
                    path = os.path.join(anonymized_dir, filename)
                    try:
                        with open(path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            conv_id = data.get("conversation_id")
                            if conv_id and conv_id not in approved:
                                messages = []
                                for m in data.get("messages", [])[:5]:
                                    role = m.get("speaker", "user")
                                    if role not in ["user", "assistant", "system"]:
                                        role = "user"
                                    messages.append({
                                        "role": role,
                                        "content": m.get("text", "")
                                    })
                                pending_rows.append({
                                    "conversation_id": conv_id,
                                    "messages": messages
                                })
                    except Exception:
                        pass

        self.send_json_response(200, {
            "metadata": meta,
            "statistics": stats,
            "preview": preview_rows,
            "pending": pending_rows
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
            run_pipeline(config, "export")
            
            annotator_conf = config.get("annotator", {})
            if annotator_conf.get("enabled", True):
                run_pipeline(config, "annotate")
                
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
            run_pipeline(config, "export")
            
            annotator_conf = config.get("annotator", {})
            if annotator_conf.get("enabled", True):
                run_pipeline(config, "annotate")
                
            rag_conf = config.get("rag", {})
            if rag_conf.get("enabled", True):
                run_pipeline(config, "rag")
            
            self.send_json_response(200, {"status": "success"})
        except Exception as e:
            self.send_json_response(500, {"error": f"Failed to approve conversation: {str(e)}"})

    def send_json_response(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
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
