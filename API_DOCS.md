# SenioCare API Documentation v2.0

API documentation for backend integration with the SenioCare AI service.

## Base URL

```
Local:      http://localhost:8080
Production: <your-deployed-url>
```

> **Note on `/docs`:** The auto-generated FastAPI docs at `/docs` may show schema warnings due to ADK internal types. Use this documentation instead for complete API reference.

---

## Quick Start

### 1. Start the Server
```bash
python main.py
# or with custom port
python main.py --port 3000
```

### 2. Push User Profile (first time or on update)
```bash
curl -X POST http://localhost:8080/set-user-profile/user_123 \
  -H "Content-Type: application/json" \
  -d '{
    "user_name": "Ahmed",
    "age": 72,
    "conditions": ["diabetes", "hypertension"],
    "allergies": ["shellfish"],
    "medications": [
      {"name": "Metformin", "dose": "500mg"},
      {"name": "Lisinopril", "dose": "10mg"}
    ],
    "mobility": "limited"
  }'
```

### 3. Create a Session (new chat)
```bash
curl -X POST http://localhost:8080/apps/seniocare/users/user_123/sessions/session_001 \
  -H "Content-Type: application/json" \
  -d "{}"
```

### 4. Send a Message
```bash
curl -X POST http://localhost:8080/run_sse \
  -H "Content-Type: application/json" \
  -d '{
    "app_name": "seniocare",
    "user_id": "user_123",
    "session_id": "session_001",
    "new_message": {
      "role": "user",
      "parts": [{"text": "ممكن تقترح عليا وجبة فطار صحية؟"}]
    },
    "streaming": false
  }'
```

---

## Architecture & Data Flow

### Session & Memory System

