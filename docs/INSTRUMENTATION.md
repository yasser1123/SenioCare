# SenioCare — Instrumentation Plan

**Status: design only. Nothing in this document has been implemented.**

**Purpose:** define what to measure so that any change to the pipeline can be compared before/after with evidence rather than impression. Today no such comparison is possible — there is no timing, no token accounting, no per-stage attribution, and no configured logger (see `docs/AUDIT.md`, Phase 1 → Observability).

**Constraint honoured:** no new dependencies are assumed. Options requiring a new package are marked **[NEW DEP]** and presented as alternatives, not defaults.

---

## 0. The baseline problem

Before choosing metrics, note what makes measurement hard here:

1. **Three LLM calls per turn share one request.** Wall-clock latency at the HTTP layer tells you nothing about which stage is slow. Attribution requires per-stage boundaries.
2. **The two existing loggers never emit.** `app/notifications.py:15` and `app/scheduler.py:20` create loggers, but no `logging.basicConfig()` exists anywhere in the repo. Root level defaults to `WARNING`, so every `logger.info(...)` call in those modules is silently discarded today. Any logging-based instrumentation must first configure the root logger — otherwise it will appear to work while emitting nothing.
3. **`print()` is the de-facto log.** 23 calls. They go to stdout unstructured, interleaved with ADK's own output, with no timestamp, no correlation ID, and no level.
4. **Cost is not simply money.** The models run locally via Ollama (`seniocare/sub_agents/orchestrator_agent.py:315`), so token cost is compute and latency, not billing. SerpAPI (`seniocare/tools/web_search.py:159`) *is* billed per call and is currently uncapped and uncached — that is the real currency cost in this system.

---

## 1. Per-stage metrics

### What to measure

| Metric | Definition | Why it matters here |
|---|---|---|
| `stage.latency_ms` | Wall time from stage entry to `output_key` write | The only way to know which of the three stages dominates |
| `stage.input_tokens` | Prompt tokens sent | System prompts are ~200-300 lines each; this is likely the dominant cost |
| `stage.output_tokens` | Completion tokens | Feature Agent is told never to summarise (`feature_agent.py:299-300`) — expect a long tail |
| `stage.failure_rate` | Exceptions or empty output / total invocations | Currently unobservable |
| `stage.parse_success` | Did the expected field appear in output? | Directly measures **C-03** and **C-10** |
| `stage.output_chars` | Raw length | Zero-cost proxy for output_tokens if token counts prove unavailable |

### Where the instrumentation points go

The stages are ADK `LlmAgent` instances, not functions you call directly, so you cannot wrap them with a decorator. Three viable attachment points:

**Point A — ADK agent callbacks (recommended attachment, no new deps)**

ADK's `LlmAgent` accepts `before_agent_callback` and `after_agent_callback`, already used at the root level (`seniocare/agent.py:38-39`). Attach a timing pair to each of the three sub-agents:

- `seniocare/sub_agents/orchestrator_agent.py:313` — add callbacks to the constructor
- `seniocare/sub_agents/feature_agent.py:307` — same
- `seniocare/sub_agents/formatter_agent.py:229` — same

The `before` callback stamps `time.perf_counter()` into `callback_context.state` under a `temp:`-prefixed key (important — see **C-04** for what happens when you forget the prefix). The `after` callback computes the delta and emits one structured record.

*Cost:* touches all three agent files. Callback signature is ADK-version-coupled — `callback_context._invocation_context` is already relied on at `callbacks.py:114` and `:187`, and that is a private attribute; this approach inherits that fragility.

**Point B — `before_model_callback` / `after_model_callback`**

ADK also exposes model-level callbacks, which receive the actual `LlmRequest` / `LlmResponse`. This is the **only** place token counts are available — `LlmResponse.usage_metadata` carries `prompt_token_count` and `candidates_token_count`.

*Cost:* more version-coupled than Point A. If you only need latency, Point A is sufficient and more stable. If you need tokens, you need Point B.

**Point C — HTTP middleware**

A FastAPI `@app.middleware("http")` at `main.py:44` (after app construction, before routers at `:50`) gives end-to-end latency and a correlation ID for free, with zero coupling to ADK internals.

*Cost:* cannot see inside the pipeline. Gives you total latency but no attribution — which is exactly the question you most need answered. Use it as the outer frame, not the whole plan.

### Cheapest correct implementation

A single module, `app/observability.py` (new file), containing:

1. `configure_logging()` — one `logging.basicConfig()` call with a JSON-ish formatter, invoked once from `main.py:38` before app construction. **This is the prerequisite for everything else** and fixes the silently-dead loggers noted above.
2. `stage_timer(stage_name)` — a callback-pair factory returning `(before_fn, after_fn)` suitable for ADK's callback slots.
3. `emit(record: dict)` — one function that writes a single-line JSON record via `logger.info`. Everything else calls only this.

Keeping `emit` as the single sink matters: swapping stdout-JSON for OpenTelemetry later becomes a one-function change rather than a repo-wide edit.

