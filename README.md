# Unified Conversation ETL Platform

A modular, production-grade ETL pipeline designed to ingest raw communication histories (e.g., Gmail `.eml` files and WhatsApp `.txt` logs), normalize them into a canonical conversation schema, strip noise, sanitize PII, generate advanced AI annotations, translate regional languages, and compile structured datasets optimized for LLM fine-tuning, sentiment analysis, and Retrieval-Augmented Generation (RAG).

The platform also includes an interactive local web dashboard for auditing datasets, re-classifying languages, adjusting role assignments, and monitoring pipeline runs.

---

## Architecture & Directory Structure

```text
etl-platform/
├── configs/            # YAML configuration files (e.g., config.yaml)
├── connectors/         # Source-specific ingestion connectors (Gmail, WhatsApp)
├── pipeline/           # Core ETL transformation stage modules
│   ├── normalizer.py   # Normalized schema mapping
│   ├── merger.py       # Cross-channel thread merging
│   ├── thread_builder.py# Temporal session reconstruction
│   ├── cleaner.py      # Noise removal and quality cleaning
│   ├── privacy.py      # Regex + Groq LLM PII scrubbing
│   ├── annotator.py    # Intent, sentiment, summary, and language annotations
│   ├── translator.py   # Groq-powered regional language translation
│   ├── dataset_generator.py # Final dataset compiler (conversations.jsonl)
│   └── rag_generator.py # Semantic chunking & fact nugget parsing for RAG
├── storage/            # Local raw data storage layer abstraction
├── datasets/           # Output directory for versioned datasets (e.g., v1.0.0/)
├── web/                # HTML, CSS, and JS frontend assets for the dashboard
├── tests/              # Comprehensive unittest test suite
├── etl.py              # Main CLI pipeline runner script
└── web_server.py       # Local HTTP server hosting the web dashboard
```

---

## Pipeline Execution Stages

The pipeline runs sequentially through 10 distinct stages:

| Stage | Name | Description | Output Location / Files |
|---|---|---|---|
| **1** | **Ingest** | Copies raw source EML and WhatsApp files into raw storage. | `raw/gmail/`, `raw/whatsapp/` |
| **2** | **Normalize** | Parses raw logs and maps metadata to a canonical message schema. | `normalized/gmail/`, `normalized/whatsapp/` |
| **3** | **Merge** | Combines messages across channels matching email and phone records. | `normalized/unified/` |
| **4** | **Thread** | Groups dialogue into session threads using a gap threshold (default 24h). | `normalized/reconstructed/`, `validation_report.json` |
| **5** | **Clean** | Strips duplicate messages, autoreply keywords, and low-quality spam. | `normalized/cleaned/` |
| **6** | **Scrub PII** | Anonymizes phone numbers, emails, passwords, and addresses. | `normalized/anonymized/`, `privacy_report.json` |
| **7** | **Annotate** | Predicts message intents, sentiment scores, and detects languages. | `datasets/<version>/languages.jsonl`, `intent_labels.jsonl`, `summaries.jsonl` |
| **8** | **Translate** | Detects regional languages (Hinglish, Tamil, Gujarati, Marathi) and translates them to English in-place. | Updates `normalized/anonymized/*.json` |
| **9** | **Export** | Whitelists approved conversations, applies whitelist filters, and outputs final training formats. | `datasets/<version>/conversations.jsonl`, `metadata.json` |
| **10**| **RAG** | Generates sliding-window conversation segments and extracts isolated facts. | `datasets/<version>/rag_chunks.jsonl` |

---

## Setup & Installation

### 1. Prerequisites
* Python 3.9+ installed.
* A Groq API account and access key (for scrubbing, annotation, and translation).

### 2. Environment Variables
Create a `.env` file in the project root containing your API credentials:
```env
# Required for Stage 7 (Annotation) & Stage 8 (Translation)
GROQ_API_KEY=your_groq_api_key_here

# Required for Stage 6 (PII Scrubbing)
GROQ_API_KEY_SCRUBBING=your_groq_scrubbing_key_here
```

### 3. Installation
Install requirements using standard Python packages:
```bash
pip install pyyaml python-dotenv
```

---

## Usage Guide (CLI Runner)

The `etl.py` script acts as the command-line interface to execute the pipeline and inspect version diffs.

### Run the Full Pipeline
Executes all 10 stages sequentially from ingestion to RAG generation:
```bash
python etl.py run
```
You can customize the config path:
```bash
python etl.py run --config configs/custom_config.yaml
```

### Run a Single Stage
To run or debug a specific step individually, use the `--step` flag:
```bash
# Ingest raw files
python etl.py run --step ingest

# Run PII scrubbing only
python etl.py run --step anonymize

# Run regional language translation
python etl.py run --step translate

# Run dataset export
python etl.py run --step export

# Run RAG database generation
python etl.py run --step rag
```

### Compare Dataset Versions
Compares two output versions (e.g., `v1.0.0` vs `v2.0.0`) and prints stats regarding schema conformity, message count differences, and PII leakage:
```bash
python etl.py diff --v1 1.0.0 --v2 2.0.0
```
Format output as raw JSON for structured integration:
```bash
python etl.py diff --v1 1.0.0 --v2 2.0.0 --format json
```

---

## Interactive Web Dashboard

To run the dashboard locally for auditing, role assignments, and pipeline monitoring:
```bash
python web_server.py
```
Open your browser and navigate to: **`http://localhost:8000`**

### Dashboard Features:
* **Execution Hub**: Launch a clean-slate pipeline run, monitor stage progress in real-time, and view logs.
* **PII & Quality Auditor**: View metrics on scrubbed phone numbers, emails, passwords, and addresses.
* **Pending Inbox**: Whitelist and exclude conversations before final export.
* **Language Explorer**: Re-classify incorrect language tags, map unrecognized languages, and review translations.

---

## Test Suite

Run unit and integration tests covering normalization, cleaning, PII scrubbing, language translation, and CLI execution:
```bash
python -m unittest discover tests
```
To run a specific test suite directly:
```bash
python -m unittest tests/test_translation.py
```
