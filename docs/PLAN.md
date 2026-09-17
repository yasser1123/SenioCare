# SenioCare — Hardening, Observability & Evaluation Plan

**Branch:** `feat/hardening` (from `main` @ `8d88d81`)
**Input:** `docs/AUDIT.md` (22 findings + boilerplate table), `docs/INSTRUMENTATION.md`, `evals/`
**Goal:** a pipeline whose safety routing is enforced by code, whose every LLM/tool call is measured, and whose behaviour is quantified by a reproducible eval — before/after — so the numbers can go straight into the research paper.

Every step below is one commit (sometimes two). Commit messages reference the finding ID so `git log --grep C-04` finds the fix.

---

## Ordering and why

```
Phase 0  Baseline & hygiene
Phase 1  Provider-agnostic model + Colab model server      ← unblocks GPU runs
Phase 2  Observability & cost                              ← must exist BEFORE measuring
Phase 3  Eval harness (assertions, multi-turn, reporting)  ← must exist BEFORE fixing
         ▶ BASELINE RUN on the unfixed pipeline (tag: eval-baseline)
Phase 4  Correctness fixes, one commit per finding
         ▶ POST-FIX RUN (tag: eval-fixed)
Phase 5  Results, paper tables, docs refresh
```

Fixes come **after** the harness on purpose. The paper needs a before/after table, and "before" can only be measured on the unfixed code. Fixing first would destroy the baseline. If you prefer fixes first, the cost is that the baseline has to be reconstructed from a `git worktree` of the pre-fix tag, which is doable but messier.

---

## Phase 0 — Baseline & hygiene

| # | Commit | What | Why |
|---|---|---|---|
| 0.1 | `chore: carry over local hygiene changes` | The uncommitted changes already on `main`: SerpAPI key moved to env (`web_search.py`), lazy DB init (`database.py`, `agent.py`), tests migrated to Postgres (`conftest.py`, `test_database_tools.py`), two dead test files removed, `requests`/`bs4`/`pytest` in requirements | These were sitting uncommitted; the branch needs a clean base |
| 0.2 | `docs: audit deliverables + development plan` | `docs/AUDIT.md`, `docs/INSTRUMENTATION.md`, `docs/ARCHITECTURE.md`, `docs/PLAN.md`, `evals/`, rewritten `README.md`, `.env.example` | Untracked audit output |
| 0.3 | `chore: untrack scratch files, fix pytest config` | Remove `.gemini_scratch/`, `Gemma4_ADK_Server (1).ipynb` (240 KB) from git; add `pytest-timeout` to requirements (the `timeout =` line in `pytest.ini` is currently ignored) | Boilerplate table in AUDIT |
| 0.4 | `ci: unit tests + eval dry-run on push` | `.github/workflows/ci.yml`: `pytest tests/unit`, `python evals/runner.py --dry-run`, `python -m compileall`. No DB, no model | The repo has zero CI. Hiring-relevant on its own |

**⚠ Security note for 0.1:** the removed SerpAPI key `fa3aa24b…` is still in git history (commit `8d88d81` and earlier). Removing it from the working tree does not revoke it. **Rotate the key at serpapi.com.** Rewriting history is not worth it on a public repo that has already been cloned.

---

## Phase 1 — Provider-agnostic model + Colab model server

The existing `feat/colab-remote-model` branch already did half of this but is Ollama-specific (`OLLAMA_BASE_URL`) and is based on a stale `main`. This phase supersedes it; that branch can be deleted afterwards.

### 1.1 `seniocare/model.py` — one factory, any provider

```python
# .env
MODEL_NAME=ollama_chat/gemma4:e4b          # any LiteLLM model string
MODEL_API_BASE=                            # blank = provider default
MODEL_API_KEY=                             # blank = provider default / none
MODEL_TIMEOUT_S=120                        # closes R-04
MODEL_TEMPERATURE=0.2
MODEL_MAX_TOKENS=2048
```

`get_model()` returns `LiteLlm(model=MODEL_NAME, api_base=…, api_key=…, timeout=…, temperature=…, max_tokens=…)`. Verified that `LiteLlm.__init__(model, **kwargs)` forwards these to `litellm.completion` (`lite_llm.py:1584-1600`).

The same backend then talks to any of these with only `.env` changes:

| Target | `MODEL_NAME` | `MODEL_API_BASE` |
|---|---|---|
| Local Ollama | `ollama_chat/gemma4:e4b` | *(blank)* |
| Colab, Ollama backend | `openai/gemma4:e4b` | `https://<tunnel>/v1` |
| Colab, vLLM backend | `hosted_vllm/google/gemma-3-4b-it` | `https://<tunnel>/v1` |
| Google AI Studio | `gemini/gemini-2.5-flash` | *(blank)* + `MODEL_API_KEY` |
| Groq / OpenRouter / any OpenAI-compatible | `openai/<model>` | provider URL + key |

Replaces the four hardcoded `LiteLlm(model="ollama_chat/gemma4:e4b")` sites. Startup banner prints model + base. `GET /health` gains a real model probe (closes the "health check that checks nothing" item).

### 1.2 `colab/SenioCare_Model_Server.ipynb` — model only, OpenAI-compatible

Cells, in order:

1. **Config** — `BACKEND = "ollama" | "vllm"`, `MODEL`, `TUNNEL = "cloudflared" | "ngrok"`. Cloudflared needs no account and no token; ngrok gives a stable subdomain on a paid plan.
2. **Install + serve** — Ollama with `OLLAMA_HOST=0.0.0.0` and `OLLAMA_KEEP_ALIVE=-1`, or vLLM `--served-model-name`. Both expose `/v1/chat/completions`.
3. **Local smoke test** — plain chat, then a **tool-calling smoke test** with a real function schema. This is the gate: if the model cannot emit a well-formed `tool_calls` array here, stage 2 will not work remotely either. The notebook prints PASS/FAIL explicitly.
4. **Tunnel** — prints the three `.env` lines to paste, verbatim.
5. **Keep-alive + health loop** — logs GPU memory and request count every 60 s.
6. **Shutdown**.

The notebook never touches tools, DB, or prompts. Tools execute in the FastAPI process; the model only ever sees their schemas.

### 1.3 `scripts/check_model.py`

Runs from the backend with the real `.env`: connectivity, latency of one completion, and a tool-call round trip through the exact `LiteLlm` object the agents will use. Run this before starting the app after every Colab restart (the tunnel URL changes).

**Known costs:** Colab free tier idles out at ~90 min and hard-stops at ~12 h; the URL changes on every restart; Colab ToS discourages tunnelled serving. Fine for driving experiments, not for an unattended demo.

---

## Phase 2 — Observability & cost

Design is already in `docs/INSTRUMENTATION.md`; this phase implements it. **Zero new backend dependencies**: `opentelemetry-sdk` and the OTLP HTTP exporter are already installed transitively by `google-adk`, and ADK's own `maybe_set_otel_providers` reads `OTEL_EXPORTER_OTLP_ENDPOINT` from the environment.

| # | Commit | What |
|---|---|---|
| 2.1 | `obs: structured logging + trace_id middleware` | `app/observability.py`: `configure_logging()` (JSON lines, called first thing in `main.py`), `emit(record)` single sink, `trace_id` per HTTP request via middleware, `user_id` hashed (truncated SHA-256) never raw. Fixes the silently-dead loggers in `notifications.py` / `scheduler.py` |
| 2.2 | `obs: per-stage LLM metrics via model callbacks` | `before_model_callback` / `after_model_callback` attached to all four `LlmAgent`s: `stage`, `model`, `latency_ms`, `prompt_tokens`, `completion_tokens` (from `LlmResponse.usage_metadata`, populated by LiteLLM at `lite_llm.py:1171`), `finish_reason`, `error` |
| 2.3 | `obs: tool metrics via tool callbacks` | `before_tool_callback` / `after_tool_callback` on the Feature Agent: `tool`, `latency_ms`, `already_called` (direct measurement of C-04), `error`, `result_status`. SerpAPI call counter by engine |
| 2.4 | `obs: pipeline-level metrics` | Per turn: `intent`, `safety_status`, `intent_parse_ok`, `safety_parse_ok` (quantifies C-03), `response_type`, `stages_run`, `e2e_latency_ms`, `emergency_triggered`, `emergency_notify_result` (closes the C-09 blind spot) |
| 2.5 | `obs: cost estimation` | Three cost views on every LLM record, all in USD: **(a)** `cost_token_priced` — what these tokens would cost at a reference hosted model, via `litellm.completion_cost` / `litellm.model_cost` (configurable `COST_REFERENCE_MODEL`, default `gemini/gemini-2.5-flash`); **(b)** `cost_compute` — `MODEL_GPU_USD_PER_HOUR × latency` for self-hosted (Colab T4 ≈ $0.35/h, A100 ≈ $1.2/h, local = your electricity, default 0); **(c)** SerpAPI `USD_PER_SEARCH × calls`. Per-turn and per-session totals |
| 2.6 | `obs: persist traces to Postgres` | Table `llm_traces` (one row per LLM call, tool call, and turn; JSONB `attrs`). Written from `emit()` via a background writer so it never blocks a request. This is what the paper's tables are aggregated from |
| 2.7 | `obs: OTLP export + metrics endpoint` | Document `OTEL_EXPORTER_OTLP_ENDPOINT` (ADK already creates spans for every LLM/tool call — Jaeger or Langfuse via OTLP works with no code). `GET /metrics/summary` returns p50/p95 latency per stage, tokens, cost, intent distribution from `llm_traces` for the last N hours |
| 2.8 | `obs: scripts/metrics_report.py` | Aggregates `llm_traces` → Markdown + CSV: latency per stage (p50/p95), tokens per stage, cost per turn by intent, tool latency, `already_called_rate`, `intent_unknown_rate`, emergency escalation success |