**Record shape:**
```json
{"ts":"...","trace_id":"...","user_id_hash":"...","stage":"orchestrator",
 "latency_ms":8421,"input_tokens":3102,"output_tokens":412,
 "parse_ok":true,"intent":"meal","error":null}
```

Hash `user_id` rather than logging it raw — this is health data (see `docs/AUDIT.md` C-01). A truncated SHA-256 is enough to correlate a session without storing an identifier.

---

## 2. Pipeline metrics

| Metric | Definition | Instrumentation point | Notes |
|---|---|---|---|
| `pipeline.e2e_latency_ms` | Request in → response out | HTTP middleware at `main.py:44` | The number a user actually feels |
| `pipeline.stage_sum_vs_e2e` | Σ stage latency ÷ e2e | Derived | Gap = ADK overhead + DB + tool time. If the gap is large, the problem is not the model |
| `pipeline.routing_accuracy` | Extracted intent == expected intent | `seniocare/callbacks.py:208`, where `_extract_intent` already runs | Requires labelled cases — see `evals/` |
| `pipeline.intent_unknown_rate` | Share of turns where `_extract_intent` returns `"unknown"` | `seniocare/callbacks.py:212` | **Measure this first.** It directly quantifies **C-03**, needs no labelled data, and is a one-line addition |
| `pipeline.refusal_rate` | Share classified `blocked` | Same regex site | Watch both directions: over-refusal makes the app useless, under-refusal is a safety failure |
| `pipeline.emergency_rate` | Share classified `emergency` | `seniocare/callbacks.py:184` | Given **C-12**, expect a false-positive rate high enough to be visible immediately |
| `pipeline.escalation_success` | Emergency detected → FCM actually sent | `seniocare/callbacks.py:262` (report generated) and `:277` (notify result) | The life-safety path in **C-09** currently has no success signal at all |

### On `intent_unknown_rate` specifically

This is the highest-value single metric in the whole plan and the cheapest to add. `_extract_intent` (`seniocare/callbacks.py:206-212`) already computes the value; today the `"unknown"` branch returns silently. Adding one `emit()` call in that branch tells you what fraction of all traffic is falling through the safety-classification contract — the thing **C-03** says is unobservable. One line, no dependencies, no labelled data required.

### Tool-level metrics (not in the brief, but they will dominate your latency)

Given **R-01** and **R-02**, per-tool timing is worth the same treatment. ADK offers `before_tool_callback` / `after_tool_callback`. Two metrics matter most:

- `tool.latency_ms` by tool name — will immediately expose the 100-query nested loop at `interactions.py:63-68`
- `tool.already_called_rate` — counts how often a tool returns the `"already_called"` short-circuit (`nutrition.py:25`, `interactions.py:23`, `symptoms.py:26`, `image_tools.py:44`). **This is the direct measurement of C-04.** If it is non-zero outside turn 1, the guard bug is confirmed in production traffic.

### SerpAPI cost

`seniocare/tools/web_search.py:159` is the only metered external call. Add a counter at that line. The Orchestrator mandates YouTube search for every meal and every exercise intent (`orchestrator_agent.py:206`, `feature_agent.py:288-290`), so search volume scales linearly with those intents with no cache in between. A simple call counter, grouped by `engine`, tells you the monthly bill before it arrives.

---

## 3. Retrieval metrics

**Not applicable.** There is no retrieval system — no vector store, no embeddings, no chunking, no reranking (`docs/AUDIT.md`, Phase 1 → Retrieval: ABSENT).

The nearest analogues, if you want the same *shape* of signal from what exists:

| Analogue | Definition | Point |
|---|---|---|
| `meal_filter.yield` | Meals surviving condition + allergen filtering ÷ total for that meal_type | `seniocare/tools/nutrition.py:111` |
| `meal_filter.empty_rate` | Share of calls returning zero options | `nutrition.py:111` — with only 19 seed meals, over-filtering to zero is plausible and currently invisible |
| `symptom_match.count` | Diseases matched per call | `seniocare/tools/symptoms.py:139` — directly quantifies the over-matching in **C-12** |
| `interaction.hit_rate` | Pairs with a DB hit ÷ pairs checked | `seniocare/tools/interactions.py:105` — a near-zero rate would corroborate **C-14** |

`symptom_match.count` deserves emphasis: if the mean is high (say >5 of 15 diseases per query), that is quantitative proof of substring over-matching, obtainable without any labelled data.

---

## 4. Tracing approach — options and their costs

The brief asks for trade-offs rather than a pick. Four options, ordered by adoption cost.

### Option 1 — Structured JSON to stdout

One log line per stage/tool/request, correlated by a `trace_id` generated in HTTP middleware.

- **Adds:** nothing. `logging` and `json` are stdlib.
- **Costs:** no waterfall view — you reconstruct traces by grepping and sorting. No sampling control; either you log everything or you edit code. Analysis means writing ad-hoc scripts. Correlating across the `asyncio.create_task` boundary at `callbacks.py:236` requires manually threading `trace_id` into the task, or it is lost.
- **Fits when:** you want a before/after number this week and will read the data yourself.
- **Honest assessment:** for a project with no instrumentation at all, this captures most of the available value. The gap between "nothing" and "structured stdout" is far larger than the gap between "structured stdout" and a full tracing backend.

