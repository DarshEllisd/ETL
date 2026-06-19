# Canonical Conversation & Message Schema

To allow the ETL pipeline to process messages from multiple distinct sources (e.g., Gmail emails, WhatsApp chat exports) using the same cleaning, privacy, and annotation components, we normalize all input data into a single, unified canonical format.

---

## 1. Canonical Message Schema

Each individual entry/message in a conversation is normalized to this structure.

```json
{
  "message_id": "msg_9823749283",
  "conversation_id": "thread_8347239482",
  "timestamp": "2026-06-19T06:30:15Z",
  "speaker": "user",
  "text": "Hi, I ordered a widget yesterday and haven't received a tracking number yet.",
  "metadata": {
    "raw_speaker_name": "John Doe",
    "whatsapp_phone": "+15550199",
    "email_message_id": "<abcdef123@mail.gmail.com>"
  }
}
```

### Fields

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `message_id` | String | A unique identifier generated or extracted for this message. |
| `conversation_id` | String | The identifier of the thread/session this message belongs to. |
| `timestamp` | String | ISO 8601 formatted UTC timestamp (`YYYY-MM-DDTHH:MM:SSZ`). |
| `speaker` | String | Normalized role of the sender. Primary roles are: `user` (customer/client) and `assistant` (support agent/bot). |
| `text` | String | The actual message content (text body). |
| `metadata` | Object | Dictionary for storing source-specific data (e.g., email subjects, CC headers, raw name tags) without loss of context. |

---

## 2. Canonical Conversation Schema

Once individual messages are ingestion-normalized and reconstructed into threads (reconstruction step), they are grouped into a Conversation record. This is the unit used to generate final training datasets and evaluation reports.

```json
{
  "conversation_id": "thread_8347239482",
  "source": "whatsapp",
  "start_timestamp": "2026-06-19T06:30:15Z",
  "end_timestamp": "2026-06-19T06:32:00Z",
  "messages": [
    {
      "message_id": "msg_9823749283",
      "timestamp": "2026-06-19T06:30:15Z",
      "speaker": "user",
      "text": "Hi, I ordered a widget yesterday and haven't received a tracking number yet."
    },
    {
      "message_id": "msg_9823749284",
      "timestamp": "2026-06-19T06:32:00Z",
      "speaker": "assistant",
      "text": "Hello! Let me check that for you. It looks like it shipped this morning. Your tracking number is 1Z999AA10123456784."
    }
  ],
  "metadata": {
    "total_messages": 2,
    "subject": "Order Tracking Inquiry"
  }
}
```

### Fields

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `conversation_id` | String | A unique ID for the whole thread. |
| `source` | String | The ingestion source (e.g., `gmail`, `whatsapp`). |
| `start_timestamp` | String | ISO 8601 formatted UTC timestamp of the first message. |
| `end_timestamp` | String | ISO 8601 formatted UTC timestamp of the final message in the thread. |
| `messages` | Array | Chronologically ordered list of message objects conforming to the Canonical Message Schema. |
| `metadata` | Object | Aggregate metadata (e.g., participant count, subject lines, labels, overall language). |