---

## Phase 3 — Eval harness completion

`evals/runner.py` already runs the pipeline and records outputs. This phase makes it pass/fail and multi-turn.

| # | Commit | What |
|---|---|---|
| 3.1 | `eval: structural + keyword assertions` | `assert_structural` (intent, safety_status, response_type, tools_called / tools_not_called from tool events), `assert_keyword` (must/must_not contain). Uses `_extract_intent` from production code so it measures the real parser |
| 3.2 | `eval: language assertion` | Arabic-script ratio, no Latin-script sentences unless `locale=mixed`, Egyptian-dialect marker heuristic (`حضرتك`, `عايز`, `إزاي`, `دلوقتي` …) reported as a score, not a gate — §4.2 of `evals/schema.md` says why |
| 3.3 | `eval: LLM judge` | `assert_judge` via LiteLLM with a **different** model than the pipeline (`JUDGE_MODEL`, default `gemini/gemini-2.5-flash` on the AI Studio free tier). Rubrics in `evals/rubrics/*.md` (tone, dialect, safety adequacy). Scores 1-5 + rationale; stored, never used as a hard gate |
| 3.4 | `eval: human review queue` | `assert_human` writes the case + output to `evals/results/<run>/human_review.csv` with the rubric columns. The 20 human-category cases (emergency adequacy, clinical correctness) go here |
| 3.5 | `eval: multi-turn runner + cases` | `run_multi_turn` implemented; `evals/cases/06_multiturn.jsonl` — two meal requests in one session (C-04), preference then meal (does the preference apply?), symptom then emergency (escalation across turns) |
| 3.6 | `eval: per-case metrics + summary report` | Each result carries the Phase 2 metrics (latency per stage, tokens, cost). `summary.md` per run: routing accuracy, safety confusion matrix (ALLOWED/BLOCKED/EMERGENCY, 3×3), refusal rate, tool-call precision/recall, parse failure rate, mean cost/turn, p50/p95 latency |
| 3.7 | `eval: compare two runs` | `python evals/compare.py <run_a> <run_b>` → before/after table with deltas. This *is* the paper's results table |

**▶ Baseline run.** `git tag eval-baseline`; run all 48 + multi-turn cases against the unfixed pipeline, locally and on Colab GPU. Archive `evals/results/baseline-local/` and `baseline-colab/`. Commit the results (they are small JSONL).

---

## Phase 4 — Correctness fixes (one commit each)

Ordered by severity, then by dependency. Each commit adds or updates a test where the behaviour is unit-testable; prompt-only changes are validated by the eval run.

### Critical

