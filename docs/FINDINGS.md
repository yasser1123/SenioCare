# SenioCare — Research Findings Log

A running log of every finding with evidence, produced while hardening the system on branch `feat/hardening`. Each entry is written so it can be lifted into the paper: what was observed, how it was measured, what it implies, and how it was (or will be) addressed. Findings from the static audit are in `docs/AUDIT.md` (C-01…C-16, R-01…R-06); this file records what was learned **by running things**.

Entry format: **Observation → Evidence → Implication → Action → Paper use.**

---

## F-01 · Database connections hung indefinitely; cause was DNS, not load

**Observation.** The test suite stalled at 0% CPU on two consecutive runs (2026-09-18), once inside `psycopg2.connect`, once inside `cursor.execute` on a connection that had answered `SELECT 1` a moment earlier.

**Evidence.** Neon's pooler hostname resolves to three IPs; from this network one of them (`3.227.221.118`) black-holes TCP. Twenty sequential connects with an 8 s timeout: 12 succeeded in ~1 s, 8 hit the timeout before libpq fell through to the next address (`docs/PLAN.md` 0.5). `psycopg2.connect` had no `connect_timeout` and synchronous psycopg2 has no query timeout at all, so either hang was unbounded. Every tool call opened a fresh TLS connection, so the whole suite paid the lottery ~100 times.

**Implication.** The production app was one DNS answer away from a request that never returns. Latency measurements taken before this fix would have been dominated by connection setup, not by the model.

**Action.** Pooled connections with `connect_timeout`, TCP keepalives and a client-side query deadline via psycopg2's wait callback (`seniocare/data/database.py`). Suite: 108 s with random hangs → 56 s deterministic; 81/81 green locally, 122/122 on CI with a local Postgres.

**Paper use.** Methods: infrastructure controls needed before latency can be attributed to the LLM stages. Also a cautionary data point on serverless Postgres from networks with partial connectivity.

---

## F-02 · Startup handlers never ran: no scheduler, no Firebase, no caregiver pushes

**Observation.** With observability wired into `@app.on_event("startup")`, the trace sink never started under the app.

**Evidence.** ADK's `get_fast_api_app()` installs its own lifespan. Starlette ignores `on_event` handlers whenever a lifespan is set. A probe handler registered the same way reported `{'startup': False, 'shutdown': False}` after a full `TestClient` lifecycle; `app.notifications._firebase_initialized` stayed `False`; the APScheduler instance was never created (FastAPI 0.123, Starlette current).

**Implication.** In every deployment of `main.py` to date:
- the daily / weekly / monthly report jobs (`app/scheduler.py`) never ran;
- Firebase Admin was never initialised, so `notify_caregivers()` took its "Firebase not initialized — skipping notifications" branch on every call;
- therefore **no emergency push has ever been delivered by the running app**, independent of the fire-and-forget defect in AUDIT C-09. The Flutter side would have seen silence.

**Action.** `main.py` now wraps ADK's lifespan and runs startup/shutdown inside it (commit `fix(app): C-17`). Regression check: the sink and scheduler are observable at `/health` and `/metrics/summary`.

**Paper use.** Results: the emergency escalation path had a 0 % delivery rate before hardening for a reason the static audit did not catch; only instrumentation exposed it. Supports the argument that observability must precede evaluation.

---

## F-03 · Prompt volume: ~10,000 prompt tokens per turn before the user says anything

**Observation.** One ordinary meal request ("عايز أكلة كويسة على الغدا") through the unmodified three-stage pipeline.

**Evidence** (local `qwen3:0.6b`, CPU, `llm_traces` rows for trace `e2e-3e0e769c`):

| stage | prompt tokens | completion tokens | latency |
|---|---|---|---|
| orchestrator | 3,752 | 372 | 22.3 s |
| feature | 4,095 | 507 | 18.7 s |
| formatter | 2,160 | 343 | 12.8 s |
| **turn** | **10,007** | **1,222** | **54.0 s** (LLM share 99.6 %) |

Token-priced cost at the reference model (`gemini/gemini-2.5-flash` list price): **$0.0061 per turn**, 89 % of it prompt tokens.

