# SenioCare — Experiment Protocol

What was run, on what, with which commands, so the numbers in `docs/RESULTS.md` can be reproduced. Written for the paper's Method section.

## 0. Design: 2 × 2 (code × context window)

The first baseline run exposed a configuration variable that dominates everything else: Ollama's default 4,096-token context (`docs/FINDINGS.md` F-10). The experiment is therefore a 2 × 2:

| | 4k context (Ollama default) | 16k context (`OLLAMA_CONTEXT_LENGTH=16384`) |
|---|---|---|
| **Baseline code** (tag `eval-baseline`) | **Run A** `baseline-colab` — done | **Run A′** `baseline-colab-16k` |
| **Fixed code** (`feat/hardening`) | Run B — abandoned as uninformative (the Orchestrator cannot emit its output block in ~317 tokens, so no code change can show) | **Run C** `fixed-colab-16k` |

A vs A′ isolates the deployment configuration; A′ vs C isolates the code changes; A vs C is "as deployed" vs "as hardened". Same 60 turns, same model, same tunnel host, same harness in all runs.

## 1. System under test

| | Baseline | Post-fix |
|---|---|---|
| Git ref | tag `eval-baseline` (`9b98035`) | branch `feat/hardening` head at the time of the run (see `evals/results/<run>/config.json` → `git_commit`) |
| Pipeline | `SequentialAgent`: Orchestrator → Feature → Formatter, unconditionally | `SenioCarePipeline`: Orchestrator → `route()` → Feature (ALLOWED only) → Formatter |
| Safety parsing | strict regex `INTENT:\s*(\w+)`; `SAFETY_STATUS` unread | tolerant parser (bold, case, full-width colon); either signal escalates |
| Tool guards | session-lifetime flags (C-04) | per-turn (turn-number) guards |
| Symptom matching | English substring | word-level, Arabic synonyms, evidence-based escalation |
| Drug / allergen joins | exact string | normalised names, word-level |
| Prompts | phantom tools, missing templates | cleaned |
| Everything else | identical: same tools data (Neon Postgres seeds), same profiles, same model, same endpoint, same harness code (the harness file was copied into the baseline worktree unchanged in behaviour: only the per-turn timeout and heartbeat were added after the first attempt stalled) |

The eval harness is not the system under test; both runs used the same `evals/runner.py`.

## 2. Model and hardware

| | |
|---|---|
| Model | `gemma4:e4b` as packaged by Ollama (quantised GGUF), served by Ollama on **Google Colab, Tesla T4 (15 GB)** |
| Transport | Ollama's OpenAI-compatible `/v1/chat/completions` through a cloudflared quick tunnel; the backend used LiteLLM `openai/gemma4:e4b` with `MODEL_API_BASE=https://<tunnel>/v1` |
| Context window | Run A: Ollama default 4,096 tokens (`/api/ps` → `context_length: 4096`). Runs A′/C: server started with `OLLAMA_CONTEXT_LENGTH=16384` (`/api/ps` → 16384, verified after a plain `/v1` request). The `ollama_chat/` route with a per-request `num_ctx` was tried and rejected: gemma4 re-called tools instead of using their results through LiteLLM's Ollama message translation, and ADK's tool loop then spun. |
| Sampling | provider defaults (no temperature / max_tokens set in either run) |
| Timeout | 120 s per model call (`MODEL_TIMEOUT_S`), 420 s per turn in the harness |
| Backend host | Windows 10 laptop running the FastAPI/ADK process in-process (harness mode `adk`), Postgres on Neon (us-east-1) |
| Gate | `python scripts/check_model.py --adk` passed 5/5 against this endpoint before the runs (`docs/FINDINGS.md` F-06) |
| Libraries | google-adk 1.22.0, litellm 1.80.13, fastapi 0.123.10 / starlette 0.50.0, uvicorn 0.40.0, Python 3.12.10 (pinned by minor in `requirements.txt`) |

Latency numbers therefore include: tunnel round trip (Egypt → Cloudflare → Colab), T4 prefill of ~3–4k-token system prompts per stage, generation, and Neon round trips (~150–200 ms each) for tool calls. They are comparable *between* the two runs, not with a production deployment.

## 3. Cases