| # | Finding | Fix | Test |
|---|---|---|---|
| 4.1 | **C-04** tool guards persist across turns | Rename the six `_*_tool_called` keys to `temp:` prefix (ADK discards `temp:` state at the end of each invocation). Guards still stop duplicate calls *within* a turn | Multi-turn eval case + unit test that a fresh `ToolContext` state does not short-circuit |
| 4.2 | **C-03** `SAFETY_STATUS` never read | `after_agent_callback` on the Orchestrator parses `SAFETY_STATUS`, `INTENT` into `temp:safety_status`, `temp:intent`, `temp:orchestrator_parse_ok`. Parsing is tolerant (case, whitespace, markdown bold) but records whether it had to be | Unit tests on the parser with 20 malformed variants |
| 4.3 | **C-02** routing by prose | Replace `SequentialAgent` with `SenioCarePipeline(BaseAgent)` whose `_run_async_impl` runs Orchestrator → **if `temp:safety_status ∈ {EMERGENCY, BLOCKED}` skip the Feature Agent** → Formatter. The Feature Agent's ten tools are never bound on the safety path. Unparseable orchestrator output → fail-safe: run the Feature Agent but flag `parse_ok=false` in metrics | Eval: `tools_not_called` assertions on all emergency/blocked cases; unit test on routing decision |
| 4.4 | **C-09** GC-eligible emergency task | Module-level `_BACKGROUND_TASKS: set[Task]` with a done-callback that logs exceptions and emits `emergency_notify_result`. Emergency trigger keys off `temp:safety_status == EMERGENCY` **or** `intent == emergency` | Unit test: task is retained and result is recorded |
| 4.5 | **C-01** no auth | Firebase ID-token verification (`firebase-admin` is already a dependency and the Flutter app already uses Firebase for FCM). ASGI middleware so ADK's `/run_sse` and `/apps/…` routes are covered too, not just the custom routers. Token `uid` must equal the `user_id` in path/body, or be a registered caregiver of it. `AUTH_MODE=off` for local dev; `/reports/seed` and the `TEST_USER_PROFILE` path only exist when `AUTH_MODE=off` | Tests with a fake verifier: 401 without token, 403 on uid mismatch, caregiver allowed |

### High

| # | Finding | Fix | Test |
|---|---|---|---|
| 4.6 | **C-11** fabricated profile | Injected only when `AUTH_MODE=off` **and** `DEV_TEST_USER=1`. Otherwise a missing profile is passed to the Orchestrator as `profile unavailable` and logged | Unit |
| 4.7 | **C-05** preference no-op | Explicit `OPPOSITE = {"food_likes": "food_dislikes", …}` map; `existing` kept as a list (dedupe with `dict.fromkeys`) | Unit: `food_dislikes` → `food_likes` |
| 4.8 | **C-06** phantom tools | Delete the two non-existent tools and the two unconfigured model names from the Orchestrator prompt; delete the medication-schedule field from the Feature Agent prompt; add Formatter templates for `emotional_support`, `routine`, `image_medication`, `image_report` | Eval: `emotional-*`, `routine-*`, `image-*` cases |
| 4.9 | **C-16** route shadowing | Move `/medical/{user_id}` and `/seed` above `/{user_id}/{report_id}` in `reports.py` | TestClient regression test (the exact one used to verify the finding) |
| 4.10 | **C-07** date range ignored | `_get_session_data_from_history(user_id, start, end)` filters `session.events` by `event.timestamp`; `aggregate_report_data` passes the range through | Unit with fabricated events |
| 4.11 | **C-08** never-populated fields | Populate `symptoms_reported`, `meals_recommended`, `exercise_plans`, `emergency_events` from `function_response` parts in the session events (real data the pipeline already produces) within the date range. Anything that cannot be populated is **removed from the prompt** rather than left as an empty array the model is invited to hallucinate from | Unit |
| 4.12 | **C-10** STATUS defaults "moderate" | Unparseable → `status="unknown"`, `parse_ok=false`, logged. Caregiver notification text says the status could not be determined | Unit |
| 4.13 | **C-12** symptom over-match | Word-boundary token matching instead of substring; rank by confidence then severity; `is_emergency` requires either confidence ≥ 0.5 or ≥ 2 matched symptoms of an EMERGENCY condition; single weak match returns `MONITOR` with an explicit "low confidence" flag | Unit: `["dizziness"]` alone must not be emergency; `["chest pain","shortness of breath"]` must |
| 4.14 | **C-13** English-only symptoms | Bilingual synonym table `seniocare/data/seeds/symptom_synonyms_ar.json` (Egyptian Arabic + MSA per symptom) + Arabic normalisation (strip tashkeel, unify alef/yaa/taa-marbuta) applied before matching | Unit: `["ألم في الصدر"]` → chest pain |
| 4.15 | **C-14** exact-match joins | Drug names normalised (lowercase, strip dose/unit suffix, strip parentheticals) on both sides; allergen match on ingredient tokens with the same normalisation | Unit: `"Metformin 500mg"` matches `metformin`; `"cheese"` allergy catches `cottage cheese` |
| 4.16 | **R-01** event-loop blocking | DB tool functions become `async def` wrapping the psycopg2 work in `asyncio.to_thread`; `requests` → `httpx.AsyncClient` (already a dependency) in `web_search.py` | Existing unit tests updated; latency visible in Phase 2 metrics |
| 4.17 | **R-02** N+1 | `check_drug_food_interaction` fetches all rows for the user's drug list in one `WHERE LOWER(drug_name) = ANY(%s)` query | Unit + tool-latency metric |

