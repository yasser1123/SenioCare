# SenioCare — Codebase Audit

**Date:** 2026-08-31
**Commit:** `8d88d81` (branch `main`, working tree dirty — 8 modified, 2 deleted, 1 untracked)
**Scope:** Read-only static audit. No application code was modified.
**Method:** Full read of all 34 first-party Python modules, seed-data inspection, one test-suite execution.

**How to read this document.** Every claim carries a `file:line` citation. Claims that depend on runtime behaviour I could not observe statically are marked **[NEEDS RUNTIME CONFIRMATION]** with the specific experiment that would settle them. Claims I am inferring rather than reading directly are marked **[SPECULATION]**.

**A note on what I got wrong on first pass:** my initial sweep assumed there were no database indexes. That was wrong — seven indexes exist (`seniocare/data/database.py:225-231`, `seniocare/tools/reports.py:59-68`). I also hypothesised that meal ingredients were stored in Arabic and could therefore never join against the English interaction tables; that is also wrong (`seniocare/data/seeds/meals.json`, ingredients are English lowercase). Both corrections are reflected below.

---

# PHASE 0 — Inventory and Architecture

## 0.1 Repository map

### Languages and frameworks

| Layer | Technology | Evidence |
|---|---|---|
| Language | Python (3.10 target, 3.12 in `.venv`) | `.venv` interpreter is 3.12; `seniocare/.venv` is 3.10 |
| Agent framework | Google ADK 1.22.0 | `requirements.txt:1`, verified installed |
| Model gateway | LiteLLM → Ollama | `seniocare/sub_agents/orchestrator_agent.py:315` |
| Web framework | FastAPI (via ADK's `get_fast_api_app`) | `main.py:19,38` |
| ASGI server | Uvicorn | `main.py:131` |
| Tools DB | PostgreSQL (Neon), sync `psycopg2` | `seniocare/data/database.py:24-25,71` |
| Session DB | PostgreSQL via ADK `DatabaseSessionService`, async `asyncpg` | `app/config.py:43-59,90` |
| Scheduling | APScheduler `AsyncIOScheduler` | `app/scheduler.py:181-189` |
| Push | Firebase Admin SDK (FCM) | `app/notifications.py:37-38` |
| Search | SerpAPI + BeautifulSoup | `seniocare/tools/web_search.py:20-21,35` |

### Entry points

| Entry point | File:line | Notes |
|---|---|---|
| HTTP server | `main.py:131` | `uvicorn.run(app, host="0.0.0.0", port=port)` |
| ASGI app construction | `main.py:38-44` | ADK builds the app; custom routers layered on at `main.py:50-54` |
| Agent import side-effect | `seniocare/agent.py:27-30` | `_init_db()` runs at import, wrapped in bare `try/except` |
| Scheduler | `main.py:62-64` → `app/scheduler.py:170` | Started via deprecated `@app.on_event("startup")` |
| Seed CLI | `seed_reports.py`, `seed_chat_history.py` | Standalone scripts, also invoked by `app/routers/reports.py:243` |

`0.0.0.0` bind at `main.py:131` is combined with wildcard CORS (`app/config.py:76`) and no authentication — see Finding **C-01**.

### Deployment config

**Absent.** No `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `pyproject.toml`, `Procfile`, `cloudbuild.yaml`, `render.yaml`, or `fly.toml`. Verified by direct filesystem check. Dependency pinning is `>=`-only across all 18 lines of `requirements.txt` — no lock file.

### Test files

| File | Lines | Status |
|---|---|---|
| `tests/conftest.py` | 178 | Mocks the entire `google.adk` module tree (`tests/conftest.py:36-62`) |
| `tests/unit/test_symptoms.py` | 273 | Passes |
| `tests/unit/test_nutrition.py` | 230 | Passes |
| `tests/unit/test_interactions.py` | 157 | Passes |
| `tests/unit/test_exercise.py` | 120 | Passes |
| `tests/test_database_tools.py` | — | Passes |
| `tests/integration/test_api_endpoints.py` | 235 | **All skipped** — gated on a live server at `tests/integration/test_api_endpoints.py:37-40` |
| `tests/integration/test_multi_tool_flows.py` | 142 | **Fails to import** |
| `tests/unit/test_medication.py` | — | Tracked in git, deleted from disk |
| `tests/unit/test_image_analysis.py` | — | Tracked in git, deleted from disk |

Observed run (`python -m pytest -q --ignore=tests/integration/test_multi_tool_flows.py`):
```
76 passed, 48 skipped, 2 warnings in 107.89s
```

Collection of the full suite **errors out**:
```
tests/integration/test_multi_tool_flows.py:17: in <module>
    from seniocare.tools.medication import get_medication_schedule, log_medication_intake
E   ModuleNotFoundError: No module named 'seniocare.tools.medication'
```

Two `pytest.ini` options are silently inert because their plugins are not installed:
```
PytestConfigWarning: Unknown config option: asyncio_mode
PytestConfigWarning: Unknown config option: timeout
```
`pytest.ini:6` sets `asyncio_mode = auto` and `pytest.ini:7` sets `timeout = 30`; neither `pytest-asyncio` nor `pytest-timeout` appears in `requirements.txt`. Any `async def` test is therefore not being awaited — it is collected, skipped or warned on, and reported as non-failing. **[NEEDS RUNTIME CONFIRMATION]** — run `pytest --collect-only -q | grep -c "async"` and inspect whether async tests report as passed or warned.

The 108-second wall time is because unit tests reach the live Neon database via `get_connection()` (`seniocare/data/database.py:71`). There is no local or in-memory test database.

### CI config

**Absent.** No `.github/workflows/`, no `.pre-commit-config.yaml`, no linter or type-checker configuration of any kind.

---

## 0.2 Runtime call graph — one chat request

Traced for `POST /run_sse`, the endpoint the Flutter client uses for conversation.

| # | Hop | File:line |
|---|---|---|
| 1 | Client `POST /run_sse` with `{app_name, user_id, session_id, new_message}` | Route registered by ADK inside `get_fast_api_app`, called at `main.py:38` |
| 2 | ADK resolves agent dir → imports `seniocare` package | `main.py:36` (`AGENT_DIR`), `seniocare/__init__.py` |
| 3 | Import side-effect: create + seed all tables | `seniocare/agent.py:27-30` → `seniocare/data/database.py:83` |
| 4 | ADK loads session from Postgres | `app/config.py:90` (`DatabaseSessionService`) |
| 5 | `before_agent_callback` → `populate_user_data` | `seniocare/agent.py:38` → `seniocare/callbacks.py:73` |
| 5a | If no `user:user_id` in state, inject fabricated test patient | `seniocare/callbacks.py:87-94` |
| 5b | Increment turn counter; build `conversation_history` from last 12 events | `seniocare/callbacks.py:108-109`, `:114-120` |
| 6 | `SequentialAgent` runs sub-agents in fixed order | `seniocare/agent.py:35-43` |
| 7 | **Stage 1** — Orchestrator LLM call; prompt interpolates `{conversation_history}` and `{user:preferences}` | `seniocare/sub_agents/orchestrator_agent.py:313-319`; templates at `:39,:42` |
| 8 | Writes `orchestrator_result` to session state | `seniocare/sub_agents/orchestrator_agent.py:318` (`output_key`) |
| 9 | **Stage 2** — Feature LLM call; prompt interpolates `{orchestrator_result}` | `seniocare/sub_agents/feature_agent.py:307-325`; template at `:63` |
| 10 | Tool calls dispatched by ADK against the 10 registered tools | `seniocare/sub_agents/feature_agent.py:312-323` |
| 10a | Each DB tool opens its own connection | e.g. `seniocare/tools/nutrition.py:35` → `seniocare/data/database.py:71` |
| 11 | Writes `feature_result` to session state | `seniocare/sub_agents/feature_agent.py:324` |
| 12 | **Stage 3** — Formatter LLM call; prompt interpolates `{feature_result}` | `seniocare/sub_agents/formatter_agent.py:229-235`; template at `:50` |
| 13 | Writes `final_response` to session state | `seniocare/sub_agents/formatter_agent.py:234` |
| 14 | `after_agent_callback` → `auto_save_to_memory` | `seniocare/agent.py:39` → `seniocare/callbacks.py:149` |
| 14a | Headline generated on turn 1 only | `seniocare/callbacks.py:157-181` |
| 14b | If intent parsed as `emergency`, fire-and-forget background task | `seniocare/callbacks.py:183-185` → `:213-248` |
| 14c | Memory save attempt (always fails — see **G-04**) | `seniocare/callbacks.py:187-194` |
| 15 | SSE events stream back; client renders the `formatter_agent` event | Consumer contract visible at `app/routers/chat_history.py:82` |

**Three sequential LLM round-trips per user turn**, each a full ~10 KB system prompt. No caching, no parallelism, no streaming to first token from stage 1. **[SPECULATION]** — on consumer hardware running `gemma4:e4b` locally, end-to-end latency is likely tens of seconds. I cannot measure this without running the stack; see `docs/INSTRUMENTATION.md`.

---

## 0.3 Architecture pattern

**What it is: a fixed sequential chain (pipeline).**

Evidence: `seniocare/agent.py:35-43` constructs `SequentialAgent(sub_agents=[orchestrator, feature, formatter])`. ADK's `SequentialAgent` executes every sub-agent in list order unconditionally. There is no router, no conditional edge, no supervisor loop, no delegation primitive, and no agent-to-agent handoff. Data moves forward only, via `output_key` state writes.

**What it appears to intend: orchestrator-worker with conditional skip.**

The docstrings and prompts describe a different system than the code builds:

- `seniocare/sub_agents/orchestrator_agent.py:8-9` — "the Feature Agent is skipped in those cases"
- `seniocare/sub_agents/feature_agent.py:8-9` — "For BLOCKED/EMERGENCY cases, it relays the Orchestrator's output directly"
- `README.md:39` — the Mermaid diagram draws an edge `Orch -->|BLOCKED / EMERGENCY| Fmt` bypassing the Feature Agent

**The deviation:** no such bypass edge exists. On an emergency, the Feature Agent still runs — a full LLM invocation with all 10 tools bound — and is merely *asked in prose* not to call them (`seniocare/sub_agents/feature_agent.py:54`, `:79`). Safety-critical routing is enforced by prompt text rather than control flow. A model that ignores the instruction will call tools on an emergency path; a model that obeys it still burns a full LLM round-trip and its latency during a medical emergency.

This is the single most consequential architectural finding in the audit. See **C-02**.

**Cost of the sequential-chain choice** (stated as cost, not as criticism):
- Every request pays all three LLM calls regardless of complexity. A `preference` intent ("I don't like fish") costs the same three round-trips as a full meal plan.
- No stage can be skipped, retried independently, or run in parallel.
- Errors have no recovery path — a malformed stage-1 output propagates as text into stage 2's prompt and is never validated.
- The upside, which is real: the flow is trivially traceable and each stage has one job. For a graduation project this is a defensible trade.

---

## 0.4 State: where it lives, how it moves, what mutates

### Storage tiers

| Tier | Mechanism | Lifetime | Evidence |
|---|---|---|---|
| Session state (unprefixed) | ADK `state_delta` → Postgres | Whole session | `seniocare/callbacks.py:109` |
| User state (`user:` prefix) | ADK user-scoped state → Postgres | Across all sessions | `app/routers/user_profile.py:43-56` |
| Stage handoff | `output_key` → session state | Within one invocation | `orchestrator_agent.py:318`, `feature_agent.py:324`, `formatter_agent.py:234` |
| Event log | ADK session events | Whole session | Read at `app/routers/chat_history.py:71` |
| Tools data | Postgres, direct `psycopg2` | Permanent | `seniocare/data/database.py:71` |
| Firebase init flag | Module global | Process | `app/notifications.py:20` |
| Scheduler handle | Module global | Process | `app/scheduler.py:167` |
| DB init flag | Module global | Process | `seniocare/data/database.py:46` |

### In-place mutation

Yes, in three places, and one is a defect:

1. **`seniocare/callbacks.py:88-89`** — iterates `TEST_USER_PROFILE` and writes each key into live session state. The module-level dict itself is not copied; nested values (the `medications` list at `callbacks.py:25-28`, the `caregivers` list at `:32-39`) are shared by reference across every session that triggers this path. **[SPECULATION]** — whether a downstream write mutates the shared module global depends on ADK's serialisation of `state_delta`. If ADK deep-copies on persist, this is harmless; if it does not, one user's profile edit could leak into another's. Confirm by writing to `state["user:medications"].append(...)` in a callback and re-reading `TEST_USER_PROFILE` in the same process.

2. **`seniocare/tools/preferences.py:57,62-65,68`** — reads the `user:preferences` dict out of state, mutates it in place, writes it back. Contains a real bug — see **C-05**.

3. **`app/routers/user_profile.py:216-224`** — reads `user:caregivers`, mutates the list, writes back. This is a **read-modify-write with no locking** across three separate session create/delete round-trips (`:199`, `:230`, `:236`). Two caregivers registering concurrently will lose one registration. See **R-03**.

### The temp-session pattern

Six call sites create a throwaway session purely to read or write `user:`-scoped state, then delete it:

| Purpose | File:line |
|---|---|
| Read profile | `app/routers/user_profile.py:88-92` |
| Write profile | `app/routers/user_profile.py:36-58` |
| Sync profile | `app/routers/user_profile.py:172-180` |
| Register caregiver (read) | `app/routers/user_profile.py:196-200` |
| Register caregiver (write) | `app/routers/user_profile.py:229-237` |
| Notify caregivers | `app/routers/reports.py:103-107` |
| Scheduler caregiver read | `app/scheduler.py:82-86` |
| Report profile read | `seniocare/tools/reports.py:155-160` |

Each is 2–3 database round-trips to read one dictionary. This is ADK's user-state API being used against its grain. The `_profile_` prefix then has to be filtered out of the conversation list (`app/routers/chat_history.py:29-30`) — but that filter only matches `_profile_`, while sessions are also created with prefixes `_notif_`, `_fcm_reg_`, `_fcm_write_`, `_sched_read_`, and `_report_profile_`. See **C-08**.

---

## 0.5 LLM call sites

Five call sites. Four agent definitions plus one manual Runner invocation.

| # | Site | File:line | Model | Prompt | Output key |
|---|---|---|---|---|---|
| 1 | `orchestrator_agent` | `seniocare/sub_agents/orchestrator_agent.py:313-319` | `ollama_chat/gemma4:e4b` | `ORCHESTRATOR_INSTRUCTION`, `:15-311` (~297 lines) | `orchestrator_result` |
| 2 | `feature_agent` | `seniocare/sub_agents/feature_agent.py:307-325` | `ollama_chat/gemma4:e4b` | `FEATURE_INSTRUCTION`, `:22-305` | `feature_result` |
| 3 | `formatter_agent` | `seniocare/sub_agents/formatter_agent.py:229-235` | `ollama_chat/gemma4:e4b` | `FORMATTER_INSTRUCTION`, `:13-227` | `final_response` |
| 4 | `report_agent` | `seniocare/sub_agents/report_agent.py:131-137` | `ollama_chat/gemma4:e4b` | `REPORT_INSTRUCTION`, `:24-129` | `report_result` |
| 5 | Manual Runner | `seniocare/tools/reports.py:434-471` | (invokes #4) | Wrapper prompt at `:447-452` | returned string |

### Generation parameters

**None are set at any of the five sites.** No `temperature`, no `max_tokens`, no `top_p`, no `generate_content_config`, no seed, no stop sequences. Every call inherits LiteLLM/Ollama defaults. Consequences:

- Output is non-deterministic with no way to reduce variance for the safety-classification stage, where determinism matters most.
- No output cap. The Feature Agent is instructed "Include ALL tool results in your output — do not summarize or trim" (`seniocare/sub_agents/feature_agent.py:299-300`). With a large tool payload this can generate until the context window ends.
- Model identifier `ollama_chat/gemma4:e4b` is hardcoded in four separate files with no environment override and no `OLLAMA_API_BASE` configuration anywhere in the repo. The application cannot be pointed at a different model or a remote host without editing source.

### Output parsing and validation

| Stage | Output format | Parsed? | Validated? | On malformed output |
|---|---|---|---|---|
| Orchestrator | Free text with `SAFETY_STATUS:` / `INTENT:` labels (`orchestrator_agent.py:282-306`) | Only `INTENT` — one regex at `seniocare/callbacks.py:208` | **No** | `_extract_intent` returns `"unknown"` (`callbacks.py:210,212`). No emergency triggered, no error raised. |
| Feature | Free text with `RESPONSE_TYPE:` etc. (`feature_agent.py:231-273`) | **Not parsed at all** | **No** | Passed verbatim as a string into the Formatter prompt. |
| Formatter | Egyptian Arabic prose | **Not parsed** | **No** | Whatever the model emits is the user-facing answer. |
| Report | Markdown with `STATUS:` line (`report_agent.py:122-123`) | `seniocare/tools/reports.py:503` | Value checked against a 4-item allowlist at `:506` | **Silently defaults to `"moderate"`** (`:502`) |

No stage uses structured output, JSON mode, a Pydantic response schema, or a retry-on-parse-failure loop. `SAFETY_STATUS` — the field that gates whether a medical emergency is escalated — **is never read by any Python code.** The only signal extracted is `INTENT`, via a single regex. See **C-03**.

---

# PHASE 1 — Gap Analysis

Status only. Recommendations are deliberately withheld.

### Retrieval / RAG — **ABSENT**

No vector store, no embedding model, no chunking, no retrieval step, no reranking. Verified by repo-wide grep for `embed|vector|faiss|chroma|pinecone|qdrant|weaviate|pgvector|retriev` across first-party code and `requirements.txt` — zero hits outside unrelated docstring prose.

Knowledge access is exclusively (a) exact-match SQL over 7 seed tables and (b) live SerpAPI calls. `app/config.py:63` documents that ADK memory is disabled: `MEMORY_SERVICE_URI = None`. Retrieval quality is measured nowhere.

Corpus sizes: 19 meals, 20 drug-food interactions, 15 diseases, 23 food-allergen pairs (counted from `seniocare/data/seeds/*.json`).

### Evaluation — **ABSENT** (for LLM output)

124 tests exist but every one targets deterministic Python — tool functions, DB queries, HTTP status codes. Zero assertions touch model output. No golden files, no snapshot tests, no LLM-as-judge, no regression corpus, no safety-classification test set. `tests/conftest.py:36-62` mocks the entire `google.adk` tree, so no test can invoke an agent even in principle.

There is no test asserting that an emergency phrase produces `SAFETY_STATUS: EMERGENCY`.

### Observability — **ABSENT**

| Capability | Status | Evidence |
|---|---|---|
| Structured logging | Absent | 23 `print()` calls across first-party modules |
| `logging` module | Partial — 2 of 34 modules | `app/notifications.py:15`, `app/scheduler.py:20` |
| Logging configuration | Absent | No `basicConfig`, no handler, no formatter, no level set anywhere |
| Tracing | Absent | No OpenTelemetry, Langfuse, LangSmith, Sentry |
| Latency measurement | Absent | No timing instrumentation at any call site |
| Token counting | Absent | `usage_metadata` never accessed |
| Cost tracking | Absent | — |
| Request correlation ID | Absent | — |
| Metrics endpoint | Absent | `/health` (`app/routers/health.py:10-25`) returns static config strings only — it does not check DB connectivity, Ollama reachability, or scheduler liveness |

**Can a failed response be attributed to a stage?** No. The three stages are indistinguishable in any output. Because the loggers at `app/notifications.py:15` and `app/scheduler.py:20` are never configured with a handler, their `logger.info` and `logger.warning` calls **produce no output at all** under default `WARNING` root level — the `logger.info` lines are silently discarded. Only the `print()` calls are visible.

### MCP — **ABSENT**

No MCP server, no MCP client, no `mcp` dependency. The single grep hit is an unrelated comment at `app/openapi.py:5`.

### Tool calling — **PRESENT, with gaps**

Definition: plain Python functions with type hints and docstrings, registered as a list at `seniocare/sub_agents/feature_agent.py:312-323`. ADK derives schemas from signatures. Idiomatic and clean.

Gaps:
- **No input validation in any tool.** `meal_type` (`nutrition.py:8`) is not checked against the four valid values; `preference_type` (`preferences.py:12`) silently falls through to `"general"` for any unrecognised string (`:50-51`); `symptoms` (`symptoms.py:8`) accepts any list including empty strings.
- **No per-tool error handling.** `nutrition.py:35`, `interactions.py:55`, `symptoms.py:46`, `exercise.py:33` call `get_connection()` with no try/except. A DB outage raises inside the ADK tool dispatcher rather than returning a structured error the model can reason about.
- **Connection lifecycle is `try/finally: conn.close()`** with no `rollback()` and no cursor close (`nutrition.py:141-142`, `interactions.py:110-111`, `symptoms.py:145-146`).
- **The re-entrancy guards are broken** — see **C-04**.
- **Two advertised tools do not exist** — see **C-06**.

### Auth / data protection — **ABSENT**

| Control | Status |
|---|---|
| Authentication | **None.** No JWT, no API key, no session token, no OAuth, no FastAPI dependency guard on any route. |
| Authorization | **One check exists**, at `app/routers/reports.py:180-181`, comparing `report.user_id` to the path `user_id`. Both come from the caller. |
| Identity establishment | `user_id` is an unauthenticated path or body parameter on every endpoint. |
| CORS | `"*"` at `app/config.py:76`, with a `TODO` acknowledging it. |
| Transport | Server binds `0.0.0.0` (`main.py:131`); no TLS termination in-repo. |
| Encryption at rest | None beyond whatever Neon provides by default. |
| PII/PHI handling | Chronic diseases, medications, allergies, blood type stored as plaintext session state. |
| Audit log | None. |
| Rate limiting | None. |
| Secret management | `.env` + a service-account JSON on disk. Correctly gitignored (`.gitignore:26,29`) and confirmed absent from git history. |
| Data retention / deletion | No endpoint deletes user data. No GDPR/HIPAA-style erasure path. |

`sessions.db` **was committed in git history** (confirmed via `git log --diff-filter=A`). It is gitignored now and untracked, but if it ever contained real conversation data, that data remains in history.

### Error handling — **PARTIAL and inconsistent**

| Failure | Behaviour | Evidence |
|---|---|---|
| LLM timeout | **No timeout is configured anywhere.** A hung Ollama call hangs the request indefinitely. | No `timeout` param at any of the 5 call sites |
| LLM rate limit | Unhandled | — |
| Malformed LLM output | Silently absorbed | `callbacks.py:210-212`, `reports.py:502` |
| SerpAPI timeout | Handled — returns structured error | `web_search.py:175-180` |
| SerpAPI non-200 | **Unhandled** — `response.json()` at `:160` without a status check; an HTML error page raises `JSONDecodeError`, caught by the broad handler at `:181` and reported as a generic failure |
| DB connection failure | One blind retry, then raises | `database.py:73-76` |
| DB error inside a tool | Propagates uncaught | `nutrition.py:35` and peers |
| Firebase init failure | Caught, logged, disabled | `notifications.py:74-79` |
| FCM send failure | Caught per-token, counted | `notifications.py:185-206` |
| Emergency report failure | **Caught and discarded** | `callbacks.py:294-295` |
| Scheduled report failure | Caught per user, loop continues | `scheduler.py:155-158` |

35 `except Exception` handlers across first-party code. Several leak raw exception text to HTTP clients via `detail=f"...{e}"` (`app/routers/sessions.py:37`, `chat_history.py:47`, `user_profile.py:75`), which can expose database connection strings.

### Data layer — **PARTIAL**

- **Schema:** 8 tables via `CREATE TABLE IF NOT EXISTS` at import time (`database.py:119-222`, `reports.py:41-57`).
- **Migrations:** **Absent.** No Alembic. Schema changes to an existing deployment are impossible without manual SQL — `IF NOT EXISTS` never alters an existing table.
- **Indexes:** **Present** — 7 total (`database.py:225-231`, `reports.py:58-68`). Correcting my first-pass claim that there were none.
- **Index effectiveness:** compromised at `interactions.py:67`, where `WHERE LOWER(drug_name) = %s` applies a function to the indexed column, defeating `idx_drug_interactions_drug` and forcing a sequential scan.
- **N+1 patterns:** three confirmed — `interactions.py:63-68` (drugs × foods), `symptoms.py:101-104` (per disease), `reports.py:223-229` (per session).
- **Blocking I/O:** all tool DB access is synchronous `psycopg2` (`database.py:71`) called from `async def` endpoints (`app/routers/reports.py:141,173,200`) and async tools (`image_tools.py:16,54`). Every such call blocks the entire event loop.
- **Connection pooling:** **Absent.** `get_connection()` opens a new TCP+TLS connection per call (`database.py:71`) and closes it. Against serverless Neon this is both slow and connection-limit-bound.
- **Type modelling:** every column is `TEXT`, including JSON payloads (`ingredients TEXT` at `database.py:126`) and timestamps (`scanned_at TEXT`, `generated_at TEXT` at `reports.py:54`). Date filtering on reports is therefore string comparison.

---

# PHASE 2 — Correctness and Reliability Findings

Ranked by severity, silent-wrong-answer first. Severity reflects consequence in a healthcare context, not code ugliness.

---

## C-01 — No authentication on any endpoint exposing health data
**Severity: Critical | Confidence: High | Blast radius: Confidentiality breach**

Every endpoint accepts `user_id` as an unauthenticated parameter.

- `app/routers/chat_history.py:11` — `GET /chat-history/{user_id}` returns another person's full medical conversation log
- `app/routers/user_profile.py:78` — `GET /get-user-profile/{user_id}` returns diseases, medications, allergies, blood type
- `app/routers/user_profile.py:27` — `POST /set-user-profile/{user_id}` **overwrites** any user's medical profile
- `app/routers/user_profile.py:186` — `POST /register-caregiver-fcm` attaches an arbitrary FCM token to any elder, redirecting their emergency alerts to an attacker's device
- `app/config.py:76` — `ALLOWED_ORIGINS` includes `"*"`, so any web origin can issue these requests

**Trigger:** `curl http://host:8080/get-user-profile/elder_123`

The lone authorization check at `app/routers/reports.py:180-181` compares two attacker-supplied values and provides no protection.

---

## C-02 — Safety routing is enforced by prose, not control flow
**Severity: Critical | Confidence: High | Blast radius: Silent wrong answer on the emergency path**

`seniocare/agent.py:35-43` uses `SequentialAgent`, which runs all three sub-agents unconditionally. The documented bypass for BLOCKED/EMERGENCY (`orchestrator_agent.py:8-9`, `feature_agent.py:8-9`, `README.md:39`) does not exist in code.

On an emergency the Feature Agent still executes with all 10 tools bound, restrained only by the instruction at `feature_agent.py:54` ("Do NOT call tools when safety_status is BLOCKED or EMERGENCY"). Nothing enforces it.

**Trigger:** a message containing chest-pain symptoms. The Orchestrator emits `SAFETY_STATUS: EMERGENCY`; stage 2 runs anyway.

**Consequences:** (a) a full LLM round-trip of added latency during a medical emergency; (b) if the model disregards the instruction, arbitrary tool execution on the emergency path; (c) the emergency message must survive being paraphrased through two further LLM stages before the user sees it — `formatter_agent.py:213` forbids adding information but nothing forbids omission.

**[NEEDS RUNTIME CONFIRMATION]** — how often `gemma4:e4b` honours the no-tools instruction. Run 50 emergency-phrased inputs and count tool invocations in stage 2.

---

## C-03 — `SAFETY_STATUS` is never read by any code
**Severity: Critical | Confidence: High | Blast radius: Silent failure to escalate**

The only extraction from the Orchestrator's output is `INTENT`, via one regex at `seniocare/callbacks.py:208`:
```python
match = re.search(r"INTENT:\s*(\w+)", orchestrator_output)
```
`SAFETY_STATUS` appears in the prompt contract (`orchestrator_agent.py:284,293,302`) but is read nowhere in the codebase.

The emergency escalation at `callbacks.py:184` therefore depends entirely on the model emitting the literal token `INTENT: emergency`. If it writes `Intent: Emergency`, `INTENT: EMERGENCY_MEDICAL`, or wraps the block in markdown, `_extract_intent` returns `"unknown"` (`callbacks.py:212`) and:
- no emergency report is generated,
- no caregiver FCM notification is sent,
- the headline falls back to "new conversation" (`callbacks.py:160`),
- **nothing anywhere logs that escalation was skipped.**

Note `\w+` does not match `EMERGENCY_MEDICAL` partially — it matches `EMERGENCY_MEDICAL` in full, which then fails the `== "emergency"` comparison at `callbacks.py:184`.

**Trigger:** any Orchestrator output whose intent line deviates from the exact expected casing/format.

---

## C-04 — Tool re-entrancy guards persist for the whole session, blocking every subsequent request
**Severity: Critical | Confidence: High (code) / **[NEEDS RUNTIME CONFIRMATION]** (ADK state semantics) | Blast radius: Silent wrong answer from turn 2 onward**

Five tools set a "called" flag in session state to prevent duplicate calls within a turn:

| Tool | Set at | Flag |
|---|---|---|
| `get_meal_options` | `nutrition.py:29` | `_meal_tool_called` |
| `get_meal_recipe` | `nutrition.py:166` | `_recipe_tool_called` |
| `check_drug_food_interaction` | `interactions.py:27` | `_interaction_tool_called` |
| `assess_symptoms` | `symptoms.py:30` | `_symptom_tool_called` |
| `store_medical_report` | `image_tools.py:48` | `_store_report_tool_called` |

The comment on each says "Prevent multiple calls in the same turn." But the keys carry **no `temp:` prefix**, and in ADK only `temp:`-prefixed state is scoped to a single invocation. A repo-wide grep confirms **these flags are never reset anywhere.**

**Trigger:** ask for a meal, then ask for another meal in the same conversation.
- Turn 1: `get_meal_options` returns 3 meals.
- Turn 2: returns `{"status": "already_called", "message": "…use the previous result…"}` (`nutrition.py:25-28`).

The Feature Agent now has **no meal data** and an Arabic instruction telling it to reuse a previous result it cannot see. It will either fabricate a meal or emit a degraded answer. The same applies to drug-interaction checking (`interactions.py:22`) — **on turn 2 onward, drug-food interaction screening silently returns nothing.**

The Formatter will still render the meal template at `formatter_agent.py:99-125` including the `⚕️ تفاعلات الأدوية` section, because the template is unconditional.

**Confirm by:** two consecutive meal requests in one session; assert `get_meal_options` returns `status: "success"` both times.

---

## C-05 — Preference conflict-resolution silently does nothing for dislikes
**Severity: High | Confidence: High | Blast radius: Silent wrong answer, contradictory state**

`seniocare/tools/preferences.py:60`:
```python
opposite_key = key.replace("likes", "dislikes") if "likes" in key else key.replace("dislikes", "likes")
```
`"likes"` is a substring of `"dislikes"`, so the condition is always true. Verified by execution:

| `key` | computed `opposite_key` |
|---|---|
| `food_likes` | `food_dislikes` ✅ |
| `food_dislikes` | `food_disdislikes` ❌ |
| `exercise_dislikes` | `exercise_disdislikes` ❌ |
| `general_dislikes` | `general_disdislikes` ❌ |

The guard at `:61` (`if opposite_key in preferences`) then fails, so the removal loop at `:62-65` never runs.

**Trigger:** "I like fish" then later "I don't like fish". Result: `food_likes` and `food_dislikes` **both contain `"fish"`**, permanently, in cross-session `user:` state.

The Orchestrator prompt at `orchestrator_agent.py:44-46` reads these preferences and is told "If they dislike fish, NEVER suggest fish-based meals" — while being handed state asserting both. Behaviour becomes model-dependent and unpredictable.

Secondary defect, same file: `:57` writes `list(existing)` from a Python `set`, so preference ordering is non-deterministic across runs.

---

## C-06 — The Orchestrator plans calls to two tools that do not exist
**Severity: High | Confidence: High | Blast radius: Silent wrong answer on image intents**

`orchestrator_agent.py:225-239` documents two tools to the planner:
- `analyze_medication_image_tool(image_base64)` (`:225`), attributed to model `richardyoung/olmocr2:7b-q8` (`:228`)
- `analyze_medical_report_tool(image_base64)` (`:232`), attributed to model `llama3.2-vision` (`:236`)

Neither exists. The Feature Agent's actual tool list (`feature_agent.py:312-323`) contains 10 tools, and neither is among them. Neither name appears anywhere in `seniocare/tools/`. Neither model is configured anywhere in the repo.

The instructions actively contradict each other: `orchestrator_agent.py:271` tells the planner to call `analyze_medication_image_tool`, while `feature_agent.py:211` tells the executor "Do NOT call any tool — just format the model's analysis."

**Trigger:** any `image_medication` or `image_report` intent. The Orchestrator emits a plan referencing a non-existent tool; the Feature Agent cannot execute it.

**This is unadapted generated boilerplate** — the prompt describes an architecture (dedicated OCR and vision models) that was replaced by native multimodal handling, and the prompt was never updated. Related dead reference: `feature_agent.py:242` still lists "For medication: full schedule with next doses", a leftover of the deleted `seniocare/tools/medication.py`.

---

## C-07 — Report date range is silently ignored for all conversation data
**Severity: High | Confidence: High | Blast radius: Silent wrong answer in clinical reports**

`seniocare/tools/reports.py:301`:
```python
session_data = await _get_session_data_from_history(user_id)
```
`_get_session_data_from_history` is defined at `:195` with signature `(user_id: str)` — **it accepts no date parameters at all.** It slices `sessions.sessions[-10:]` (`:223`) and `session.events[-6:]` (`:251`), i.e. a fixed recency window.

Only `_get_medical_reports` (`:313`) receives `start_date`/`end_date`. The `period` block written at `:318` is therefore cosmetic for everything except medical reports.

**Consequence:** a "daily" report and a "monthly" report aggregate **exactly the same conversation data**. A daily report can summarise months-old conversations; a monthly report covers only the last 10 sessions regardless of period.

**Trigger:** `POST /reports/generate` with `report_type: "daily"` versus `"monthly"` for the same user — the conversation inputs are identical.

---

## C-08 — Four aggregation fields are declared, read, and never populated
**Severity: High | Confidence: High | Blast radius: Hallucinated report content**

In `_get_session_data_from_history`, four keys are initialised empty at `reports.py:203-206` and read back at `:321-325`, but **no code path ever writes to them**:

| Field | Initialised | Read | Written |
|---|---|---|---|
| `symptoms_reported` | `:203` | `:321` | never |
| `meals_accessed` | `:204` | `:322` | never |
| `exercises_accessed` | `:205` | `:323` | never |
| `interaction_warnings` | `:206` | `:325` | never |

Meanwhile `report_agent.py:40` tells the model it will receive "symptoms_reported: [list of symptoms mentioned with dates]" and `report_agent.py:117` instructs "Always include medication adherence observations if data available."

The model is therefore prompted to report on symptom trends, meals, exercise, and drug interactions using four permanently empty arrays. It will either state "no data" for every clinical section — making the reports worthless — or fabricate content. **[NEEDS RUNTIME CONFIRMATION]** — generate 10 reports and count how many assert clinical facts not present in the input JSON.

Related: `conversation_topics` is type-confused — it receives intent labels at `:241` and raw user message text at `:258-260`, producing a mixed list like `["meal", "عندي صداع في راسي", "exercise"]`.

---

## C-09 — Emergency notification is a fire-and-forget task that can be garbage collected
**Severity: High | Confidence: High | Blast radius: Silent failure of the life-safety path**

`seniocare/callbacks.py:236-243`:
```python
asyncio.create_task(
    _generate_and_notify_emergency(...)
)
```
The returned task is not stored. Per CPython's documented behaviour, the event loop keeps only a weak reference to running tasks; a task whose only strong reference is dropped may be garbage collected mid-execution.

Compounding factors on the same path:
- no retry (`callbacks.py:294-295` catches everything and prints)
- no persistence — a process restart loses in-flight emergencies
- no dead-letter queue
- no alerting on failure
- the whole trigger block is itself wrapped in `try/except` that prints and continues (`callbacks.py:245-246`)
- it depends on `generate_report`, which makes an unbounded LLM call with no timeout (`reports.py:461`)

**Trigger:** an emergency that coincides with GC pressure, a slow Ollama response, or a process restart. The caregiver is never notified and **no record of the failure exists** beyond a `print` to stdout.

---

## C-10 — Report status silently defaults to "moderate" on unparseable output
**Severity: High | Confidence: High | Blast radius: Silent wrong answer with clinical meaning**

`seniocare/tools/reports.py:502-507`:
```python
overall_status = "moderate"
status_match = re.search(r"^STATUS:\s*(\w+)", raw_text, re.MULTILINE)
if status_match:
    status_val = status_match.group(1).lower().strip()
    if status_val in ("good", "moderate", "concerning", "critical"):
        overall_status = status_val
```
If the model omits the `STATUS:` line, indents it, or emits an out-of-vocabulary value, the report is persisted as `"moderate"` with no warning.

**Trigger:** an emergency report where the model writes `STATUS: خطير` (Arabic) or `**STATUS:** critical` (markdown bold — `^STATUS:` will not match). A critical patient is stored and displayed as moderate. `caregiver`-facing UI and the FCM notification path both consume this field.

---

## C-11 — A fabricated patient profile is injected whenever identity is missing
**Severity: High | Confidence: High | Blast radius: Silent wrong answer / clinically dangerous advice**

`seniocare/callbacks.py:86-94` — if `state.get("user:user_id")` is falsy, the module-level `TEST_USER_PROFILE` (`callbacks.py:16-47`) is written into live state: a 72-year-old male, diabetic and hypertensive, shellfish-allergic, on Metformin 500 mg and Lisinopril 10 mg, plus a caregiver with a placeholder FCM token (`:36`).

The guard is only "is this key missing" — there is no environment check, no `DEBUG` flag, no allow-list. Any production misconfiguration that loses the profile silently produces a patient identity rather than an error.

**Trigger:** call `/run_sse` with a `user_id` that never had `/set-user-profile` called. The pipeline then screens meals against diabetes rules and checks drug interactions against Metformin — for an unknown real person.

The parallel failure mode is at `reports.py:183-192`: if profile retrieval raises, it returns a profile with empty `conditions`, `medications`, and `allergies`, and report generation continues as if the patient has no medical history.

---

## C-12 — Symptom matching over-matches, escalating mild inputs to EMERGENCY
**Severity: High | Confidence: High | Blast radius: False emergency — caregiver alerts, wasted trust**

`seniocare/tools/symptoms.py:66-68` matches bidirectionally by substring:
```python
if (user_symptom in db_symptom or
        db_symptom in user_symptom or
        _fuzzy_symptom_match(user_symptom, db_symptom)):
```
`"dizziness"` is a listed symptom of stroke, heart attack, and severe allergic reaction (verified in `seniocare/data/seeds/disease_symptoms.json`, DIS001/DIS002/DIS003 — all `severity: EMERGENCY`).

The sort at `:121-122` orders by severity **before** confidence, so a 1-of-9 match (11.1% confidence, `:81`) on stroke outranks a high-confidence non-emergency match. Then `:140`:
```python
"is_emergency": top_severity == "EMERGENCY",
```

**Trigger:** a user reports only "dizziness". Result: `overall_severity: "EMERGENCY"`, `is_emergency: True`, `emergency_action: "اتصل بالطوارئ فوراً (123)"` — and the Feature Agent is instructed at `feature_agent.py:296-297` to treat this as critical.

Generic single words compound it: `"pain"` is a substring of `"chest pain"`, `"jaw pain"`, `"leg pain"`, and `"pain in left arm"`, matching multiple EMERGENCY diseases at once.

The confidence figure is also misleading by construction: `match_count / total_disease_symptoms * 100` (`:81`) means matching 1 of 2 listed symptoms yields "50% confidence", which reads as clinically meaningful and is not.

Cosmetic but telling: the comment at `:130` says "Limit to top 5 matches" while the code slices `[:3]`.

---

## C-13 — Symptom database is English-only; the user speaks Egyptian Arabic
**Severity: High | Confidence: Medium — **[NEEDS RUNTIME CONFIRMATION]** | Blast radius: Silent failure to detect a real emergency**

Every symptom string in `seniocare/data/seeds/disease_symptoms.json` is English (`"chest pain"`, `"face drooping"`, `"shortness of breath"`). Matching at `symptoms.py:62-68` is pure string containment with no translation layer and no Arabic synonym table.

The entire user-facing contract is Egyptian Arabic (`formatter_agent.py:217`). Nothing in `feature_agent.py` instructs the model to translate symptoms to English before calling `assess_symptoms` — the tool doc at `feature_agent.py:119-121` shows only English examples, which is an implicit hint rather than an instruction.

If the Feature Agent passes Arabic symptom strings, zero diseases match, `matches` is empty, and `:128` sets `top_severity = "UNKNOWN"` → `is_emergency: False`. **A stroke described in Arabic returns no emergency flag from the tool.**

The Orchestrator's independent keyword screen (`orchestrator_agent.py:76-85`) may still catch it — which is why I rate this Medium rather than High confidence on impact.

**Confirm by:** calling `assess_symptoms(["ألم في الصدر", "دوخة"])` directly and asserting on `overall_severity`. This is a 5-minute experiment and should be the first one run.

---

## C-14 — Drug and allergen matching is exact-string and currently masked by hand-tuned seed data
**Severity: Medium-High | Confidence: High | Blast radius: Silent false-negative on interaction and allergy screening**

Two exact-match joins:

1. **Drugs** — `interactions.py:49` takes `med.get("name", "").lower()` and `:67` requires `LOWER(drug_name) = %s`. The API accepts any free-text `name` (`app/schemas/profile.py:9` — plain `str`, no validation). A profile with `"Metformin HCl"`, `"Metformin 500mg"`, or the Arabic trade name returns **zero interactions**, indistinguishable from genuinely zero.

2. **Allergens** — `nutrition.py:99` uses `[f for f in allergen_foods if f in ingredient_names]`, where `ingredient_names` is a **list**, making this exact element equality, not substring.

I initially believed (2) was actively broken. It is not — the seed data compensates. `food_allergens.json` explicitly enumerates both `"cheese"` and `"cottage cheese"`, both `"bread"` and `"whole wheat bread"`, matching the exact ingredient strings used in `meals.json`. The filter works **only because someone hand-tuned 23 allergen rows against 19 meals.**

That is the finding: allergen safety currently depends on exhaustive manual enumeration with no test enforcing it. Adding one meal with an unenumerated ingredient spelling silently bypasses allergy filtering, and nothing fails.

Coverage is also thin — 20 interaction records across 12 drugs (`drug_food_interactions.json`). Any medication outside that list returns "no interaction found" (`interactions.py:83-87`), which the model may well present as a safety confirmation.

---

## C-15 — Nutrient filtering passes meals with missing values
**Severity: Medium | Confidence: High | Blast radius: Silent wrong answer**

`seniocare/tools/nutrition.py:76-80`:
```python
meal_value = meal.get(nutrient, 0)
if meal_value is not None and meal_value > max_val:
    passes = False
```
A meal whose `sodium_mg` is SQL `NULL` yields `meal_value = None`, the condition short-circuits, and the meal **passes** a hypertension sodium ceiling. A missing nutrient key yields `0`, which also passes.

The schema permits this — every nutrient column at `database.py:127-133` is nullable `REAL`.

**Trigger:** a hypertensive user requests a meal whose sodium value is null. It is recommended as compliant.

Secondary: `:111` takes `filtered_meals[:3]` with **no `ORDER BY`** in the query at `:41`. The "top 3" meals are arbitrary Postgres row order, not a ranking, despite `feature_agent.py:165-168` instructing the model to pick the "BEST" from them.

---

## C-16 — `GET /reports/medical/{user_id}` is unreachable: shadowed by an earlier route
**Severity: High | Confidence: High (empirically verified) | Blast radius: Endpoint always 404s**

Route registration order in `app/routers/reports.py`:

| Line | Route |
|---|---|
| `:140` | `@router.get("/{user_id}")` |
| `:172` | `@router.get("/{user_id}/{report_id}")` |
| `:199` | `@router.get("/medical/{user_id}")` |

Starlette matches routes in registration order, first match wins. `GET /reports/medical/elder_123` has two path segments and is therefore captured by the **line 172** route, binding `user_id="medical"` and `report_id="elder_123"`. The handler at `:199` is never reached.

Verified by executing the same three routes in an isolated FastAPI app:
```
GET /reports/medical/elder_123 -> {'route': 'report_detail', 'user_id': 'medical', 'report_id': 'elder_123'}
```

Execution then proceeds to `reports.py:177-179`: `get_health_report_detail("elder_123")` returns `None`, so the client receives **`404 {"detail": "Report not found"}`** for every call.

**Trigger:** any request to the medical-reports endpoint. It has never worked.

The fix is ordering, not logic — `/medical/{user_id}` must be registered before `/{user_id}/{report_id}`. Note also that `README.md:117` documents this capability under a *third*, entirely different path (`GET /user-medical-reports/{user_id}`), which does not exist either.

This bug is invisible to the test suite because `tests/integration/test_api_endpoints.py` is skipped whenever no server is running (`:37-40`) — which is always, in the absence of CI.

---

## R-01 — Synchronous database and HTTP calls block the event loop
**Severity: High | Confidence: High | Blast radius: Degraded latency for all concurrent users**

Sync `psycopg2` (`database.py:71`) invoked from `async def` handlers:
- `app/routers/reports.py:141` `list_reports` → `get_health_reports`
- `app/routers/reports.py:173` `get_report_detail` → `get_health_report_detail`
- `app/routers/reports.py:200` `get_medical_reports` → `get_user_medical_reports`
- `seniocare/tools/image_tools.py:16` `store_medical_report` (`async def`) → `:54` sync connect

Sync `requests` in tool paths:
- `seniocare/tools/web_search.py:69` — `timeout=10`, arbitrary URL fetch
- `seniocare/tools/web_search.py:159` — `timeout=15`, SerpAPI

Each of these stalls **every** concurrent request for its full duration. A 15-second SerpAPI timeout freezes the whole server for 15 seconds.

Compounded by the absence of pooling: `get_connection()` (`database.py:71`) performs a fresh TCP + TLS handshake to Neon per call, and `interactions.py:63-68` does this inside a nested loop.

---

## R-02 — N+1 query patterns
**Severity: Medium | Confidence: High | Blast radius: Latency, Neon connection exhaustion**

| Location | Pattern | Worst case |
|---|---|---|
| `interactions.py:63-68` | Nested loop, one query per (drug, food) pair | 5 meds × 20 ingredients = **100 queries** |
| `symptoms.py:101-104` | One precautions query per matched disease, inside the loop | 15 queries |
| `reports.py:223-229` | One `get_session` per session | 10 round-trips |

`interactions.py:67` additionally defeats its own index via `LOWER()` on the column.

---

## R-03 — Caregiver registration is a lock-free read-modify-write
**Severity: Medium | Confidence: High | Blast radius: Lost registration — a caregiver silently stops receiving emergency alerts**

`app/routers/user_profile.py:196-237` reads `user:caregivers` (`:200`), mutates the list in memory (`:216-224`), and writes it back through a second temp session (`:229-237`). Between read and write there is a `delete_session` round-trip (`:226`).

Two caregivers registering concurrently for the same elder: both read the same list, both append, the second write overwrites the first. **The lost caregiver receives no emergency notifications and gets no error.**

The same pattern appears in `preferences.py:36-68`, where two tool calls in one turn can lose a preference.

---

## R-04 — No timeout on any LLM call
**Severity: Medium | Confidence: High | Blast radius: Indefinite hang**

No timeout is configured at any of the five LLM call sites. `reports.py:461`'s `async for event in runner.run_async(...)` has no wrapping `asyncio.wait_for`. A stalled Ollama process hangs the request forever; with `R-01`, it hangs the whole worker.

Note that `pytest.ini:7` attempts a 30-second test timeout but the plugin is not installed, so even the test suite has no timeout protection.

---

## R-05 — The report Runner concatenates text from every event, not just the final response
**Severity: Medium | Confidence: Medium — **[NEEDS RUNTIME CONFIRMATION]** | Blast radius: Polluted report content**

`seniocare/tools/reports.py:460-471`:
```python
response_text = ""
async for event in runner.run_async(...):
    if event.content and event.content.parts:
        for part in event.content.parts:
            if part.text:
                response_text += part.text
```
There is no filter on `event.is_final_response()`, no author check, and no partial/streaming-chunk guard. Any intermediate event carrying text is concatenated into the stored report.

**[NEEDS RUNTIME CONFIRMATION]** — whether ADK 1.22.0 emits intermediate text events for a single tool-less `LlmAgent`. If it emits streaming partials, the report will contain the response duplicated or interleaved. Confirm by logging `event.author`, `event.partial`, and `event.is_final_response()` for one report generation.

---

## R-06 — Session-state pollution from the temp-session pattern
**Severity: Low-Medium | Confidence: High | Blast radius: Wrong data in the user's conversation list**

`app/routers/chat_history.py:29-30` filters out internal sessions by one prefix only:
```python
if session.id.startswith("_profile_"):
    continue
```
But temp sessions are created with six prefixes: `_profile_setup_` / `_profile_read_` / `_profile_sync_` (`user_profile.py:35,88,171`), `_notif_` (`reports.py:102`), `_fcm_reg_` / `_fcm_write_` (`user_profile.py:196,229`), `_sched_read_` (`scheduler.py:82`), `_report_profile_` (`reports.py:155`).

Only the three `_profile_*` variants are filtered. If any `delete_session` call fails or the process dies between create and delete, an orphaned `_notif_`, `_fcm_reg_`, or `_sched_read_` session appears in the user's chat history as a conversation titled "💬 محادثة جديدة".

---

## Generated boilerplate never adapted to this codebase

Called out separately as the brief requests.

| Item | File:line | Evidence it was never adapted |
|---|---|---|
| Two non-existent image tools in the planner prompt | `orchestrator_agent.py:225-239` | Names appear nowhere in `seniocare/tools/`; contradicted by `feature_agent.py:211` |
| Two model names referenced but never configured | `orchestrator_agent.py:228,236` | `richardyoung/olmocr2:7b-q8`, `llama3.2-vision` — absent from all config |
| Medication-schedule output field | `feature_agent.py:242` | References the deleted `seniocare/tools/medication.py` |
| Two RESPONSE_TYPEs with no Formatter template | `feature_agent.py:233` declares `emotional_support` and `routine`; `formatter_agent.py:99-183` provides templates for meal, exercise, preference, symptom, medical Q&A only | `emotional` and `routine` are valid intents (`orchestrator_agent.py:134-137`) that reach the Formatter with no template |
| Dead `neutral_interactions` branch | `interactions.py:92` filters `effect == "no_effect"` | The seed data contains only `negative` and `positive` — verified. Always `[]` |
| Broken `pytest.ini` options | `pytest.ini:6-7` | `asyncio_mode`, `timeout` — neither plugin installed |
| `MEMORY_SERVICE_URI = None` with live consumer | `app/config.py:63`; consumed at `main.py:41` and `callbacks.py:189-192` | The memory-save block at `callbacks.py:187-194` can never succeed; it silently prints a warning on every single turn |
| `/reports/seed` in production | `app/routers/reports.py:225-227` | Unauthenticated endpoint that writes and, with `clear=true`, **deletes** report data |
| Deprecated FastAPI lifecycle | `main.py:60,71` | `@app.on_event` — removed idiom in current FastAPI |
| Health check that checks nothing | `app/routers/health.py:10-25` | Returns static strings; no DB ping, no Ollama probe, no scheduler check |
| `/run_sse` absent from OpenAPI | `app/openapi.py:13-23` | `_CUSTOM_PATHS` omits the primary chat endpoint — the one the Flutter client depends on is undocumented in Swagger |
| README documents non-existent endpoints | `README.md:115-116` | `POST /analyze-medication-image`, `POST /analyze-medical-report` — no such routes exist |
| Tracked scratch files | `.gemini_scratch/list_cells.py`, `Gemma4_ADK_Server (1).ipynb` (240 KB) | Both tracked in git |
| `app_name="seniocare"` hardcoded | 8 sites incl. `chat_history.py:21`, `user_profile.py:38`, `scheduler.py:84` | `APP_NAME` exists at `app/config.py:23` and is never imported |

---

## Findings summary

| ID | Finding | Severity | Confidence |
|---|---|---|---|
| C-01 | No authentication on health-data endpoints | Critical | High |
| C-02 | Safety routing enforced by prose, not control flow | Critical | High |
| C-03 | `SAFETY_STATUS` never read by any code | Critical | High |
| C-04 | Tool guards persist across turns, blocking all later calls | Critical | High / runtime |
| C-05 | Preference conflict-resolution silently no-ops for dislikes | High | High |
| C-06 | Orchestrator plans two non-existent tools | High | High |
| C-07 | Report date range ignored for conversation data | High | High |
| C-08 | Four aggregation fields declared, read, never populated | High | High |
| C-09 | Emergency notify is GC-eligible fire-and-forget | High | High |
| C-10 | Report status silently defaults to "moderate" | High | High |
| C-11 | Fabricated patient profile injected when identity missing | High | High |
| C-12 | Symptom over-matching escalates mild input to EMERGENCY | High | High |
| C-13 | English-only symptom DB vs Arabic users | High | Medium |
| C-14 | Exact-match drug/allergen joins masked by hand-tuned seeds | Med-High | High |
| C-15 | Nutrient filter passes meals with NULL values | Medium | High |
| C-16 | `/reports/medical/{user_id}` unreachable — route shadowing | High | High (verified) |
| R-01 | Sync DB/HTTP blocks the event loop | High | High |
| R-02 | N+1 query patterns | Medium | High |
| R-03 | Lock-free read-modify-write on caregivers | Medium | High |
| R-04 | No LLM timeout anywhere | Medium | High |
| R-05 | Report Runner concatenates all events | Medium | Medium |
| R-06 | Temp-session prefix filter is incomplete | Low-Med | High |

## Experiments needed to close open questions

Ordered by information value per minute:

1. **C-13** — call `assess_symptoms(["ألم في الصدر"])` directly; assert `overall_severity`. (~5 min)
2. **C-04** — two consecutive meal requests in one session; assert both return `status: "success"`. (~10 min)
3. **C-02 / C-03** — 50 emergency-phrased inputs; count how many produce `INTENT: emergency` verbatim, and how many trigger a stage-2 tool call. (~1 hr with the harness in `evals/runner.py`)
4. **C-08** — generate 10 reports; count clinical assertions unsupported by the input JSON. (~30 min, human review)
5. **R-05** — log `event.author`, `event.partial`, `event.is_final_response()` for one report generation. (~10 min)
6. **0.1** — confirm whether async tests actually execute given the missing `pytest-asyncio`. (~5 min)
