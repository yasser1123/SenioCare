# SenioCare

An AI healthcare assistant for elderly Egyptian users. A three-stage agent pipeline screens each message for safety, gathers data from a health database, and replies in Egyptian Arabic. Every LLM call, tool call and turn is measured, and the pipeline's behaviour is scored by a reproducible evaluation suite.

Built on the [Google Agent Development Kit](https://google.github.io/adk-docs/) (ADK 1.22) with FastAPI and PostgreSQL. The model is reached through LiteLLM and configured by environment: local Ollama by default, or any remote OpenAI-compatible server (for example a GPU on Colab) or hosted provider.

> **Status: graduation project.** The static audit in [`docs/AUDIT.md`](docs/AUDIT.md) found 22 correctness and security defects; the branch this README describes fixes them one commit each (`git log --grep C-04`). What was learned by running the system is in [`docs/FINDINGS.md`](docs/FINDINGS.md); the before/after numbers are in [`docs/RESULTS.md`](docs/RESULTS.md). It is still not a medical device — see [Safety](#safety-and-medical-disclaimer).

---

## What it does

A user sends a message in Egyptian Arabic. The root agent (`seniocare/pipeline.py`) runs:

1. **Orchestrator** — classifies safety (`EMERGENCY` / `BLOCKED` / `ALLOWED`), classifies intent, and writes a tool-calling plan. No tools.
2. **Routing, in code** — the Orchestrator's output is parsed; `EMERGENCY` and `BLOCKED` skip stage 2 entirely and the relay message is synthesised from the Orchestrator's own text. Unparseable output fails open and is flagged.
3. **Feature** — executes the plan against 10 tools, picks the best option, packages the result. Runs only for `ALLOWED` requests.
4. **Formatter** — renders the package as warm Egyptian Arabic using per-intent templates.

A separate Report agent generates health reports on a schedule or on demand and pushes notifications to caregivers; an emergency detected in conversation triggers one immediately.

### Capabilities

| Capability | Where |
|---|---|
| Safety screening and emergency detection, enforced by control flow | `seniocare/routing.py`, `seniocare/pipeline.py` |
| Condition- and allergy-aware meal recommendations | `seniocare/tools/nutrition.py` |
| Drug–food interaction screening (normalised drug names) | `seniocare/tools/interactions.py` |
| Symptom assessment in Arabic or English, evidence-based escalation | `seniocare/tools/symptoms.py`, `seniocare/tools/_text.py` |
| Mobility-aware exercise recommendations | `seniocare/tools/exercise.py` |
| Cross-session food and exercise preferences | `seniocare/tools/preferences.py` |
| Web, YouTube, and medical search (SerpAPI) | `seniocare/tools/web_search.py` |
| Medical-report findings storage | `seniocare/tools/image_tools.py` |
| Scheduled and emergency health reports from real conversation facts | `seniocare/tools/reports.py`, `app/scheduler.py` |
| Caregiver push notifications (FCM) | `app/notifications.py` |
| Per-user authorisation with Firebase ID tokens | `app/auth.py` |
| Structured JSON logs, per-stage tokens/latency/cost, `llm_traces` table | `seniocare/observability.py`, `GET /metrics/summary` |
| Evaluation suite: 54 cases / 60 turns, multi-turn, before/after comparison | `evals/` |

**Multimodal note.** Images are handled natively by the model through `/run_sse`; there are no image-upload endpoints and no image-analysis tool. `store_medical_report` persists what the model read from a report image.

---

## Architecture

```mermaid
graph LR
    U(["User"]) --> API["FastAPI · auth middleware<br/>/run_sse"]
    API --> CB["populate_user_data<br/>profile + history"]
    CB --> O["1 · Orchestrator<br/>safety + intent + plan"]
    O --> R{"route()<br/>seniocare/routing.py"}
    R -->|ALLOWED| F["2 · Feature<br/>tools + decision"]
    R -->|BLOCKED / EMERGENCY| M["3 · Formatter<br/>Egyptian Arabic"]
    F --> M
    M --> U
    F --> T["10 tools · thread pool"]
    T --> DB[("PostgreSQL")]
    T --> S[("SerpAPI")]
    M --> AC["auto_save_to_memory"]
    AC -->|"EMERGENCY (status or intent)"| RP["Report agent"]
    RP --> FCM["FCM → caregivers"]
    O -. llm_call / stage records .-> OBS[("observability<br/>JSON logs + llm_traces")]
    F -. tool_call records .-> OBS
```

Full call graph, state model and data model: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

### Agents

| Agent | Role |
|---|---|
| Orchestrator | Safety, intent, planning |
| Feature | Tool execution and selection (ALLOWED only) |
| Formatter | Egyptian Arabic rendering |
| Report | Health report generation |

All four use the same model, built once by `get_model()` in `seniocare/model.py` from the `MODEL_*` environment variables. Every agent carries the observability callbacks (`stage_callbacks()`), so each model and tool call is recorded.

### Tools

The ten tools registered on the Feature Agent (`seniocare/sub_agents/feature_agent.py`). They are synchronous functions wrapped by `threaded()` so they run in a thread pool instead of blocking the event loop.

| Tool | Does |
|---|---|
| `get_meal_options` | Meals filtered by condition nutrient limits and allergens; meals with unknown nutrients are excluded and reported |
| `get_meal_recipe` | Full recipe for a selected meal |
| `check_drug_food_interaction` | Screens foods against the user's medications, one query |
| `assess_symptoms` | Matches symptoms (Arabic or English) to diseases; `is_emergency` needs two matched symptoms or ≥50 % confidence, weaker emergency hits are listed as `possible_emergency` |
| `get_exercises` | Exercises for the user's mobility level, minus contraindications |
| `save_user_preference` | Persists likes/dislikes to cross-session state; a dislike removes the matching like |
| `search_web` | General web search with content extraction |
| `search_youtube` | Video tutorials |
| `search_medical_info` | Search restricted to trusted medical domains |
| `store_medical_report` | Stores medical-report findings to the database |

Each tool has a per-turn re-entrancy guard (`seniocare/tools/_guards.py`): a second call in the same turn returns `already_called`; the next turn runs it again.

---

## Model configuration

The backend consumes the model like an external API. Tools, prompts, sessions and the database run here; only inference happens wherever `MODEL_API_BASE` points. The model receives tool *schemas* and returns tool-call requests that ADK executes in this process, so moving inference needs no tool changes.

| Target | `MODEL_NAME` | `MODEL_API_BASE` | `MODEL_API_KEY` |
|---|---|---|---|
| Local Ollama (default) | `ollama_chat/gemma4:e4b` | *(blank)* | *(blank)* |
| Ollama on Colab | `openai/gemma4:e4b` | `https://<tunnel>/v1` | *(blank)* |
| vLLM on Colab | `hosted_vllm/google/gemma-3-4b-it` | `https://<tunnel>/v1` | *(blank)* |
| Google AI Studio | `gemini/gemini-2.5-flash` | *(blank)* | your key |
| Groq, OpenRouter, any OpenAI-compatible | `openai/<model>` | provider URL | provider key |

Optional: `MODEL_TIMEOUT_S` (default 120), `MODEL_TEMPERATURE`, `MODEL_MAX_TOKENS`, `MODEL_EXTRA_JSON` for any other `litellm.completion` kwarg.

**Colab.** `colab/SenioCare_Model_Server.ipynb` (generated from `colab/build_notebook.py`) installs Ollama or vLLM on the Colab GPU, exposes an OpenAI-compatible endpoint through a cloudflared or ngrok tunnel, runs a tool-calling gate, and prints the three `.env` lines to paste. Then, from the backend:

```bash
python scripts/check_model.py --adk
```

runs reachability, a completion, a tool call, a tool-result round trip and ADK's own tool loop against the configured endpoint. Run it after every Colab restart; the tunnel URL changes.

---

## Getting started

### Prerequisites

- **Python 3.12** (CI runs 3.12; 3.10+ should work)
- **A model server.** By default [Ollama](https://ollama.com/) on this machine with the model pulled (`ollama pull gemma4:e4b`), or a remote endpoint per [Model configuration](#model-configuration). The model must support tool calling; `scripts/check_model.py` tells you.
- **PostgreSQL** — two databases (or two schemas): one for tools data, one for ADK sessions. [Neon](https://neon.tech/) works. Connections are pooled with connect and query deadlines.
- *Optional:* **SerpAPI key** — without it the three search tools return a structured error and the rest of the pipeline continues.
- *Optional:* **Firebase service-account JSON** — needed for push notifications and for `AUTH_MODE=firebase`.

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
| `APP_DATABASE_URL` | **Yes** | Tools database |
| `SESSION_DB_URL` | **Yes** | ADK session store (falls back to local SQLite if unset) |
| `MODEL_NAME`, `MODEL_API_BASE`, `MODEL_API_KEY` | No | Model; defaults to local Ollama |
| `AUTH_MODE` | No | `firebase` or `off`. Unset: `firebase` when the Firebase file exists, else `off` (announced at startup) |
| `ADMIN_UIDS` | No | Firebase uids allowed on `/metrics`, `/dev-ui`, `/debug`, eval sets |
| `SERPAPI_KEY` | No | Web/YouTube/medical search |
| `FIREBASE_CREDENTIALS_PATH` | No | FCM service account and token verification |
| `OBS_DB_ENABLED`, `COST_REFERENCE_MODEL`, `MODEL_GPU_USD_PER_HOUR`, `SERPAPI_USD_PER_SEARCH` | No | Observability and cost views |
| `JUDGE_MODEL`, `JUDGE_API_KEY`, `JUDGE_API_BASE` | No | LLM judge for the eval suite |
| `DEV_TEST_USER` | No | `1` injects the built-in test profile for requests without a profile (dev only) |
| `PORT` | No | Server port, default 8080 |
| `TEST_DATABASE_URL` | No | Test database. **Fixtures DROP all tables — never point this at anything you care about** |

`SESSION_DB_URL` is rewritten to add the `+asyncpg` prefix and strip `sslmode` / `channel_binding`, which asyncpg rejects. Supply a normal `postgresql://` URL.

### Run

```bash
python main.py
```

Serves on `http://localhost:8080`. Swagger UI at `/docs`. Tables are created and seeded on first import. The startup banner shows the resolved model, endpoint and auth mode; `GET /health` shows the same plus live checks.

---

## API

All routes except `/health`, `/docs`, `/openapi.json`, `/redoc` and `/list-apps` require `Authorization: Bearer <Firebase ID token>` when `AUTH_MODE=firebase`. A request may act on `user_id` U when the token's uid is U or is listed in U's `user:caregiver_ids`.

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

Responses stream as SSE events. Render events whose `author` is `formatter_agent` — that is the only user-facing stage. Every response carries an `X-Trace-Id` header that matches the JSON log records for that request.

### Custom endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Config plus live checks: DB `SELECT 1`, model-server reachability, auth mode. `?probe=full` also sends a one-token completion |
| `GET` | `/metrics/summary?hours=24` | p50/p95 latency and tokens per stage, cost per turn, intent and safety distribution, tool latency and guard hits, SerpAPI spend, emergency escalation outcomes (admin) |
| `POST` | `/create-session` | Create a session, returns `session_id` |
| `GET` | `/chat-history/{user_id}` | List conversations with headlines |
| `GET` | `/chat-history/{user_id}/{session_id}` | Full turns for one conversation |
| `POST` | `/set-user-profile/{user_id}` | Create/replace the health profile (`caregiver_ids` is the caregiver allow-list) |
| `GET` | `/get-user-profile/{user_id}` | Read the health profile |
| `POST` | `/sync-user-profile/{user_id}` | Partial profile update |
| `POST` | `/register-caregiver-fcm` | Register a caregiver device token (caller must be that caregiver) |
| `POST` | `/reports/generate` | Generate a report (`daily`/`weekly`/`monthly`/`emergency`) for a period |
| `GET` | `/reports/{user_id}` | List a user's reports |
| `GET` | `/reports/{user_id}/{report_id}` | One report in full |
| `GET` | `/reports/medical/{user_id}` | Stored medical-report analyses |
| `POST` | `/reports/seed` | Insert sample data. Exists only when `AUTH_MODE=off` |

---

## Observability

`seniocare/observability.py` emits one JSON record per LLM call, tool call, stage, turn, metered search, emergency escalation and HTTP request, to stdout and (when a database is configured) to the `llm_traces` table. Each turn record carries end-to-end latency, tokens, three cost views (list price at a reference hosted model, GPU-hour × wall time, SerpAPI), the parsed intent and safety status with parse flags, the stages that ran, tool guard hits and errors.

```bash
python scripts/metrics_report.py --hours 24            # Markdown tables
python scripts/metrics_report.py --csv-dir out/metrics # plus CSVs
```

ADK already creates OpenTelemetry spans for every model and tool call; set `OTEL_EXPORTER_OTLP_ENDPOINT` to ship them to any OTLP collector. Design and rationale: [`docs/INSTRUMENTATION.md`](docs/INSTRUMENTATION.md).

---

## Testing

```bash
# Pure tests (routing, guards, text matching, auth, observability, eval assertions): no DB needed
python -m pytest tests -q

# Tool tests need a database. Either a disposable one (fixtures DROP every table)…
export TEST_DATABASE_URL='postgresql://user:pass@host/seniocare_test?sslmode=require'
# …or, locally, the configured APP_DATABASE_URL (read-only queries, slower)
python -m pytest tests -q
```

Without any database the DB-backed tests skip with an explicit reason. CI (`.github/workflows/ci.yml`) runs the whole suite against a PostgreSQL service on every push.

### Agent evaluation

[`evals/`](evals/) holds 54 cases (60 turns) in Egyptian Arabic across every route the code can take, including six multi-turn scenarios that probe the defects only visible across turns.

```bash
python evals/runner.py --dry-run                 # validate cases
python evals/runner.py --name my-run             # run in-process, results in evals/results/my-run/
python evals/runner.py --filter emergency- --judge-human
python evals/compare.py baseline-colab fixed-colab
```

Each run writes `results.jsonl`, `summary.md`/`summary.json` (routing accuracy, safety confusion matrix, tool precision/recall, guard-hit rate, silent-failure counts, latency/tokens/cost) and `human_review.csv` for the cases a person must judge. Schema, assertion tiers and the categories that cannot be automated: [`evals/schema.md`](evals/schema.md). Protocol and threats to validity: [`docs/EXPERIMENTS.md`](docs/EXPERIMENTS.md).

---

## Safety and medical disclaimer

For **informational and support purposes only**.

- It does **not** diagnose. Diagnosis requests are refused by the Orchestrator and the refusal path skips the tools.
- It does **not** prescribe or adjust dosages.
- It screens for emergency language, directs users to emergency services (123), and notifies registered caregivers.
- It advises consulting a qualified provider.

The safety path now runs in code rather than prose, and its behaviour is measured (`docs/RESULTS.md`), but the model can still misclassify, the symptom database is small (15 conditions), and the human-review tier of the evaluation has not been completed. Do not rely on this system for real medical safety.

---

## Known limitations

- **Single-process assumptions.** The caregiver-registration lock and the auth caregiver cache are per process; a multi-worker deployment needs a shared lock/cache.
- **No token revocation check, no rate limiting, no audit log, no data-deletion path.** CORS still allows `*`.
- **Prompt size.** Each turn sends ~10,000 prompt tokens across three stages (`docs/FINDINGS.md` F-03); no prompt caching or compression yet.
- **Symptom coverage.** 15 conditions, 81 symptom phrases, one synonym table; not a clinical knowledge base.
- **Human-review tier pending.** Emergency adequacy, clinical appropriateness and dialect are triaged, not verified.
- **No migrations, no Docker, no lock file.** Schema is `CREATE TABLE IF NOT EXISTS` at import.

---

## Project layout

```
main.py                     FastAPI entry point: lifespan, auth + trace middleware, routers
app/
  auth.py                   Firebase ID-token auth, per-user authorisation (ASGI middleware)
  config.py                 Env parsing, model info, shared DatabaseSessionService
  metrics_queries.py        SQL aggregations over llm_traces
  notifications.py          FCM push notifications
  openapi.py                Custom OpenAPI schema
  scheduler.py              APScheduler report jobs
  routers/                  health, metrics, sessions, chat_history, user_profile, reports
  schemas/                  Pydantic request models
seniocare/
  agent.py                  Root agent (SenioCarePipeline) + root callbacks
  pipeline.py               Orchestrator -> route() -> Feature -> Formatter
  routing.py                Pure routing decision from the Orchestrator's output
  callbacks.py              Profile/history loading, emergency trigger, turn record
  model.py                  Provider-agnostic model factory (MODEL_* env)
  observability.py          emit(), ADK callbacks, cost views, Postgres sink
  sub_agents/               orchestrator, feature, formatter, report
  tools/                    10 agent tools + _guards, _text, _async helpers
  data/
    database.py             Schema, seeding, pooled connections with deadlines
    seeds/*.json            Seed data incl. symptom_synonyms_ar.json
colab/                      Model-server notebook + its generator
scripts/                    check_model.py, metrics_report.py
evals/                      Cases, runner, compare, rubrics, results
tests/                      Pure tests + DB-backed tool tests
docs/
  AUDIT.md                  Static audit: findings, severities, citations
  FINDINGS.md               What running the system revealed (F-01…)
  PLAN.md                   Phased plan and status
  ARCHITECTURE.md           Call graph, state flow, data model
  INSTRUMENTATION.md        Measurement design
  EXPERIMENTS.md            Eval protocol and threats to validity
  RESULTS.md                Baseline vs post-fix numbers
```

---

## License

[MIT](LICENSE)