```
┌─────────────────────────────────────────────────────────────┐
│                     Flutter App (Frontend)                   │
│  • User registration → sends profile to backend             │
│  • Chat UI → sends messages via backend                     │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                  Backend Server (Firebase/REST)              │
│  • Stores user profiles in main DB                          │
│  • Manages session IDs (creates new for each chat)          │
│  • On registration/profile change:                          │
│    → POST /set-user-profile/{user_id}                       │
│  • On each message:                                         │
│    → POST /run_sse (with user_id + session_id)              │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│            SenioCare AI Service (this server)                │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  DatabaseSessionService (sessions.db - SQLite)        │   │
│  │  • Stores session events (chat history)               │   │
│  │  • Stores state with prefix scoping:                  │   │
│  │    - user: prefix → persists across ALL sessions      │   │
│  │    - no prefix   → persists within ONE session        │   │
│  │    - temp: prefix → ONE invocation only               │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  InMemoryMemoryService (long-term memory)             │   │
│  │  • Archives past sessions for cross-session recall    │   │
│  │  • Lost on server restart (dev mode)                  │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  3-Agent Pipeline                                     │   │
│  │  1. Orchestrator → Safety + Intent + Planning         │   │
│  │  2. Feature Agent → Tool Calls + Decisions            │   │
│  │  3. Formatter → Egyptian Arabic response              │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### State Key Reference

| Key | Prefix | Scope | Example |
|-----|--------|-------|---------|
| `user:user_id` | `user:` | All sessions for this user | `"user_firebase_123"` |
| `user:user_name` | `user:` | All sessions for this user | `"Ahmed"` |
| `user:age` | `user:` | All sessions for this user | `72` |
| `user:conditions` | `user:` | All sessions for this user | `["diabetes", "hypertension"]` |
| `user:medications` | `user:` | All sessions for this user | `[{"name":"Metformin","dose":"500mg"}]` |
| `user:allergies` | `user:` | All sessions for this user | `["shellfish"]` |
| `user:mobility` | `user:` | All sessions for this user | `"limited"` |
| `conversation_turn_count` | *(none)* | Current session only | `3` |

---

## Endpoints

### Health Check
```http
GET /health
```

**Response:**
```json
{
    "status": "healthy",
    "service": "seniocare-api",
    "version": "2.0.0",
    "session_db": "sqlite+aiosqlite:///./sessions.db",
    "memory_service": "InMemoryMemoryService"
}
```

---

### List Available Agents
```http
GET /list-apps
```

**Response:**
```json
["seniocare"]
```

---

### Set User Profile ⭐ NEW
```http
POST /set-user-profile/{user_id}
Content-Type: application/json
```

Push user health profile to persist across ALL sessions. Call this:
- **Once** after user registration
- **Again** when user profile changes (use `/sync-user-profile` for partial updates)

**Request Body:**
```json
{
    "user_name": "Ahmed",
    "age": 72,
    "conditions": ["diabetes", "hypertension"],
    "allergies": ["shellfish"],
    "medications": [
        {"name": "Metformin", "dose": "500mg"},
        {"name": "Lisinopril", "dose": "10mg"}
    ],
    "mobility": "limited"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| user_name | string | Yes | User's display name |
| age | integer | Yes | User's age |
| conditions | string[] | No | Health conditions (e.g., diabetes, hypertension) |
| allergies | string[] | No | Food allergies (e.g., shellfish, peanuts) |
| medications | object[] | No | Array of `{name, dose}` medication objects |
| mobility | string | No | `"limited"`, `"moderate"`, or `"active"` (default: `"limited"`) |

**Response:**
```json
{
    "success": true,
    "message": "Profile saved for user user_123",
    "user_id": "user_123",
    "profile_keys": [
        "user:user_id", "user:user_name", "user:age",
        "user:conditions", "user:allergies", "user:medications",
        "user:mobility"
    ]
}
```

---

### Get User Profile ⭐ NEW
```http
GET /get-user-profile/{user_id}
```

Retrieve user health profile data that was previously saved.

**Response (profile exists):**
```json
{
    "success": true,
    "user_id": "user_123",
    "profile": {
        "user_id": "user_123",
        "user_name": "Ahmed",
        "age": 72,
        "conditions": ["diabetes", "hypertension"],
        "allergies": ["shellfish"],
        "medications": [
            {"name": "Metformin", "dose": "500mg"},
            {"name": "Lisinopril", "dose": "10mg"}
        ],
        "mobility": "limited"
    }
}
```

**Response (no profile):**
```json
{
    "success": false,
    "message": "No profile found for user user_456. Call /set-user-profile first.",
    "profile": null
}
```

---

### Sync User Profile (Partial Update) ⭐ NEW
```http
POST /sync-user-profile/{user_id}
Content-Type: application/json
```

Update only the changed fields when the backend detects profile changes.
Only send the fields that changed — other fields remain unchanged.

**Example: Doctor changed medication**
```json
{
    "medications": [
        {"name": "Metformin", "dose": "500mg"},
        {"name": "Amlodipine", "dose": "5mg"}
    ]
}
```

**Example: New allergy discovered**
```json
{
    "allergies": ["shellfish", "peanuts"]
}
```

**Response:**
```json
{
    "success": true,
    "message": "Profile synced for user user_123",
    "updated_fields": ["user:medications"]
}
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
| user_id | string | Your user's unique ID (same as used in `/set-user-profile`) |
| session_id | string | Unique conversation session ID (UUID recommended) |

---

### List User Sessions
```http
GET /apps/{app_name}/users/{user_id}/sessions
```

Returns all active sessions for a user. Use this for a "chat history" screen.

---

### Get Session Details
```http
GET /apps/{app_name}/users/{user_id}/sessions/{session_id}
```

Returns session details including events (chat history) and state.

---

### Delete Session
```http
DELETE /apps/{app_name}/users/{user_id}/sessions/{session_id}
```

Delete a conversation. The `user:`-prefixed state (profile data) is NOT deleted.

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
| user_id | string | Yes | User identifier (must match `/set-user-profile`) |
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

> **Note:** Requires `llama3.2-vision` model. Run `ollama pull llama3.2-vision` if not installed.

---

## Backend Integration Guide

### Complete Flow: User Registration → First Chat

```
1. User registers in Flutter app
   ↓
2. Backend saves user data to Firebase/main DB
   ↓
3. Backend calls: POST /set-user-profile/{user_id}
   Body: { user_name, age, conditions, allergies, medications, mobility }
   → Profile persisted in sessions.db with user: prefix
   ↓
4. User opens chat tab
   ↓
5. Backend generates UUID for session_id
   Backend calls: POST /apps/seniocare/users/{user_id}/sessions/{session_id}
   → New session created (user: profile auto-loaded)
   ↓
6. User sends message
   ↓
7. Backend calls: POST /run_sse
   Body: { app_name: "seniocare", user_id, session_id, new_message }
   → Agent has full access to user profile + chat history
   ↓
8. Agent responds with personalized recommendation
```

### Complete Flow: User Opens New Chat Tab

```
1. User taps "New Chat" in Flutter app
   ↓
2. Backend generates NEW session_id (UUID)
   Backend calls: POST /apps/seniocare/users/{user_id}/sessions/{new_session_id}
   → New session created
   → User profile (user: prefix) automatically available (same user_id)
   → Previous chat history NOT available (different session)
   → Long-term memory can recall past conversations
   ↓
3. User sends message → POST /run_sse → Agent responds
```

### Complete Flow: Profile Update (Doctor Changes Medication)

```
1. Doctor changes patient's medication in the backend
   ↓
2. Backend detects change, calls:
   POST /sync-user-profile/{user_id}
   Body: { "medications": [{"name": "Amlodipine", "dose": "5mg"}] }
   → Only medications updated, other fields unchanged
   ↓
3. Next time user sends a message in ANY session:
   → Agent automatically uses updated medications
   → Drug interaction checks use new medications
```

### Complete Flow: Resuming a Past Conversation

```
1. User selects past chat from history screen
   ↓
2. Backend calls: GET /apps/seniocare/users/{user_id}/sessions
   → Gets list of all sessions with timestamps
   ↓
3. User selects a session
   ↓
4. Backend calls: GET /apps/seniocare/users/{user_id}/sessions/{session_id}
   → Gets full chat history (events) and session state
   ↓
5. Frontend displays chat history
   ↓
6. User sends new message in the SAME session
   → POST /run_sse with the SAME session_id
   → Agent has access to full previous conversation context
```

---

## What the Backend Needs to Store

| Data | Where | Purpose |
|------|-------|---------|
| `user_id` | Backend DB | Primary key for user |
| `session_id` (current) | Backend memory/DB | Track active conversation |
| `session_id` (list) | Backend DB or call `GET /sessions` | Chat history screen |
| `profile_synced` flag | Backend DB | Track if profile was sent to AI service |

The backend does NOT need to store:
- Chat messages (stored in `sessions.db` by ADK)
- User profile for AI (stored in `sessions.db` with `user:` prefix)
- Agent responses (stored as events in `sessions.db`)

---

## Web UI Testing

Visit http://localhost:8080 in browser for interactive testing via ADK web UI.
When using `adk web`, test user data is auto-populated (no `/set-user-profile` needed).