`evals/cases/*.jsonl`: 54 cases, 60 turns (48 single-turn + 6 two-turn scenarios). Categories and counts in `evals/schema.md` §5 and §8. Profiles in `evals/profiles.json`. Cases were written from the code's own taxonomy (`orchestrator_agent.py` intents and safety triggers), before either run, and were not changed between runs.

Assertion tiers: `structural` (28 + scenarios), `human` (20; structural checks still run, verdict pending), `keyword`/`language` where declared. No LLM judge was configured for the runs reported here (`JUDGE_MODEL` unset), so judge scores are absent rather than partial.

## 4. Commands

```bash
# Baseline (unfixed code) — from a worktree at the tag, same venv, same .env
git worktree add ../SenioCare-baseline eval-baseline
cp .env ../SenioCare-baseline/.env && cp evals/runner.py ../SenioCare-baseline/evals/runner.py
cd ../SenioCare-baseline && python evals/runner.py --name baseline-colab

# Post-fix — on the branch (server restarted with OLLAMA_CONTEXT_LENGTH=16384 first)
python scripts/check_model.py --adk          # gate, after every Colab restart
python evals/runner.py --name fixed-colab-16k

# Baseline code, 16k context (A′) — from the worktree
cd ../SenioCare-baseline && python evals/runner.py --name baseline-colab-16k

# Comparison table
python evals/compare.py baseline-colab fixed-colab-16k --out docs/results_compare.md
python evals/compare.py baseline-colab baseline-colab-16k     # context effect alone
python evals/compare.py baseline-colab-16k fixed-colab-16k    # code effect alone

# Per-stage latency/token/cost tables for a run window (from llm_traces, when the
# app or the harness wrote to Postgres) — the harness also stores per-turn metrics
# in results.jsonl, which summary.md aggregates
python scripts/metrics_report.py --since <run start ISO> --until <run end ISO>
```

## 5. What each metric means

| Metric | Definition | Source |
|---|---|---|
| Routing accuracy | `parsed.intent == expect.intent` over cases that declare an intent, with the **production** parser; the tolerant-parser figure is reported next to it | `summary.json → routing` |
| Intent unparsed rate | share of completed turns where the production parser returned `unknown` (AUDIT C-03) | `rates.intent_unknown` |
| Safety accuracy / confusion matrix | expected vs parsed `SAFETY_STATUS` (ALLOWED / BLOCKED / EMERGENCY / unknown) over cases that declare it; *under-escalated* = expected EMERGENCY parsed as anything else; *over-refused* = expected ALLOWED parsed BLOCKED or EMERGENCY | `safety` |
| Forbidden-tool calls | turns where a tool in `expect.tools_not_called` was called (emergency/blocked cases) — the C-02 measurement | `tools.forbidden_calls` |
| Turn≥2 guard-hit rate | scenario turns after the first in which any tool returned `already_called` — the C-04 measurement, from the observability tool records | `tools.turn2plus_guard_hit_rate` |
| Tool precision / recall | expected vs called tools over cases declaring `tools_called` | `tools.precision`, `tools.recall` |
| Empty Feature output on ALLOWED | silent-failure count (F-04) | `rates.empty_feature_when_allowed` |
| e2e latency p50/p95, stage p50 | wall time per turn / per stage (observability `llm_call` records) | `latency` |
| Tokens / cost per turn | prompt + completion tokens from the provider's usage; cost at the reference model's list price (`COST_REFERENCE_MODEL`, default `gemini/gemini-2.5-flash`) so the two runs are comparable regardless of where inference ran | `tokens`, `cost` |

## 6. Threats to validity (state them in the paper)

- **Single model, single hardware.** Results characterise `gemma4:e4b` on a T4; a stronger model could mask some prompt-parsing failures.
- **Author-written cases.** The 60 turns were written by the same people who audited the code; they are designed to probe known defects, so absolute pass rates overstate difficulty for defect categories and understate it for unseen inputs.
- **Non-determinism.** No seed control is available through Ollama's OpenAI endpoint; each run is one sample. Re-running gives different per-case outcomes; aggregate rates are the intended reading.
- **Human tier not yet judged.** 20 cases (emergency adequacy, clinical appropriateness, dialect) are pending human review in `human_review.csv`; structural results for them are reported, verdicts are not.
- **Network.** Latency includes a tunnel and a serverless database in another region.
