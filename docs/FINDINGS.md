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

## F-10 · The deployed model configuration left the Orchestrator ~317 output tokens

**Observation.** Baseline run, 60/60 turns: the Orchestrator's output was the model's own reasoning narrative ("Here's a thinking process that leads to the desired output…"), cut off mid-sentence; the structured `SAFETY_STATUS` / `INTENT` block never appeared on 54 of 60 turns.

**Evidence** (`evals/results/baseline-colab/results.jsonl`, observability `llm_call` records):

| stage | prompt tokens (median) | completion tokens (median / max) | finish_reason |
|---|---|---|---|
| orchestrator | 3,779 | 317 / 343 | `MAX_TOKENS` on **60/60** calls |
| feature | 2,051 | 464 / 1,706 | `STOP` 98/98 |
| formatter | 2,547 | 955 / 1,571 | `MAX_TOKENS` 15/60 |

3,779 + 317 = 4,096. Ollama 0.34 serves every model with a **4,096-token context window** unless `OLLAMA_CONTEXT_LENGTH` (or a per-request `num_ctx`) says otherwise, regardless of the model's advertised 131k limit (`/api/show` → `gemma4.context_length: 131072`). The Orchestrator's system prompt fills 92 % of that window; the model's thinking consumes the remainder and generation stops. Nothing in the app checked `finish_reason`, so every truncated turn looked like a normal answer: the Feature Agent received a fragment of reasoning as its "plan", the Formatter still produced fluent Arabic (F-04), and routing accuracy was 13.6 % with `intent = unknown` on 90 % of turns.

**Implication.** The pipeline as deployed never executed its own design with this model on this server configuration. The audit's C-02/C-03 findings (routing by prose, strict parser) were real, but the dominant failure was one level below them: the model was never given room to answer. A code-only fix (Phase 4) cannot show its effect under this configuration, which is why the first post-fix run was stopped.

**Action.**
- Per-request `num_ctx` was tried first and **rejected**: `MODEL_NAME=ollama_chat/gemma4:e4b` + `MODEL_EXTRA_JSON={"num_ctx": 16384}` does forward the window, but on that route `gemma4` re-calls the same tool instead of answering from its result, so the ADK loop spins (`check_model.py --adk`: tool round trip FAIL). The window has to be set **server-side** so the OpenAI-compatible `/v1` route inherits it.
- Colab notebook: `OLLAMA_CONTEXT_LENGTH=16384` on the server so `/v1` clients get it too.
- Observability already records `finish_reason`; `metrics_report.py` and the eval summary now surface `MAX_TOKENS` counts per stage so this cannot hide again.
- Experiment design becomes 2×2: {baseline code, fixed code} × {4k context, 16k context}; B (fixed, 4k) was abandoned as uninformative.

**Outcome.** Confirmed by run A′: the baseline code, unchanged, with only `OLLAMA_CONTEXT_LENGTH=16384` on the server, goes from 13.6 % to 95.2 % routing accuracy and from 0 to 60 of 60 parseable Orchestrator outputs. Truncation is 0 % in both 16k runs. Full numbers in `docs/RESULTS.md` §4.

**Paper use.** Headline finding for the deployment section: prompt-size versus context-window is a silent, configuration-level failure mode that no prompt or code review catches; only per-call `finish_reason` telemetry exposed it.

---

## F-11 · The system tells an elder to call an ambulance without giving the number

**Observation.** In the post-fix run (C, `fixed-colab-16k`), every emergency case was classified correctly (6/6 EMERGENCY, 0 under-escalated) and the caregiver escalation started on 6 of 7 emergency turns, yet the Egyptian ambulance number **123** appears in only **1 of 7** emergency responses. The eval catches one instance of this, because only `emergency-happy-001` carries a `contains '123'` assertion.

**Evidence.** Per-turn scan of `final_response` over `evals/results/fixed-colab-16k/results.jsonl`, emergency category:

| run | emergency-labelled turns | responses containing "123" |
|---|---|---|
| A′ `baseline-colab-16k` | 9 | 4 |
| C `fixed-colab-16k` | 9 | 2 (both in `mt-escalation-001`) |

Typical failing text: the response opens with a red-alert banner, says to "call the ambulance or ask someone nearby for help", lists first-aid steps, and never prints a number. The Formatter prompt supplies `123` in its emergency template; the model paraphrases the instruction instead of copying the literal.

**Implication.** The most safety-critical piece of information in the product is the one the model is least reliable about, and it fails *in a way that reads as correct*: the answer is urgent, well-formatted, clinically sensible and useless to someone who does not know the number. Classification accuracy (100 % in run C) is not a measure of emergency handling. This is the strongest available argument in the paper for content-level assertions on top of routing/safety labels, and for taking safety-critical strings out of the generative path entirely.

**Root cause.** The Formatter's emergency template carried a *placeholder* rather than the number: `• اتصل بالإسعاف فوراً على [رقم الطوارئ]`. The model treated the bracketed text as an instruction to paraphrase, not a slot to fill. The number was present in `routing.py`'s `DEFAULT_EMERGENCY_MESSAGE`, one stage upstream, and the Formatter rewrote it away.