**Implication.** The three system prompts (orchestrator ≈ 300 lines, feature ≈ 300, formatter ≈ 230) dominate both cost and latency. Prompt caching or prompt compression would have more effect than any model swap. This is the baseline against which the Phase 4 prompt clean-ups (C-06 phantom tools, dead fields) can be measured.

**Action.** Recorded per stage on every turn; `scripts/metrics_report.py` reports it.

**Paper use.** Cost model section; motivates the "prompt share of cost" metric.

---

## F-04 · Small models fail the pipeline silently in different ways, and the harness must catch each

**Observation.** Verifying the plumbing with small local models before the GPU model was available.

**Evidence.**
- `qwen2.5:0.5b` (both `ollama_chat/` and the OpenAI-compatible `/v1` route): answers fluently, never emits a `tool_calls` array → `scripts/check_model.py` FAIL on the tool-call check.
- `qwen3:0.6b`: passes all five `check_model.py` checks, including ADK's real tool loop, **but** in the full pipeline the Feature Agent returned an **empty** completion (its 4,095-token prompt plus reasoning consumed the budget) → `stage` record `empty_output=true`, `parse_ok=false`; the Formatter then produced 489 chars of fluent Arabic **from nothing** and the turn looked normal to a user.
- Thinking models spend the completion budget on hidden reasoning; the first version of the check reported a bare "empty response" and had to be made reasoning-aware.

**Implication.** "Model responds" is not evidence of a working pipeline. A stage can produce nothing and the next stage will confabulate a plausible answer. The `empty_output` / `parse_ok` stage metrics are the only place this is visible.

**Action.** Both metrics are emitted per stage; the eval harness (Phase 3) treats an empty or unparseable Feature output as a failed structural assertion regardless of how good the final Arabic looks.

**Paper use.** Motivates stage-level assertions over end-to-end judgement; concrete example of silent failure propagation in sequential agent chains.

---

## F-05 · Where a model runs is orthogonal to tools (verified, not assumed)

**Observation.** The same backend, unchanged, drove tools through local Ollama (`ollama_chat/`), through Ollama's OpenAI-compatible `/v1` (the route a Colab tunnel uses, with a placeholder API key), and through ADK's `Runner` tool loop.

**Evidence.** `scripts/check_model.py --adk` → 5/5 PASS with `qwen3:0.6b` on both routes; tool executed in-process with `meal_type='lunch'` from a model-emitted call.

**Implication.** Inference location is a deployment variable (`MODEL_API_BASE`), not an architecture change. Supports the Colab-GPU experimental setup without threatening validity of tool-related measurements.

**Paper use.** Experimental setup section.

---

## F-06 · gemma4:e4b does emit tool calls; the notebook's own gate produced a false negative

**Observation.** Two gates ran against the same Colab T4 Ollama serving `gemma4:e4b` through the OpenAI-compatible `/v1` endpoint and a cloudflared quick tunnel.

**Evidence.**
- `scripts/check_model.py --adk` from the backend (LiteLLM `openai/gemma4:e4b`, `MODEL_API_BASE=https://…trycloudflare.com/v1`): **5/5 PASS** — reachability 0.7 s, completion 4.5 s (46/22 tokens), tool call 2.1 s → `get_meal_options({'meal_type': 'lunch'})`, tool-result round trip 4.8 s, ADK Runner tool loop 3.8 s with the tool executed in-process.
- The notebook's in-Colab gate reported **FAIL**, but only on test 1: "plain chat: 67.88 s, 256 completion tokens → ''". The first request after load spent its entire 256-token budget on hidden reasoning and returned empty content (same failure mode as F-04); tests 2 and 3 (tool call, round trip) passed at 2.3 s and 2.0 s.

**Implication.** (1) The model is suitable for the Feature Agent; the open question in F-04's table is closed. (2) Latency per call on a T4 is 2–5 s versus 12–22 s for a 0.6B model on the local CPU, so the three-stage pipeline should land around 10–20 s per turn. (3) Any gate for a reasoning model must budget for hidden reasoning tokens or it will reject working models.

**Action.** `.env` points at the tunnel; `check_model.py` is the authoritative gate (reasoning-aware since Phase 1); the notebook's test 1 gets the same treatment. Baseline eval run launched against this endpoint on commit `eval-baseline`.

