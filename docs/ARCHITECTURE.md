# SenioCare — Architecture

**Scope:** what the code does on branch `feat/hardening`. The pre-hardening state is preserved in `docs/AUDIT.md` (findings are referenced here by id). Nothing planned-but-unbuilt is described.

**Version:** `APP_VERSION = "3.1.0"` (`app/config.py`) · ADK 1.22.0

---

## 1. System overview

SenioCare is a FastAPI service wrapping a three-stage Google ADK agent pipeline with a routing decision made in code between stages 1 and 2. A user message enters over `/run_sse`, is authorised, passes through the Orchestrator, is routed, optionally passes through the Feature Agent, and returns an Egyptian Arabic response from the Formatter. A separate Report agent generates health reports on a schedule, on demand, or on an emergency.

```mermaid
graph TB
    subgraph client [Client]
        Flutter[Flutter app · Firebase sign-in]
    end

    subgraph api [FastAPI · main.py]
        Auth["AuthMiddleware · app/auth.py<br/>Bearer Firebase ID token → uid<br/>uid == user_id or uid ∈ caregiver_ids"]
        Trace["trace middleware<br/>X-Trace-Id · http_request record"]
        SSE["POST /run_sse (ADK)"]
        Custom["Custom routers · app/routers/*"]
    end

    subgraph pipeline [Chat pipeline · SenioCarePipeline · seniocare/pipeline.py]
        Before["populate_user_data<br/>callbacks.py"]
        Orch["1 · orchestrator_agent<br/>→ orchestrator_result"]
        Route{"route()<br/>seniocare/routing.py<br/>→ safety_status, intent, route, parse_ok"}
        Feat["2 · feature_agent<br/>→ feature_result"]
        Fmt["3 · formatter_agent<br/>→ final_response"]
        After["auto_save_to_memory<br/>headline · emergency trigger · turn record"]
    end

    subgraph tools [Tools · seniocare/tools/ · threaded()]
        DBTools["get_meal_options · get_meal_recipe<br/>check_drug_food_interaction<br/>assess_symptoms · get_exercises<br/>store_medical_report"]
        StateTools["save_user_preference"]
        WebTools["search_web · search_youtube<br/>search_medical_info"]
    end

    subgraph reports [Report pipeline]
        Sched["APScheduler · app/scheduler.py"]
        RptAgent["report_agent → report_result"]
        FCM["Firebase Cloud Messaging"]
    end

    subgraph obs [Observability · seniocare/observability.py]
        Emit["emit() → JSON log line<br/>+ llm_traces (Postgres sink)"]
    end

    subgraph data [Persistence]
        SessDB[("Session DB · Postgres · asyncpg<br/>ADK DatabaseSessionService")]
        ToolDB[("Tools DB · Postgres · psycopg2 pool<br/>9 tables + llm_traces")]
    end

    Flutter --> Auth --> Trace --> SSE
    Trace --> Custom
    SSE --> Before --> Orch --> Route
    Route -->|ALLOWED / unparseable| Feat --> Fmt
    Route -->|BLOCKED / EMERGENCY<br/>synthesised feature_result| Fmt
    Fmt --> After
    Feat --> DBTools & StateTools & WebTools
    DBTools --> ToolDB
    Before -.reads.-> SessDB
    After -.writes.-> SessDB
    After -->|"EMERGENCY (status or intent)<br/>tracked background task"| RptAgent
    Sched --> RptAgent
    Custom --> RptAgent
    RptAgent --> ToolDB
    RptAgent --> FCM
    WebTools --> SerpAPI[(SerpAPI)]
    Orch & Feat & Fmt & RptAgent -. model/tool/stage callbacks .-> Emit
    After -. turn record .-> Emit
    Emit --> ToolDB
```

Compared with the audited version: the bypass edge now exists (it is a Python `if`, not a prompt instruction); every route is behind auth; tools run in a thread pool; every stage is measured.

---

## 2. Call graph — one chat request