**Action.** Fixed in `d54e8d1`, in two layers:
- The template now carries the literal `123`.
- The number no longer depends on the model at all. `routing.ensure_emergency_number()` is idempotent, and `SenioCarePipeline` patches the Formatter's event in place on an EMERGENCY turn, both the text part the user is shown and the `final_response` state delta, so the stream, the session state and the eval harness cannot disagree.
- Every emergency case now asserts `must_contain: ["123"]`, not just `emergency-happy-001`, so the rate is measured on every run. Four unit tests cover omission, non-duplication, empty Formatter output and the synthesised bypass message.
- Still open: the same argument applies to medication names and doses in the Feature Agent's output, which are still model-reproduced. Not yet measured.
- Not yet re-run against the model: the fix is verified by unit tests; the next eval run will report the rate.

**Paper use.** Safety section, headline: a 100 % correct safety classifier still produced an emergency answer missing the emergency number on 6 of 7 turns. Label-level metrics and content-level metrics disagree, and only the second one matters to the user.

---

## F-12 · Tool precision inverted the ranking of the runs; the expected sets were minimums

**Observation.** Tool precision *falls* from 84.6 % in the broken run A to 45.2 % in the fixed run C, while recall rises from 78.6 % to 100 %. Taken at face value the metric says the truncated pipeline used tools better.

**Evidence.** `summary.json → tools` for the three runs: A `tp=22 fp=4 fn=6`, A′ `tp=24 fp=31 fn=2`, C `tp=28 fp=34 fn=0`. Inspection of the false positives shows they are the remaining steps of legitimate chains, for example a meal turn whose case file expects `get_meal_options` + `check_drug_food_interaction` + `get_meal_recipe` and which also calls `search_youtube`. In run A the Orchestrator's plan was a truncated fragment, so the Feature Agent attempted fewer tools and accumulated fewer "extra" calls.

**Implication.** The expected `tools` list in a case file is a *minimum* set ("all of these were called"); scoring calls outside it as false positives measures verbosity, not correctness, and it does so with a sign that is opposite to quality. A tool-use metric needs two lists: the required set (recall) and an allowed set (precision), with forbidden tools defined per safety status rather than per case.

**Action.** Recall and the forbidden-tool count (C-02, 0 in all three runs) are reported as accuracy figures; precision is reported only with this caveat attached. Adding an explicit `tools_allowed` field per case is open work.

**Paper use.** Methods / threats to validity: a worked example of an eval metric that ranks a broken system above a working one, and why the fix is in the assertion schema rather than in the model.

---

## F-13 · The harness aliased mutable session state, so multi-turn state assertions could not both pass

**Observation.** In run C, `mt-pref-conflict-001#t1` fails ("the dish should be in `food_likes` after turn 1") while `#t2` passes ("it should be gone after turn 2"). In run A′ exactly the opposite pair holds. The response texts show both products behaved as specified at turn 1.

**Evidence.** The runner captured `result.state_snapshot = {k: state.get(k) for k in SNAPSHOT_STATE_KEYS if k in state}`. ADK mutates nested state values (`user:preferences` is a dict) **in place** across the turns of a scenario, so both turn records referenced the same live object and serialised the end-of-scenario value when the file was written. The two turn records of that scenario are byte-identical in `state_snapshot`.

**Implication.** Any multi-turn assertion on a mutable state value was evaluated against the final state of the scenario, not the state at that turn. For a conflict scenario, where the point is that the value changes, the two assertions are then mutually unsatisfiable, and the run is guaranteed to report one false failure whichever way the product behaves. The class of bug is worth reporting: an eval harness that shares a mutable object with the system under test measures the system's last state, not its history.

**Action.** Fixed in `1f032bb`: the snapshot is deep-copied at capture time. The 16k runs predate the fix, so the one affected assertion in run C is annotated in `docs/RESULTS.md` §9 rather than counted as a product defect. Re-running the scenario tier will clear it.

**Paper use.** Methods: harness-validity threats deserve the same treatment as system defects, and this one was only detectable by reading two records that should have differed and did not.

---

## Open items being tracked

| Item | Status | Evidence |
|---|---|---|
| Does `gemma4:e4b` emit well-formed tool calls at all? | **Yes** (F-06) | `check_model.py --adk`, 5/5 |
| Orchestrator truncation (F-10) | **Closed** — 0 % in both 16k runs | `summary.json → truncation` |
| Intent-unparsed rate (C-03) | **Closed** — 90.0 % → 0 % at 16k, both code versions | RESULTS §2 |
| Turn-2 tool failure rate (C-04) | **Measured** — baseline hangs 2 of 6 scenarios at 16k; fixed code 0 | RESULTS §5 |
| False-emergency rate on single mild symptoms (C-12) | **Measured** — baseline over-escalates 1 follow-up; fixed code 0 over-refusals | RESULTS §6 |
| Arabic symptom recall (C-13) | **Measured** — 4/4 `symptom_assessment` turns pass at 16k in both code versions | RESULTS §8 |
| Emergency number in the answer | **Fixed** (F-11, `d54e8d1`), rate not yet re-measured | 1 of 7 turns in run C |
| Tool precision needs an allowed-set | **Open** (F-12) | RESULTS §9 |
| Per-turn state snapshots | **Fixed** (F-13), not yet re-run | commit `1f032bb` |
| Human-review tier (23 turns × 3 runs) | **Open** — not reviewed | `human_review.csv` |
| Judge tier (3 malformed cases) | **Open** — no judge model configured | `summary.json → judge` |