### Medium / low

| # | Finding | Fix |
|---|---|---|
| 4.18 | **C-15** NULL nutrients pass | A rule that needs a nutrient the meal does not have **fails** the meal (conservative); the response carries `nutrition_data_complete: false` so the Formatter can say so |
| 4.19 | **R-03** caregiver RMW race | Per-user `asyncio.Lock` around read-modify-write in `user_profile.py` (single-process; documented as such) |
| 4.20 | **R-05** report Runner concatenates all events | Keep only the `report_agent` event where `is_final_response()` is true |
| 4.21 | **R-06** temp-session filter | Temp sessions get `state["temp_session"] = True`; `chat_history.py` filters on the flag, not on a name prefix |
| 4.22 | Boilerplate batch | `MEMORY_SERVICE_URI` — either `InMemoryMemoryService` or delete the save block (it warns on every turn today); `@app.on_event` → `lifespan`; `APP_NAME` imported at the 8 hardcoded sites; `/run_sse` added to OpenAPI; health check probes DB + model + scheduler |

**▶ Post-fix run.** `git tag eval-fixed`; same cases, same two environments. `evals/compare.py baseline-local fixed-local` etc.

---

## Phase 5 — Results and docs

| # | Commit | What |
|---|---|---|
| 5.1 | `results: baseline vs fixed` | `docs/RESULTS.md` generated by `metrics_report.py` + `compare.py`: routing accuracy, safety confusion matrices, tool-call precision/recall, parse-failure rate, turn-2 tool-availability rate (C-04), latency p50/p95 per stage local vs Colab GPU, tokens and cost per turn by intent, judge scores, human-review outcomes |
| 5.2 | `docs: experiment protocol` | `docs/EXPERIMENTS.md` — exact commands, model versions, hardware, seeds, case counts. What the paper's Method section needs to be reproducible |
| 5.3 | `docs: refresh README + ARCHITECTURE` | New control flow (conditional pipeline, not sequential), auth, model config, observability, how to run evals. Remove the "known defects" caveats that are now fixed; keep the ones that are not |

### What the paper gets out of this

- **Ablation:** prose-routing vs code-routing on the same 55 cases — safety confusion matrix before/after.
- **Defect quantification:** turn-2 tool failure rate (C-04), `intent_unknown_rate` (C-03), false-emergency rate (C-12), Arabic symptom recall (C-13), all measured, not asserted.
- **Cost/latency:** per-stage tokens and latency, local CPU vs Colab T4, three-stage pipeline cost per turn at reference-model pricing.
- **Method:** a reproducible eval protocol for an Egyptian-Arabic health assistant with structural, keyword, judge, and human assertion tiers.

---

## Decisions already made (say so if you disagree)

1. **Auth = Firebase ID tokens.** Already a dependency, already in the Flutter app. Alternative was a home-rolled JWT; more code, less hireable.
2. **Routing = custom `BaseAgent`, not ADK `LoopAgent`/`LlmAgent` transfer.** Deterministic, testable, three lines of control flow. Agent-transfer would put routing back in the model's hands, which is the defect being fixed.
3. **Observability = JSON logs + Postgres table + optional OTLP.** No new dependencies. Langfuse/Phoenix are one env var away via OTLP if wanted later.
4. **Judge = a different provider than the pipeline model.** A `gemma4` judge would share `gemma4`'s blind spots.
5. **Cost for self-hosted = GPU-hour × wall-time, reported next to token-priced cost.** Neither alone is honest; both together are.
6. **Fixes after baseline.** See "Ordering and why".

## Not in scope

- RAG over medical documents — absent today, and none of the findings need it. Separate phase if the paper wants it.
- MCP — no external agent consumes these tools yet.
- Multi-process safety for R-03 — needs Redis or DB-level locking; out of proportion for this deployment.
- Rewriting git history to purge the leaked key — rotate it instead.
