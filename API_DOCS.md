# SenioCare AI Agent — API Documentation

> **Base URL:** `http://localhost:8080` (development)
> **Swagger UI:** `http://localhost:8080/docs`
> **ReDoc:** `http://localhost:8080/redoc`
> **OpenAPI JSON:** `http://localhost:8080/export-openapi`

---

## Quick Start (Backend Integration)

```
1. Start the AI agent server:    python main.py
2. Set user profile:             POST /set-user-profile/{user_id}
3. Create a session:             POST /apps/seniocare/users/{user_id}/sessions/{session_id}
4. Send a message:               POST /run_sse
```

---

---

## Endpoints

### 🟢 Health

#### `GET /health`
Health check endpoint for monitoring.

**Response:**
```json
{
    "status": "healthy",
    "service": "seniocare-api",
    "version": "2.0.0",
    "session_db": "sqlite+aiosqlite:///./sessions.db",
    "memory_service": "InMemoryMemoryService",
    "docs": "/docs"
}
```

**cURL:**
```bash
curl http://localhost:8080/health
```

---

#### `GET /export-openapi`
Download the OpenAPI spec as JSON (for static Swagger hosting).

**cURL:**
```bash
curl http://localhost:8080/export-openapi > openapi.json
```

---

### 👤 User Profile

#### `POST /set-user-profile/{user_id}`
Push user health profile data to persist across all sessions.

**When to call:** After user registration or when the full profile changes.

**Request Body (aligned with backend `ElderCreate` schema):**
```json
{
    "user_name": "Ahmed",
    "age": 72,
    "weight": 78.0,
    "height": 170.0,
    "gender": "male",
    "chronicDiseases": ["diabetes", "hypertension"],
    "allergies": ["shellfish"],
    "medications": [
        {"name": "Metformin", "dose": "500mg"},
        {"name": "Lisinopril", "dose": "10mg"}
    ],
    "mobilityStatus": "limited",
    "bloodType": "A+",
    "caregiver_ids": []
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `user_name` | string | ❌ | User's display name (from Firebase) |
| `age` | integer | ❌ | User's age |
| `weight` | float | ❌ | Weight in kg |
| `height` | float | ❌ | Height in cm |
| `gender` | string | ❌ | `"male"` or `"female"` |
| `chronicDiseases` | string[] | ❌ | Chronic conditions: `diabetes`, `hypertension`, `heart disease`, `arthritis`, `kidney disease` |
| `allergies` | string[] | ❌ | Food allergies: `shellfish`, `dairy`, `gluten`, `fish`, `eggs`, `nuts` |
| `medications` | object[] | ❌ | Each with `name` (string) and `dose` (string) |
| `mobilityStatus` | string | ❌ | `"limited"`, `"moderate"`, or `"active"` (default: `"limited"`) |
| `bloodType` | string | ❌ | e.g. `"A+"`, `"O-"`, `"B+"` |
| `caregiver_ids` | string[] | ❌ | Linked caregiver IDs from backend |

**Response (200):**
```json
{
    "success": true,
    "message": "Profile saved for user user_123",
    "user_id": "user_123",
    "profile_keys": ["user:user_id", "user:user_name", "user:age", "user:weight", "user:height", "user:gender", "user:chronicDiseases", "user:allergies", "user:medications", "user:mobilityStatus", "user:bloodType", "user:caregiver_ids"]
}
```

**cURL:**
```bash
curl -X POST http://localhost:8080/set-user-profile/user_123 \
  -H "Content-Type: application/json" \
  -d '{"user_name":"Ahmed","age":72,"weight":78.0,"height":170.0,"gender":"male","chronicDiseases":["diabetes"],"allergies":[],"medications":[{"name":"Metformin","dose":"500mg"}],"mobilityStatus":"limited","bloodType":"A+"}'
```

---

#### `GET /get-user-profile/{user_id}`
Retrieve user health profile data.

**Response (200 — profile exists):**
```json
{
    "success": true,
    "user_id": "user_123",
    "profile": {
        "user_id": "user_123",
        "user_name": "Ahmed",
        "age": 72,
        "weight": 78.0,
        "height": 170.0,
        "gender": "male",
        "chronicDiseases": ["diabetes"],
        "allergies": [],
        "medications": [{"name": "Metformin", "dose": "500mg"}],
        "mobilityStatus": "limited",
        "bloodType": "A+",
        "caregiver_ids": []
    }
}
```

**Response (200 — profile not found):**
```json
{
    "success": false,
    "message": "No profile found for user xyz. Call /set-user-profile first.",
    "profile": null
}
```

**cURL:**
```bash
curl http://localhost:8080/get-user-profile/user_123
```

---

#### `POST /sync-user-profile/{user_id}`
Partial profile update — only send the fields that changed.

**When to call:** When the backend detects profile changes (e.g. doctor changed medication).

**Request Body (only changed fields):**
```json
{
    "medications": [
        {"name": "Amlodipine", "dose": "5mg"}
    ]
}
```

**Response (200):**
```json
{
    "success": true,
    "message": "Profile synced for user user_123",
    "updated_fields": ["user:medications"]
}
```

**Response (200 — no fields):**
```json
{
    "success": false,
    "message": "No fields provided for update"
}
```

**cURL:**
```bash
curl -X POST http://localhost:8080/sync-user-profile/user_123 \
  -H "Content-Type: application/json" \
  -d '{"medications":[{"name":"Amlodipine","dose":"5mg"}]}'