### Option 2 — OpenTelemetry SDK **[NEW DEP]**

Spans for request → stage → tool, exported to any OTLP backend.

- **Adds:** `opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi`, an exporter. Non-trivial dependency weight.
- **Costs:** a collector or backend to run (Jaeger, Tempo, Honeycomb) — real operational surface for a project with no Docker setup yet. Async context propagation across `asyncio.create_task` needs care. Roughly a day to get right.
- **Buys:** proper waterfalls, sampling, and vendor portability. It is also the answer most backend interviewers expect to hear, which matters given your stated goal.
- **Note:** ADK 1.22.0 has its own internal tracing; check for a built-in OTel hook before instrumenting manually, or you will produce duplicate spans. **[SPECULATION]** — I did not verify what ADK 1.22.0 exports natively.

### Option 3 — LLM-specific observability platform **[NEW DEP]**

Langfuse, LangSmith, Phoenix, or similar.

- **Adds:** one SDK plus an account (or a self-hosted service).
- **Costs:** vendor coupling; health data leaves your infrastructure unless self-hosted — a genuine problem for PHI. Most integrate best with LangChain/LlamaIndex; ADK support ranges from thin to absent, so expect manual span creation anyway.
- **Buys:** prompt/response capture, diffing, eval integration, and a UI built for exactly this three-stage-chain debugging problem.
- **The blocker for this project:** sending Egyptian elderly patients' medications and diagnoses to a third-party SaaS is a decision to make deliberately, not by adding a dependency. Self-hosted Langfuse avoids it at the cost of running another service.

### Option 4 — Database table

Write records to a `pipeline_traces` table in the Neon DB you already have.

- **Adds:** nothing. `psycopg2` is present.
- **Costs:** you are writing to the same connection-starved database that **R-01** identifies as a bottleneck, on the request path, synchronously. That is self-defeating unless writes are batched or async. Also no UI — you write SQL to analyse.
- **Buys:** durable, queryable history with zero new infrastructure, and joinable against `health_reports` for questions like "do concerning reports correlate with slow stages?"
- **Reasonable variant:** stdout for hot-path stage traces, DB only for eval-run results (which are offline and low-volume).

### Trade-off summary

| | Setup cost | New deps | Ops burden | PHI exposure | Waterfall UI |
|---|---|---|---|---|---|
| 1. Structured stdout | Hours | None | None | None | No |
| 2. OpenTelemetry | ~1 day | 3+ | Collector | Configurable | Yes |
| 3. LLM platform | Hours | 1 | Account or self-host | **High unless self-hosted** | Yes, purpose-built |
| 4. Database table | Hours | None | None | None | No |

The decision is yours. The one thing I would flag: options 1 and 4 are not mutually exclusive with 2 — if `emit()` is the single sink (§1), starting with stdout and moving to OTel later is a one-function change. Starting with option 3 is the hardest to reverse, because prompt-capture semantics differ per vendor.

---

## 5. Suggested sequencing

Not a recommendation about *what to fix* — only about the order in which measurement becomes possible.

| Step | Action | Unblocks |
|---|---|---|
| 1 | `logging.basicConfig()` in a new `app/observability.py`, called from `main.py:38` | Everything. Without it the existing loggers stay silent |
| 2 | `trace_id` in HTTP middleware at `main.py:44` | Correlation across all later records |
| 3 | `emit()` in the `"unknown"` branch of `_extract_intent` (`callbacks.py:212`) | Quantifies **C-03** with one line, no labelled data |
| 4 | `already_called_rate` counter in the 5 guard branches | Confirms or refutes **C-04** from real traffic |
| 5 | Stage timers via ADK agent callbacks | Per-stage latency attribution |
| 6 | Token counts via `before_model_callback` / `after_model_callback` | Cost modelling |
| 7 | Tool timers via tool callbacks | Confirms **R-01** / **R-02** magnitude |
| 8 | SerpAPI call counter at `web_search.py:159` | Actual currency cost |

Steps 3 and 4 are each roughly one line and each convert a static finding in `docs/AUDIT.md` into a measured production number. They are worth doing before any refactor, because they establish the before-baseline that makes an after-comparison meaningful.

---

## 6. What this plan cannot tell you

Stated plainly, so the plan is not oversold:

- **Answer quality is not measured by any of this.** Latency and token counts say nothing about whether the meal recommendation was safe. That requires the eval harness in `evals/`, and — per Phase 4 — several categories need human review regardless.
- **Routing accuracy needs labels.** `intent_unknown_rate` is free; `routing_accuracy` requires a labelled dataset that does not yet exist.
- **The emergency path resists measurement.** You can count how often escalation *fired*; measuring how often it *should have* requires ground-truth labels on real conversations you do not have and should not collect casually given the PHI involved.
- **Single-user timings will mislead you.** Because of **R-01**, latency under one user and latency under ten will differ by more than a constant factor. Any before/after comparison should hold concurrency fixed and state it.