| # | Hop | Where |
|---|---|---|
| 1 | `POST /run_sse` — route provided by ADK's `get_fast_api_app` | `main.py` |
| 1a | Auth middleware verifies the bearer token, reads `user_id` from the body, checks uid/caregiver allow-list; 401/403 otherwise | `app/auth.py:AuthMiddleware` |
| 1b | Trace middleware assigns `X-Trace-Id`, times the request | `main.py:trace_requests` |
| 2 | ADK loads the session from Postgres | `app/config.py` |
| 3 | `before_agent_callback` → `populate_user_data`: starts the turn record; injects the test profile only with `DEV_TEST_USER=1`, otherwise sets `profile_missing`; increments `conversation_turn_count`; builds `conversation_history` | `seniocare/callbacks.py` |
| 4 | **Stage 1 — Orchestrator.** Prompt interpolates `{conversation_history}` and `{user:preferences}`; writes `orchestrator_result` | `seniocare/sub_agents/orchestrator_agent.py` |
| 5 | **Routing.** `route(orchestrator_result)` parses `SAFETY_STATUS` and `INTENT` tolerantly; writes `safety_status`, `intent`, `route`, `orchestrator_parse_ok`; on BLOCKED/EMERGENCY also writes a synthesised `feature_result` (`RESPONSE_TYPE: emergency` + the Orchestrator's `EMERGENCY_MESSAGE`, or the blocked equivalent) | `seniocare/routing.py`, `seniocare/pipeline.py` |
| 6 | **Stage 2 — Feature** (ALLOWED or unparseable only). Prompt interpolates `{orchestrator_result}`; ADK dispatches tool calls; each tool runs in a thread via `threaded()`; per-turn guards stop duplicates; writes `feature_result` | `feature_agent.py`, `tools/_async.py`, `tools/_guards.py` |
| 7 | **Stage 3 — Formatter.** Prompt interpolates `{feature_result}`; writes `final_response` | `formatter_agent.py` |
| 8 | `after_agent_callback` → `auto_save_to_memory`: headline on turn 1; if `safety_status == EMERGENCY` or `intent == emergency`, spawn the report + FCM task (kept in `_BACKGROUND_TASKS` with a done-callback); emit the `turn` record | `seniocare/callbacks.py` |
| 9 | SSE events stream to the client | — |

Each `LlmAgent` also runs the observability callbacks: `before/after_model` (latency, tokens, cost, finish reason, requested tools), `before/after_tool` (latency, status, `already_called`), `before/after_agent` (stage latency, output size, parse success).

**LLM round-trips per turn:** three on the ALLOWED path, two on the BLOCKED/EMERGENCY path.

---

## 3. Stage responsibilities

### Stage 1 — Orchestrator (`seniocare/sub_agents/orchestrator_agent.py`)

Reasoning only; no tools bound. Emits labelled text: `SAFETY_STATUS`, `INTENT`, `USER_CONTEXT`, `TASK_PLAN`, and for the safety paths `BLOCKED_REASON` / `BLOCKED_MESSAGE` / `EMERGENCY_MESSAGE`. Both `SAFETY_STATUS` and `INTENT` are read by `route()` with a parser tolerant of markdown bold, case and full-width colons (C-03). The tool catalogue in the prompt matches the ten real tools (C-06).

### Routing (`seniocare/routing.py`)

Pure function. Decision table:

| Orchestrator says | Feature runs | `feature_result` |
|---|---|---|
| `EMERGENCY` by status **or** intent | no | synthesised emergency relay, default message includes 123 |
| `BLOCKED` by status **or** intent | no | synthesised blocked relay |
| `ALLOWED` | yes | written by the Feature Agent |
| unparseable | yes (fail open) | written by the Feature Agent; `orchestrator_parse_ok=false` |

### Stage 2 — Feature (`seniocare/sub_agents/feature_agent.py`)

Executes the plan with the ten tools, selects, packages `RESPONSE_TYPE` + data + `PRESENTATION_PLAN`. Response types cover every intent (meal, exercise, symptom, medical Q&A, emotional support, routine, preference, both image intents).

### Stage 3 — Formatter (`seniocare/sub_agents/formatter_agent.py`)

Renders Egyptian Arabic from templates; one template per response type, including the emergency and blocked relays.

### Report agent (`seniocare/sub_agents/report_agent.py`)

Invoked by `seniocare/tools/reports.py::generate_report` with an aggregate built from: the profile (session state), conversation facts extracted from the session events **inside the report period** (symptoms reported and assessed, meals and exercises returned by tools, harmful interactions, emergency turns), stored medical-report analyses, and a `data_coverage` block naming the fields with no data. Only the agent's final response is kept; an unparseable `STATUS` is stored as `unknown` and recorded.

---

## 4. Model configuration

All four agents call `get_model()` in `seniocare/model.py`, which builds one `LiteLlm` from the environment:

| Variable | Effect |
|---|---|
| `MODEL_NAME` | LiteLLM model string; provider prefix decides the client (`ollama_chat/`, `openai/`, `hosted_vllm/`, `gemini/`, …). Default `ollama_chat/gemma4:e4b` |
| `MODEL_API_BASE` | Endpoint for self-hosted / OpenAI-compatible servers. Ollama root for `ollama_chat/`, `…/v1` for `openai/` and `hosted_vllm/` |
| `MODEL_API_KEY` | Provider key. For `openai/` and `hosted_vllm/` with a base URL and no key, a placeholder is sent because the client refuses an empty key |
| `MODEL_TIMEOUT_S` | Per-request timeout forwarded to `litellm.completion` (default 120) |
| `MODEL_TEMPERATURE`, `MODEL_MAX_TOKENS`, `MODEL_EXTRA_JSON` | Sampling parameters; unset means provider default |

`LiteLlm.__init__(model, **kwargs)` stores every kwarg and merges it into each `litellm.completion` call, which is how the base URL, key, timeout and sampling parameters reach the provider. Where the model runs is irrelevant to the tools: ADK serialises the tool functions into JSON schemas, the model returns tool-call requests, ADK executes the Python in this process.

`GET /health` reports the resolved configuration and probes the model server; `scripts/check_model.py --adk` runs a completion, a tool call, a round trip and ADK's tool loop with the exact agent settings.

---

## 5. State flow

### Storage tiers

| Tier | Prefix | Lifetime | Backed by |
|---|---|---|---|
| Session state | none | one session | Postgres via ADK |
| User state | `user:` | all sessions for that user | Postgres via ADK |
| Invocation-only | `temp:` | one invocation, never merged into `session.state` | in the event's own delta only |
| Event log | — | one session | Postgres via ADK |
| Tools data, traces | — | permanent | Postgres via `psycopg2` |

### Keys in use

**`user:`-scoped** — written by `POST /set-user-profile`, read by tools, prompts and the auth middleware:
`user:user_id`, `user:user_name`, `user:age`, `user:weight`, `user:height`, `user:gender`, `user:chronicDiseases`, `user:allergies`, `user:medications`, `user:mobilityStatus`, `user:bloodType`, `user:caregiver_ids` (caregiver **allow-list**), `user:caregivers` (device tokens, caregiver-written), `user:preferences`.

**Session-scoped:**

| Key | Written by | Read by |
|---|---|---|
| `orchestrator_result` | Orchestrator | Feature prompt, `route()`, callbacks |
| `safety_status`, `intent`, `route`, `orchestrator_parse_ok` | `SenioCarePipeline` | emergency trigger, turn record, evals |
| `feature_result` | Feature Agent, or the pipeline on the bypass path | Formatter prompt |
| `final_response` | Formatter | streamed to client |
| `conversation_turn_count` | `populate_user_data` | tool guards, headline |
| `conversation_history` | `populate_user_data` | Orchestrator prompt |
| `session_headline`, `session_preview` | `auto_save_to_memory` | chat history |
| `profile_missing` | `populate_user_data` (no profile, `DEV_TEST_USER` unset) | — |
| `emergency_task_started` | emergency trigger | — |
| `_meal_tool_called` … `_store_report_tool_called` | tools, value = turn number | tools (`_guards.py`) |

**Why the guards store the turn number, not a `temp:` flag.** ADK's `BaseSessionService._update_session_state` skips `temp:` keys, so a `temp:` flag set by one tool call is invisible to the next tool call in the same turn. The turn-number guard blocks duplicates within a turn and resets naturally on the next one.

### The temp-session pattern

Reading or writing `user:`-scoped state outside an agent invocation is done by creating a throwaway session, reading its state, and deleting it (`user_profile.py`, `reports.py`, `scheduler.py`, `tools/reports.py`, `auth.py`). All temp session ids start with `_` and are hidden from chat history. It costs two or three round-trips per read; the auth middleware caches caregiver allow-lists for 60 s.

---

## 6. Data model

### Tools database — `seniocare/data/database.py`

| Table | Purpose | Seed rows |
|---|---|---|
| `meals` | Meals with nutrition and recipes | 19 |
| `condition_dietary_rules` | Nutrient ceilings per condition | — |
| `drug_food_interactions` | Drug↔food effects and severity | 20 |
| `disease_symptoms` | Disease→symptom lists with severity | 15 (81 phrases; Arabic synonyms in `seeds/symptom_synonyms_ar.json`) |
| `disease_precautions` | Precautions per disease | — |
| `food_allergens` | Food→allergen category | 23 |
| `exercises` | Exercises by mobility level | — |
| `medical_reports` | Stored image-analysis results | — |
| `health_reports` | Generated reports | — |
| `llm_traces` | One row per LLM call, tool call, stage, turn, HTTP request (`seniocare/observability.py`) | — |

Columns are `TEXT` (JSON payloads and timestamps included) except `llm_traces`. Schema is `CREATE TABLE IF NOT EXISTS` at import; there is no migration tool.

**Connections** (`database.py`): a per-process pool hands out proxies whose `close()` returns the connection; connects use libpq's `connect_timeout` and keepalives; query waits run through a psycopg2 wait callback with a client-side deadline (`APP_DATABASE_QUERY_TIMEOUT_S`). Background: `docs/FINDINGS.md` F-01.

### Session database

Managed by ADK's `DatabaseSessionService` (`app/config.py`). The URL is rewritten to add the `+asyncpg` prefix and strip `sslmode` / `channel_binding`. No memory service is configured; cross-session continuity is carried by `user:` state.

---

## 7. HTTP surface

Middleware order (outermost first): `AuthMiddleware` → trace middleware → app. Public paths: `/`, `/health`, `/docs*`, `/openapi.json`, `/redoc`, `/list-apps`. Admin-only (uid ∈ `ADMIN_UIDS`): `/metrics*`, `/dev-ui*`, `/debug/*`, `/builder/*`, ADK eval routes.

| Method | Path | Handler |
|---|---|---|
| GET | `/health` | `app/routers/health.py` — config, auth mode, DB and model probes |
| GET | `/metrics/summary` | `app/routers/metrics.py` — aggregates from `llm_traces` |
| POST | `/create-session` | `app/routers/sessions.py` |
| GET | `/chat-history/{user_id}` | `app/routers/chat_history.py` |
| GET | `/chat-history/{user_id}/{session_id}` | `app/routers/chat_history.py` |
| POST | `/set-user-profile/{user_id}` | `app/routers/user_profile.py` |
| GET | `/get-user-profile/{user_id}` | `app/routers/user_profile.py` |
| POST | `/sync-user-profile/{user_id}` | `app/routers/user_profile.py` |
| POST | `/register-caregiver-fcm` | `app/routers/user_profile.py` — per-elder lock |
| POST | `/reports/generate` | `app/routers/reports.py` |
| GET | `/reports/medical/{user_id}` | `app/routers/reports.py` — registered before the parametric route (C-16) |
| POST | `/reports/seed` | `app/routers/reports.py` — only when `AUTH_MODE=off` |
| GET | `/reports/{user_id}` | `app/routers/reports.py` |
| GET | `/reports/{user_id}/{report_id}` | `app/routers/reports.py` |

ADK-provided: `/run_sse`, `/run`, `/list-apps`, `/apps/{app}/users/{user}/sessions/...`, the dev UI. `/run_sse` is documented manually in `app/openapi.py`.

**Lifecycle.** `main.py` wraps ADK's lifespan: on startup it starts the Postgres trace sink, the APScheduler jobs and Firebase Admin; on shutdown it stops the scheduler, flushes the sink and closes the DB pool. (`@app.on_event` handlers were silently ignored under ADK's lifespan — `docs/FINDINGS.md` F-02.)