```

---

### 🖼️ Image Analysis

#### `POST /analyze-medication-image`
Extract medication info from a photo of a medication box using OCR AI.

**Requires:** Ollama model `richardyoung/olmocr2:7b-q8`

**Request Body:**
```json
{
    "user_id": "user_123",
    "image_base64": "<base64 encoded image>"
}
```

**Response (200 — success):**
```json
{
    "success": true,
    "medication_name": "Panadol Extra",
    "active_ingredient": "Paracetamol + Caffeine",
    "dosage": "500mg/65mg",
    "manufacturer": "GSK",
    "expiry_date": "12/2026",
    "error": null
}
```

**Response (200 — invalid image):**
```json
{
    "success": false,
    "error": "Invalid base64 image data"
}
```

**cURL:**
```bash
curl -X POST http://localhost:8080/analyze-medication-image \
  -H "Content-Type: application/json" \
  -d '{"user_id":"user_123","image_base64":"<BASE64>"}'
```

---

#### `POST /analyze-medical-report`
Two-pass analysis of medical report images (lab tests, blood work, etc).

**Requires:** Ollama model `llama3.2-vision`

**Request Body:**
```json
{
    "user_id": "user_123",
    "image_base64": "<base64 encoded image>"
}
```

**Response (200 — success):**
```json
{
    "success": true,
    "report_id": "RPT_a1b2c3d4e5f6",
    "report_type": "blood_test",
    "report_date": "2025-01-15",
    "key_findings": ["Elevated fasting glucose", "Low HDL cholesterol"],
    "lab_values": {
        "fasting glucose": "180 mg/dL (ref: 70-100)",
        "HbA1c": "8.5%",
        "total cholesterol": "220 mg/dL"
    },
    "health_summary": "Your blood sugar levels are elevated...",
    "severity_level": "ATTENTION",
    "recommendations": ["Monitor glucose daily", "Follow up with doctor"],
    "safety_disclaimers": ["⚕️ This analysis is generated by AI..."],
    "stored_in_db": true,
    "error": null
}
```

| Severity Level | Meaning |
|---------------|---------|
| `NORMAL` | All values within acceptable ranges |
| `ATTENTION` | Some values slightly out of range, needs monitoring |
| `CRITICAL` | Significantly out of range, needs prompt medical attention |

**cURL:**
```bash
curl -X POST http://localhost:8080/analyze-medical-report \
  -H "Content-Type: application/json" \
  -d '{"user_id":"user_123","image_base64":"<BASE64>"}'
```

---

#### `GET /user-medical-reports/{user_id}`
Retrieve all previously analyzed medical reports for a user.

**Response (200):**
```json
{
    "success": true,
    "user_id": "user_123",
    "count": 2,
    "reports": [
        {
            "report_id": "RPT_a1b2c3d4e5f6",
            "report_type": "blood_test",
            "severity_level": "ATTENTION",
            "scanned_at": "2025-01-15T10:30:00",
            "lab_values": {...},
            "health_summary": "..."
        }
    ]
}
```

**cURL:**
```bash
curl http://localhost:8080/user-medical-reports/user_123
```

---

### 🤖 Agent

#### `POST /run_sse`
Send a message to the SenioCare AI agent and receive a response.

**Request Body:**
```json
{
    "app_name": "seniocare",
    "user_id": "user_123",
    "session_id": "session_abc",
    "new_message": {
        "role": "user",
        "parts": [{"text": "مرحبا، عايز اعرف وجبات مناسبة ليا"}]
    },
    "streaming": false
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `app_name` | string | ✅ | Always `"seniocare"` |
| `user_id` | string | ✅ | User's unique ID |
| `session_id` | string | ✅ | Session ID (from Create Session) |
| `new_message` | object | ✅ | Message with `role` and `parts` |
| `streaming` | boolean | ❌ | `false` = single JSON, `true` = SSE stream |

**cURL:**
```bash
curl -X POST http://localhost:8080/run_sse \
  -H "Content-Type: application/json" \
  -d '{"app_name":"seniocare","user_id":"user_123","session_id":"sess_1","new_message":{"role":"user","parts":[{"text":"مرحبا"}]},"streaming":false}'
```

---

### 📋 Sessions

#### `POST /apps/seniocare/users/{user_id}/sessions/{session_id}`
Create a new conversation session. **Must be called before `/run_sse`.**

**cURL:**
```bash
curl -X POST http://localhost:8080/apps/seniocare/users/user_123/sessions/session_abc \
  -H "Content-Type: application/json" -d '{}'
```

#### `GET /apps/seniocare/users/{user_id}/sessions/{session_id}`
Get session info and state.

#### `GET /apps/seniocare/users/{user_id}/sessions`
List all sessions for a user.

#### `DELETE /apps/seniocare/users/{user_id}/sessions/{session_id}`
Delete a specific session.

---

## Error Handling

All endpoints return HTTP 200 with a `success` field in the response body. Non-200 errors are thrown as FastAPI HTTPException:

| Status | Meaning |
|--------|---------|
| 200 | Success (check `success` field in body) |
| 422 | Validation error (missing/invalid fields) |
| 500 | Server error (check `detail` field) |

---

## Required Ollama Models

These models must be installed locally via Ollama for full functionality:

```bash
ollama pull llama3.1:8b                   # Chat & Agent responses
ollama pull richardyoung/olmocr2:7b-q8    # Medication image OCR
ollama pull llama3.2-vision               # Medical report analysis
```

**Endpoints that work WITHOUT Ollama:**
`/health`, `/set-user-profile`, `/get-user-profile`, `/sync-user-profile`, `/user-medical-reports`, `/list-apps`, `/export-openapi`, all session endpoints.

**Endpoints that REQUIRE Ollama:**
`/run_sse`, `/analyze-medication-image`, `/analyze-medical-report`
