# SenioCare

An AI healthcare assistant for elderly Egyptian users. A three-stage agent pipeline screens each message for safety, gathers data from a health database, and replies in Egyptian Arabic.

Built on the [Google Agent Development Kit](https://google.github.io/adk-docs/) (ADK 1.22.0) with FastAPI and PostgreSQL. Models run locally through Ollama.

> **Status: graduation project, not production software.** It has no authentication, and a documented set of correctness and safety defects. Read [`docs/AUDIT.md`](docs/AUDIT.md) before deploying it anywhere or connecting it to real patient data.

---

## What it does

A user sends a message in Egyptian Arabic. It passes through three agents in sequence:

1. **Orchestrator** — classifies safety (`EMERGENCY` / `BLOCKED` / `ALLOWED`), classifies intent, and writes a tool-calling plan. No tools.
2. **Feature** — executes the plan against 10 tools, picks the best option, packages the result.
3. **Formatter** — renders the package as warm Egyptian Arabic using per-intent templates.

A fourth agent, run separately, generates health reports on a schedule or on demand and pushes notifications to caregivers.

### Who it's for

- **Elderly users** — meal and exercise recommendations filtered against their conditions, allergies, and medications; symptom guidance; health questions.
- **Caregivers** — push notifications when a scheduled report is ready or an emergency is detected in conversation.

### Capabilities

| Capability | Where |
|---|---|
| Safety screening and emergency detection | `seniocare/sub_agents/orchestrator_agent.py:67-116` |
| Condition- and allergy-aware meal recommendations | `seniocare/tools/nutrition.py:8` |
| Drug–food interaction checking | `seniocare/tools/interactions.py:7` |
| Symptom assessment with severity ranking | `seniocare/tools/symptoms.py:8` |
| Mobility-aware exercise recommendations | `seniocare/tools/exercise.py:8` |
| Cross-session food and exercise preferences | `seniocare/tools/preferences.py:11` |
| Web, YouTube, and medical search (SerpAPI) | `seniocare/tools/web_search.py` |
| Storage of medical-report analysis results | `seniocare/tools/image_tools.py:16` |
| Scheduled + emergency health reports | `seniocare/sub_agents/report_agent.py`, `app/scheduler.py` |
| Caregiver push notifications (FCM) | `app/notifications.py` |

**Multimodal note.** Images are handled natively by the model through `/run_sse`; there are no image-upload endpoints. `store_medical_report` persists the model's extracted findings — it does not perform analysis (`seniocare/tools/image_tools.py:1-6`).

---

## Architecture

```mermaid
graph LR
    U(["User"]) --> API["FastAPI<br/>/run_sse"]
    API --> CB["before_agent_callback<br/>load profile + history"]
    CB --> O["1 · Orchestrator<br/>safety + intent + plan"]
    O --> F["2 · Feature<br/>tools + decision"]
    F --> M["3 · Formatter<br/>Egyptian Arabic"]
    M --> U
    F --> T["Tools"]
    T --> DB[("PostgreSQL")]
    T --> S[("SerpAPI")]
    M --> AC["after_agent_callback"]
    AC -->|"intent == emergency"| R["Report agent"]
    R --> FCM["FCM → caregivers"]
```

All three stages run on **every** request. There is no conditional bypass — blocked and emergency messages still traverse all three. Full call graph and state model: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

### Agents

| Agent | Model | Role |
|---|---|---|
| Orchestrator | `ollama_chat/gemma4:e4b` | Safety, intent, planning |
| Feature | `ollama_chat/gemma4:e4b` | Tool execution and selection |
| Formatter | `ollama_chat/gemma4:e4b` | Egyptian Arabic rendering |
| Report | `ollama_chat/gemma4:e4b` | Health report generation |

The model name is hardcoded in each agent file and cannot be changed by configuration. See [Known limitations](#known-limitations).

### Tools

The ten tools registered on the Feature Agent (`seniocare/sub_agents/feature_agent.py:312-323`):

| Tool | Does |
|---|---|
| `get_meal_options` | Meals filtered by condition nutrient limits and allergens |
| `get_meal_recipe` | Full recipe for a selected meal |
| `check_drug_food_interaction` | Screens foods against the user's medications |
| `assess_symptoms` | Matches symptoms to diseases with severity and precautions |
| `get_exercises` | Exercises for the user's mobility level, minus contraindications |
| `save_user_preference` | Persists likes/dislikes to cross-session state |
| `search_web` | General web search with content extraction |
| `search_youtube` | Video tutorials |
| `search_medical_info` | Search restricted to trusted medical domains |
| `store_medical_report` | Stores medical-report findings to the database |

---

## Getting started

### Prerequisites

- **Python 3.10+**
- **[Ollama](https://ollama.com/)** with the model pulled:
  ```bash
  ollama pull gemma4:e4b
  ```
  Required. All four agents call it and there is no hosted fallback.
- **PostgreSQL** — two databases (or two schemas): one for tools data, one for ADK sessions. [Neon](https://neon.tech/) works.
- *Optional:* **SerpAPI key** — without it the three search tools return a structured error and the rest of the pipeline continues.
- *Optional:* **Firebase service-account JSON** — without it push notifications are skipped with a warning (`app/notifications.py:74-79`).

### Install

```bash
git clone <your-repo-url>
cd SenioCare
pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
```

| Variable | Required | Purpose |
|---|---|---|
| `APP_DATABASE_URL` | **Yes** | Tools database. Read at `seniocare/data/database.py:40` |
| `SESSION_DB_URL` | **Yes** | ADK session store. Read at `app/config.py:43`. Falls back to local SQLite if unset |
| `SERPAPI_KEY` | No | Web/YouTube/medical search. `seniocare/tools/web_search.py:34` |
| `FIREBASE_CREDENTIALS_PATH` | No | FCM service account. `app/config.py:29` |
| `PORT` | No | Server port, default 8080. `main.py:114` |
| `TEST_DATABASE_URL` | No | Test database. **Fixtures DROP all tables — never point this at anything you care about** |

`SESSION_DB_URL` is rewritten at `app/config.py:45-59` to add the `+asyncpg` prefix and strip `sslmode` / `channel_binding`, which asyncpg rejects as URL parameters. Supply a normal `postgresql://` URL.

### Run

```bash
python main.py
```

Serves on `http://localhost:8080`. Swagger UI at `/docs`. Tables are created and seeded on first import (`seniocare/agent.py:27-30`).

```bash
python main.py --port 3000
```

The ADK development web UI is enabled (`SERVE_WEB_INTERFACE = True`, `app/config.py:85`).

---

## API

### Chat

`POST /run_sse` — provided by ADK. This is the endpoint the client app uses.

```json
{
  "app_name": "seniocare",
  "user_id": "elder_123",
  "session_id": "<from /create-session>",
  "new_message": {"role": "user", "parts": [{"text": "عايز أكلة كويسة على الغدا"}]},
  "streaming": false
}
```

Responses stream as SSE events. Render events whose `author` is `formatter_agent` — that is the only user-facing stage.

> `/run_sse` does **not** appear in `/docs`; the custom OpenAPI generator omits it (`app/openapi.py:13-23`).

### Custom endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Static status and version. Does not check DB or Ollama |
| `POST` | `/create-session` | Create a session, returns `session_id` |
| `GET` | `/chat-history/{user_id}` | List conversations with headlines |
| `GET` | `/chat-history/{user_id}/{session_id}` | Full turns for one conversation |
| `POST` | `/set-user-profile/{user_id}` | Create/replace the health profile |
| `GET` | `/get-user-profile/{user_id}` | Read the health profile |
| `POST` | `/sync-user-profile/{user_id}` | Partial profile update |
| `POST` | `/register-caregiver-fcm` | Register a caregiver device token |
| `POST` | `/reports/generate` | Generate a report (`daily`/`weekly`/`monthly`/`emergency`) |
| `GET` | `/reports/{user_id}` | List a user's reports |
| `GET` | `/reports/{user_id}/{report_id}` | One report in full |
| `GET` | `/reports/medical/{user_id}` | Stored medical-report analyses — **currently returns 404 for all input** ([C-16](docs/AUDIT.md)) |
| `POST` | `/reports/seed` | Insert sample data. Development only — unauthenticated, and `clear=true` deletes data |

**No endpoint requires authentication.** `user_id` is an unauthenticated parameter throughout.

---

## Testing

```bash
# Unit and tool tests. Requires a disposable PostgreSQL database —
# the session fixture calls reset_database(), which DROPs every table.
export TEST_DATABASE_URL='postgresql://user:pass@host/seniocare_test?sslmode=require'
python -m pytest tests/unit tests/test_database_tools.py -v
```

```bash
# Integration tests. Skipped automatically unless a server is on :8080.
python main.py &
python -m pytest tests/integration/ -v
```

**Current state, measured:**

```
76 passed, 48 skipped in 107.89s
```

Three caveats worth knowing before you trust a green run:

- **The full suite does not collect.** `tests/integration/test_multi_tool_flows.py` imports `seniocare.tools.medication`, which no longer exists. Use `--ignore` on that file, or fix the import.
- **All 48 integration tests skip** when no server is running (`tests/integration/test_api_endpoints.py:37-40`). A green run may mean nothing was exercised.
- **`pytest.ini` sets `asyncio_mode` and `timeout`, but neither plugin is installed**, so both options are silently ignored and async tests do not run as intended.

Unit tests reach the live database, which is why the suite takes ~108 seconds.

### Agent evaluation

Scaffolding lives in [`evals/`](evals/) — 48 cases in Egyptian Arabic across every route the code can take.

```bash
python evals/runner.py --dry-run          # validate cases
python evals/runner.py                    # run in-process
python evals/runner.py --filter emergency-
```

**Assertion logic is deliberately stubbed.** The harness records outputs, tool calls, and latencies, and asserts nothing. See [`evals/schema.md`](evals/schema.md), including the categories that cannot be automated and need human review.

---

## Safety and medical disclaimer

For **informational and support purposes only**.

- It does **not** diagnose. Diagnosis requests are refused (`orchestrator_agent.py:96`).
- It does **not** prescribe or adjust dosages (`orchestrator_agent.py:97-99`).
- It screens for emergency language and directs users to emergency services (`orchestrator_agent.py:76-85`).
- It advises consulting a qualified provider.

**The safety mechanisms have documented defects.** Emergency escalation depends on a single regex matching one exact token, and symptom matching produces both false emergencies and — plausibly — missed ones for Arabic input. Do not rely on this system for real medical safety. See [`docs/AUDIT.md`](docs/AUDIT.md), findings C-02, C-03, C-12, C-13.

---

## Known limitations

Honest summary. Full detail in [`docs/AUDIT.md`](docs/AUDIT.md).

**Security**
- No authentication on any endpoint; `user_id` is caller-supplied. Any user's medical profile and conversations can be read or overwritten.
- CORS is `"*"`.
- No rate limiting, no audit log, no data-deletion path.

**Correctness**
- Emergency routing is enforced by prompt text, not control flow.
- `SAFETY_STATUS` is never read by any code; only `INTENT` is parsed.
- Tool re-entrancy guards persist for the whole session, so from the second turn onward guarded tools — including drug-interaction screening — silently return nothing.
- A fabricated patient profile is injected whenever a real one is missing.
- Preference conflict-resolution silently no-ops for dislikes.
- Report date ranges are ignored for conversation data; four aggregation fields are always empty.
- `GET /reports/medical/{user_id}` is shadowed by an earlier route and always 404s.

**Operations**
- No Docker, no CI, no migrations, no linter, no type checker.
- No tracing, metrics, or token/cost accounting; the two configured loggers emit nothing.
- Synchronous database and HTTP calls block the async event loop.
- No connection pooling; no timeout on any LLM call.
- Dependencies are unpinned (`>=` only), with no lock file.

**Configuration**
- The model name is hardcoded in four files with no environment override and no `OLLAMA_API_BASE` setting.
- The Orchestrator prompt documents two tools that do not exist and two models that are not configured.

---

## Project layout

```
main.py                     FastAPI entry point
app/
  config.py                 Env parsing, shared DatabaseSessionService
  openapi.py                Custom OpenAPI schema
  notifications.py          FCM push notifications
  scheduler.py              APScheduler report jobs
  routers/                  health, sessions, chat_history, user_profile, reports
  schemas/                  Pydantic request models
seniocare/
  agent.py                  Root SequentialAgent
  callbacks.py              before/after agent callbacks
  sub_agents/               orchestrator, feature, formatter, report
  tools/                    10 agent tools
  data/
    database.py             Schema, seeding, connections
    seeds/*.json            Seed data
tests/                      unit + integration
evals/                      Evaluation scaffolding (assertions stubbed)
docs/
  AUDIT.md                  Findings, severities, citations
  ARCHITECTURE.md           Call graph, state flow, limitations
  INSTRUMENTATION.md        Measurement plan
```

---

## License

[MIT](LICENSE)