---

## 8. Observability

`seniocare/observability.py`: one `emit(kind, **fields)` sink; JSON lines on stdout (`configure_logging()`), a batching Postgres sink into `llm_traces`, and in-memory subscribers (the eval harness). Record kinds: `llm_call`, `tool_call`, `stage`, `turn`, `serpapi_call`, `emergency_report`, `emergency_notify`, `emergency_task`, `report_parse`, `profile_missing`, `auth_denied`, `http_request`. `user_id` is stored only as a truncated SHA-256. Cost views per LLM call: token-priced at `COST_REFERENCE_MODEL`, actual price when the model is hosted, `MODEL_GPU_USD_PER_HOUR × wall time`. `app/metrics_queries.py` holds the aggregations used by both `GET /metrics/summary` and `scripts/metrics_report.py`. Design: `docs/INSTRUMENTATION.md`.

---

## 9. Known limitations

- **Single process.** Per-elder registration lock and the auth caregiver cache are in-process.
- **Auth scope.** No token revocation check, no rate limiting, no audit log, no data-deletion path; CORS `*`.
- **Prompt volume.** ~10k prompt tokens per ALLOWED turn across three stages (F-03).
- **Knowledge base.** 15 conditions; a symptom the table does not know cannot be assessed.
- **Human-review tier pending** for emergency adequacy, clinical appropriateness and dialect.
- **No migrations, no Docker, no lock file.**

---

## 10. Where to read next

| Question | Document |
|---|---|
| What was broken before, and how badly? | `docs/AUDIT.md` |
| What did running it reveal? | `docs/FINDINGS.md` |
| What are the before/after numbers? | `docs/RESULTS.md` |
| How was that measured? | `docs/EXPERIMENTS.md`, `docs/INSTRUMENTATION.md` |
| How do I test agent behaviour? | `evals/schema.md`, `evals/runner.py` |
| What was the plan and what deviated? | `docs/PLAN.md` |