**Paper use.** Experimental setup (model, hardware, transport) and a methods note on evaluating thinking models.

---

## F-07 · Startup crashed on a Windows console because of an emoji

**Observation.** With the lifespan fix (F-02) in place, booting the app from a plain Windows console (cp1252) aborted during startup.

**Evidence.** `app/scheduler.py` printed `"[Scheduler] ✅ Report scheduler started"`; `print` raised `UnicodeEncodeError: 'charmap' codec can't encode character '✅'` inside the lifespan, so the app never reached "Application startup complete". Under a UTF-8 console (`PYTHONIOENCODING=utf-8`) the same code worked, which is why the earlier uvicorn check passed.

**Implication.** A logging cosmetic can be a startup failure; this only became reachable once the startup handlers actually ran (F-02).

**Action.** `main.py` reconfigures stdout/stderr to UTF-8 with replacement; the scheduler message is plain ASCII.

**Paper use.** Minor; an example of latent defects exposed by fixing an upstream one.

---

## F-08 · Baseline eval, first attempt: every turn's safety status was unreadable to the app

**Observation.** First 22 turns of the baseline run (unfixed pipeline, `gemma4:e4b` on Colab T4) before the run stalled on turn 23.

**Evidence** (`evals/results` not written because the run had to be killed; the per-turn log survived):
- 22/22 turns took 51–78 s end to end (≈65 s median), three LLM calls each.
- The production parser (`INTENT:\s*(\w+)`, `SAFETY_STATUS:\s*(\w+)`) returned **unknown for both fields on 20 of 22 turns**; the tolerant parser recovers them. gemma4 formats the fields with markdown bold (`**INTENT:** meal`), exactly the drift AUDIT C-03 predicted. On the unfixed pipeline this means the emergency trigger could never fire and the Feature Agent ran on every request.
- Turn 23 never returned: the event loop sat idle in `select()` for 55 minutes; no timeout in the harness, in the model client path taken, or in the tools bounded it. The harness now has a per-turn timeout (default 420 s) and a 60 s heartbeat, and the baseline was re-run from a git worktree at tag `eval-baseline` so the measured code stayed unfixed while fixes continued on the branch.

**Implication.** The two most consequential findings of the audit (C-02/C-03) are not hypothetical with this model: on the deployed prompt format the app could not read its own safety classification.

**Action.** Full baseline re-run in progress; numbers go to `docs/RESULTS.md`. Fixes for C-02/C-03 (`seniocare/routing.py`, `seniocare/pipeline.py`) already committed on the branch.

**Paper use.** Core result: prose-level safety routing measured against code-level routing on the same 60 turns.

---

## F-09 · A fresh install of requirements.txt could not start the app

**Observation.** CI (fresh Ubuntu, `pip install -r requirements.txt`) failed the C-16 route test with `ModuleNotFoundError: No module named 'sqlalchemy'` … `pip install google-adk[db]`.

**Evidence.** `requirements.txt` listed `google-adk>=0.1.0` without the `[db]` extra; `DatabaseSessionService` (used by every deployment of this app) needs SQLAlchemy. Locally it worked only because another package had installed SQLAlchemy. Earlier in the branch `apscheduler` (listed) and the pytest plugins (configured) were likewise missing from the working environment.

**Implication.** The declared dependencies never described a runnable environment; "works on my machine" masked it until CI existed.

**Action.** `google-adk[db]>=1.22.0,<2`; CI runs the full suite on every push.

**Paper use.** Engineering-practice note: CI as a correctness instrument, not just a test runner.

---

## Open items being tracked

| Item | Status | Where it will be answered |
|---|---|---|
| Does `gemma4:e4b` emit well-formed tool calls at all? | **Yes** (F-06) | `check_model.py --adk`, 5/5 |
| Turn-2 tool failure rate (AUDIT C-04) | To be measured | multi-turn eval, baseline run |
| False-emergency rate on single mild symptoms (C-12) | To be measured | baseline run, `symptom_*` cases |
| Arabic symptom recall (C-13) | To be measured | baseline run |
| Intent-unparsed rate (C-03) | Measured per turn | `metrics_report.py`: *intent unparsed* |
