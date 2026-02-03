# SenioCare API Documentation

API documentation for backend integration with the SenioCare AI service.

## Base URL

```
Local:      http://localhost:8080
Production: <your-deployed-url>
```

> **Note on `/docs`:** The auto-generated FastAPI docs at `/docs` may show schema warnings due to ADK internal types. Use this documentation instead for complete API reference.

## Additional Endpoints

- **Health Check:** `GET /health` - Returns service status
- **Custom Docs:** `GET /api-docs` - Redirects to web UI

## Quick Start

### 1. Start the Server
```bash
python main.py
# or with custom port
python main.py --port 3000
```

### 2. Create a Session
```bash
curl -X POST http://localhost:8080/apps/seniocare/users/USER_ID/sessions/SESSION_ID \
  -H "Content-Type: application/json" \
  -d "{}"
```

### 3. Send a Message
```bash
curl -X POST http://localhost:8080/run_sse \
  -H "Content-Type: application/json" \
  -d '{
    "app_name": "seniocare",
    "user_id": "USER_ID",
    "session_id": "SESSION_ID",
    "new_message": {
      "role": "user",
      "parts": [{"text": "ممكن تقترح عليا وجبة فطار صحية؟"}]
    },
    "streaming": false
  }'
```

---

## Endpoints

### List Available Agents
```http
GET /list-apps
```

**Response:**
```json
["seniocare"]
```

---

### Create/Update Session
```http
POST /apps/{app_name}/users/{user_id}/sessions/{session_id}
Content-Type: application/json

{}
```

| Parameter | Type | Description |
|-----------|------|-------------|
| app_name | string | Agent name (`seniocare`) |
| user_id | string | Your user's unique ID |
| session_id | string | Unique conversation session ID |

---

### Run Agent
```http
POST /run_sse
Content-Type: application/json
```

**Request Body:**
```json
{
    "app_name": "seniocare",
    "user_id": "user_123",
    "session_id": "session_abc",
    "new_message": {
        "role": "user",
        "parts": [{"text": "User message in Arabic"}]
    },
    "streaming": false
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| app_name | string | Yes | Always `"seniocare"` |
| user_id | string | Yes | User identifier |
| session_id | string | Yes | Conversation session ID |
| new_message.role | string | Yes | Always `"user"` |
| new_message.parts | array | Yes | Array with `{"text": "..."}` |
| streaming | boolean | No | `true` for SSE streaming |

**Response (streaming: false):**
```json
{
    "events": [
        {
            "type": "agent_response",
            "content": "يا هلا! ..."
        }
    ]
}
```

---

### Analyze Image (Vision AI)
```http
POST /analyze-image
Content-Type: application/json
```

**Request Body:**
```json
{
    "user_id": "user_123",
    "session_id": "session_abc",
    "image_type": "medication",
    "image_base64": "base64_encoded_image_data..."
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| user_id | string | Yes | User identifier |
| session_id | string | Yes | Session identifier |
| image_type | string | Yes | `"medication"` or `"medical_report"` |
| image_base64 | string | Yes | Base64 encoded image |

**Response (Medication):**
```json
{
    "success": true,
    "image_type": "medication",
    "medication_info": {
        "medication_name": "Metformin",
        "active_ingredient": "Metformin Hydrochloride",
        "dosage": "500mg",
        "manufacturer": "Pharma Inc",
        "expiry_date": "2025-12"
    }
}
```

**Response (Medical Report):**
```json
{
    "success": true,
    "image_type": "medical_report",
    "report_info": {
        "report_type": "blood_test",
        "date": "2024-01-15",
        "key_findings": ["Elevated blood sugar", "Normal cholesterol"],
        "values": {
            "blood_sugar": "180 mg/dL",
            "cholesterol": "180 mg/dL"
        },
        "recommendations": ["Follow up with doctor"]
    }
}
```

> **Note:** Requires `llama3.2-vision` model. Run `ollama pull llama3.2-vision` if not installed.

---

## Session Management

- Sessions persist across requests
- Store `user_id` and `session_id` to maintain conversation history
- Create new `session_id` for new conversations
- Same `session_id` = continues previous conversation

---

## Integration Example (Node.js)

```javascript
async function sendMessage(userId, sessionId, message) {
    const response = await fetch('http://localhost:8080/run_sse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            app_name: 'seniocare',
            user_id: userId,
            session_id: sessionId,
            new_message: {
                role: 'user',
                parts: [{ text: message }]
            },
            streaming: false
        })
    });
    return response.json();
}
```

---

## Web UI Testing

Visit http://localhost:8080 in browser for interactive testing.
