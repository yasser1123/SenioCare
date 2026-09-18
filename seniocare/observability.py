"""
Observability core: one record sink, ADK callbacks, cost estimation.
====================================================================

Everything measurable in the pipeline goes through ``emit(kind, **fields)``,
which writes a JSON line to the ``seniocare.obs`` logger and hands the record
to every registered sink (the Postgres writer, the eval harness's in-memory
capture, …). Swapping the destination later is a one-function change.

Record kinds
------------
llm_call         one model invocation (stage, latency, tokens, cost, finish)
tool_call        one tool invocation (tool, latency, status, already_called)
stage            one agent stage (latency, output size, parse success)
turn             one end-to-end pipeline run (intent, safety, totals)
serpapi_call     one metered web search
emergency_notify result of the emergency report + caregiver push
http_request     one HTTP request (from the FastAPI middleware)

Attachment points (docs/INSTRUMENTATION.md §1):
  Point A  before/after_agent_callback   -> stage records
  Point B  before/after_model_callback   -> llm_call records (the only place
                                            token counts exist)
  Point C  HTTP middleware               -> http_request records, trace_id
  plus     before/after_tool_callback    -> tool_call records

State keys used are all ``temp:`` prefixed, so ADK discards them at the end of
each invocation (see docs/AUDIT.md C-04 for what happens when you forget).

Cost views (all USD, see docs/PLAN.md 2.5):
  cost_token_priced  what these tokens would cost at COST_REFERENCE_MODEL
                     (litellm's public price table) — comparable across runs
                     regardless of where inference actually ran
  cost_actual        litellm's price for the *configured* model, when it is a
                     hosted model with a known price; None for self-hosted
  cost_compute       MODEL_GPU_USD_PER_HOUR × wall time — the self-hosted view
  serpapi            SERPAPI_USD_PER_SEARCH × calls
"""

from __future__ import annotations

import contextvars
import hashlib
import json
import logging
import os
import queue
import re
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger("seniocare.obs")

# =============================================================================
# Configuration
# =============================================================================

COST_REFERENCE_MODEL = os.environ.get("COST_REFERENCE_MODEL", "gemini/gemini-2.5-flash")
MODEL_GPU_USD_PER_HOUR = float(os.environ.get("MODEL_GPU_USD_PER_HOUR", "0") or 0)
SERPAPI_USD_PER_SEARCH = float(os.environ.get("SERPAPI_USD_PER_SEARCH", "0.015") or 0)
OBS_DB_ENABLED = os.environ.get("OBS_DB_ENABLED", "1").strip().lower() not in ("0", "false", "no", "")
OBS_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

# Stage name -> the state key the stage writes (LlmAgent.output_key)
STAGE_OUTPUT_KEYS = {
    "orchestrator_agent": "orchestrator_result",
    "feature_agent": "feature_result",
    "formatter_agent": "final_response",
    "report_agent": "report_result",
}

# =============================================================================
# Trace context
# =============================================================================

_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("seniocare_trace_id", default=None)


def new_trace_id() -> str:
    return uuid.uuid4().hex[:16]


def set_trace_id(trace_id: str | None) -> contextvars.Token:
    return _trace_id.set(trace_id)


def reset_trace_id(token: contextvars.Token) -> None:
    _trace_id.reset(token)


def current_trace_id() -> str | None:
    return _trace_id.get()


def hash_user_id(user_id: str | None) -> str | None:
    """Truncated SHA-256 so records correlate per user without storing the id (health data)."""
    if not user_id:
        return None
    return hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()[:12]


# =============================================================================
# Logging
# =============================================================================


class JsonFormatter(logging.Formatter):
    """One JSON object per line. Records that already carry a dict payload are merged."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
        }
        obs = getattr(record, "obs", None)
        if isinstance(obs, dict):
            payload.update(obs)
        else:
            payload["msg"] = record.getMessage()
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


_logging_configured = False


def configure_logging(level: str | None = None, stream=None) -> None:
    """Install a JSON formatter on the root logger. Idempotent.

    This is the prerequisite for everything else: until it runs, the loggers
    that already exist in app/notifications.py and app/scheduler.py emit
    nothing at all (docs/AUDIT.md, boilerplate table).
    """
    global _logging_configured
    if _logging_configured:
        return
    # litellm's response objects trip pydantic serialisation warnings inside ADK on
    # every call; they are noise, not signal, and would swamp the record stream.
    import warnings

    warnings.filterwarnings("ignore", message=".*PydanticSerializationUnexpectedValue.*")
    warnings.filterwarnings("ignore", message=".*EXPERIMENTAL.*")
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel((level or OBS_LOG_LEVEL).upper())
    # Third-party chatter stays out of the record stream.
    for noisy in ("httpx", "httpcore", "LiteLLM", "litellm", "apscheduler", "urllib3", "google_genai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _logging_configured = True


# =============================================================================
# Sinks and emit()
# =============================================================================

Sink = Callable[[dict[str, Any]], None]
_sinks: list[Sink] = []
_sinks_lock = threading.Lock()


def add_sink(sink: Sink) -> None:
    with _sinks_lock:
        if sink not in _sinks:
            _sinks.append(sink)


def remove_sink(sink: Sink) -> None:
    with _sinks_lock:
        if sink in _sinks:
            _sinks.remove(sink)


def emit(kind: str, **fields: Any) -> dict[str, Any]:
    """The single sink. Every measurement in the pipeline passes through here."""
    record: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "kind": kind,
        "trace_id": current_trace_id(),
    }
    record.update({k: v for k, v in fields.items() if v is not None})
    logger.info(kind, extra={"obs": record})
    with _sinks_lock:
        sinks = list(_sinks)
    for sink in sinks:
        try:
            sink(record)
        except Exception:  # noqa: BLE001 - a broken sink must never break a request
            logger.exception("observability sink failed")
    return record


# =============================================================================
# Cost estimation
# =============================================================================

_price_warned: set[str] = set()


def _litellm_cost(model: str, prompt_tokens: int | None, completion_tokens: int | None) -> float | None:
    if prompt_tokens is None and completion_tokens is None:
        return None
    try:
        import litellm

        prompt_cost, completion_cost = litellm.cost_per_token(
            model=model,
            prompt_tokens=prompt_tokens or 0,
            completion_tokens=completion_tokens or 0,
        )
        return round(float(prompt_cost) + float(completion_cost), 8)
    except Exception as e:  # noqa: BLE001 - unknown model in the price table, offline, …
        if model not in _price_warned:
            _price_warned.add(model)
            logger.warning("no price for model %s: %s", model, str(e)[:120])
        return None


def token_priced_cost(prompt_tokens: int | None, completion_tokens: int | None) -> float | None:
    """USD these tokens would cost at COST_REFERENCE_MODEL."""
    return _litellm_cost(COST_REFERENCE_MODEL, prompt_tokens, completion_tokens)


def actual_model_cost(model: str | None, prompt_tokens: int | None, completion_tokens: int | None) -> float | None:
    """USD at the configured model's own price, if litellm knows one (hosted models only)."""
    if not model or model.startswith(("ollama", "hosted_vllm/")):
        return None  # self-hosted: no list price
    try:
        from seniocare.model import model_settings

        if model_settings().get("api_base"):
            return None  # custom endpoint (Colab tunnel, vLLM, …): no list price either
    except Exception:  # noqa: BLE001
        pass
    return _litellm_cost(model, prompt_tokens, completion_tokens)


def compute_cost(latency_ms: float | None) -> float | None:
    """USD of GPU time for a self-hosted model: MODEL_GPU_USD_PER_HOUR × wall time."""
    if latency_ms is None or MODEL_GPU_USD_PER_HOUR <= 0:
        return None
    return round(MODEL_GPU_USD_PER_HOUR * (latency_ms / 3_600_000.0), 8)


# =============================================================================
# Output parsing (what the harness and the turn record measure)
# =============================================================================

_SAFETY_RE = re.compile(r"SAFETY_STATUS\s*[:：]\s*\**\s*(ALLOWED|BLOCKED|EMERGENCY)", re.IGNORECASE)
_INTENT_RE = re.compile(r"INTENT\s*[:：]\s*\**\s*([A-Za-z_]+)")
_RESPONSE_TYPE_RE = re.compile(r"RESPONSE_TYPE\s*[:：]\s*\**\s*([A-Za-z_]+)")


def parse_safety_status(text: str | None) -> str | None:
    m = _SAFETY_RE.search(text or "")
    return m.group(1).upper() if m else None


def parse_intent(text: str | None) -> str | None:
    m = _INTENT_RE.search(text or "")
    return m.group(1).lower() if m else None


def parse_response_type(text: str | None) -> str | None:
    m = _RESPONSE_TYPE_RE.search(text or "")
    return m.group(1).lower() if m else None


# =============================================================================
# Per-invocation accumulator (temp: state, discarded after each turn)
# =============================================================================

_ACC_KEY = "temp:obs:acc"


def _fresh_acc() -> dict[str, Any]:
    return {
        "llm_calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "llm_latency_ms": 0,
        "cost_token_priced": 0.0,
        "cost_actual": 0.0,
        "cost_compute": 0.0,
        "tool_calls": 0,
        "tool_latency_ms": 0,
        "already_called": 0,
        "tool_errors": 0,
        "serpapi_calls": 0,
        "stages": [],
        "tools": [],
    }


def _acc(state) -> dict[str, Any]:
    acc = state.get(_ACC_KEY)
    if not isinstance(acc, dict):
        acc = {
            "llm_calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "llm_latency_ms": 0,
            "cost_token_priced": 0.0,
            "cost_actual": 0.0,
            "cost_compute": 0.0,
            "tool_calls": 0,
            "tool_latency_ms": 0,
            "already_called": 0,
            "tool_errors": 0,
            "serpapi_calls": 0,
            "stages": [],
            "tools": [],
        }
    return acc


def _save_acc(state, acc: dict[str, Any]) -> None:
    state[_ACC_KEY] = acc


def _ctx_common(ctx) -> dict[str, Any]:
    """Fields every ADK-originated record carries."""
    session = None
    try:
        session = ctx.session
    except Exception:  # noqa: BLE001
        pass
    user_id = None
    try:
        user_id = ctx.user_id
    except Exception:  # noqa: BLE001
        user_id = ctx.state.get("user:user_id") if hasattr(ctx, "state") else None
    return {
        "invocation_id": getattr(ctx, "invocation_id", None),
        "session_id": getattr(session, "id", None),
        "user_hash": hash_user_id(user_id),
    }


# =============================================================================
# ADK callbacks — model (Point B)
# =============================================================================


def before_model(callback_context, llm_request):
    callback_context.state["temp:obs:llm_started"] = time.perf_counter()
    return None


def after_model(callback_context, llm_response):
    if getattr(llm_response, "partial", False):
        return None  # streaming chunk; the aggregated response follows
    state = callback_context.state
    started = state.get("temp:obs:llm_started")
    latency_ms = round((time.perf_counter() - started) * 1000) if started else None

    usage = getattr(llm_response, "usage_metadata", None)
    prompt_tokens = getattr(usage, "prompt_token_count", None) if usage else None
    completion_tokens = getattr(usage, "candidates_token_count", None) if usage else None

    content = getattr(llm_response, "content", None)
    parts = list(getattr(content, "parts", None) or [])
    text_chars = sum(len(p.text or "") for p in parts if getattr(p, "text", None))
    tool_calls = [p.function_call.name for p in parts if getattr(p, "function_call", None)]

    error_code = getattr(llm_response, "error_code", None)
    finish = getattr(llm_response, "finish_reason", None)
    finish = getattr(finish, "name", None) or (str(finish) if finish else None)

    try:
        from seniocare.model import model_settings

        model_name = model_settings()["model"]
    except Exception:  # noqa: BLE001
        model_name = None

    cost_ref = token_priced_cost(prompt_tokens, completion_tokens)
    cost_act = actual_model_cost(model_name, prompt_tokens, completion_tokens)
    cost_gpu = compute_cost(latency_ms)

    record = emit(
        "llm_call",
        stage=callback_context.agent_name,
        model=model_name,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_token_priced=cost_ref,
        cost_actual=cost_act,
        cost_compute=cost_gpu,
        finish_reason=finish,
        ok=error_code is None,
        error=error_code,
        error_message=(getattr(llm_response, "error_message", None) or None),
        requested_tools=tool_calls or None,
        output_chars=text_chars,
        **_ctx_common(callback_context),
    )

    acc = _acc(state)
    acc["llm_calls"] += 1
    acc["prompt_tokens"] += prompt_tokens or 0
    acc["completion_tokens"] += completion_tokens or 0
    acc["llm_latency_ms"] += latency_ms or 0
    acc["cost_token_priced"] += cost_ref or 0.0
    acc["cost_actual"] += cost_act or 0.0
    acc["cost_compute"] += cost_gpu or 0.0
    _save_acc(state, acc)
    return None


# =============================================================================
# ADK callbacks — tools
# =============================================================================


def before_tool(tool, args, tool_context):
    key = f"temp:obs:tool_started:{getattr(tool_context, 'function_call_id', None) or tool.name}"
    tool_context.state[key] = time.perf_counter()
    return None


def after_tool(tool, args, tool_context, tool_response):
    state = tool_context.state
    key = f"temp:obs:tool_started:{getattr(tool_context, 'function_call_id', None) or tool.name}"
    started = state.get(key)
    latency_ms = round((time.perf_counter() - started) * 1000) if started else None

    status = tool_response.get("status") if isinstance(tool_response, dict) else None
    already_called = status == "already_called"
    error = status == "error" or (isinstance(tool_response, dict) and "error" in tool_response and status != "success")
    result_size = len(json.dumps(tool_response, ensure_ascii=False, default=str)) if tool_response is not None else 0

    emit(
        "tool_call",
        stage=tool_context.agent_name,
        tool=tool.name,
        latency_ms=latency_ms,
        status=status,
        already_called=already_called,
        ok=not error,
        args=list(args.keys()) if isinstance(args, dict) else None,
        result_chars=result_size,
        **_ctx_common(tool_context),
    )

    acc = _acc(state)
    acc["tool_calls"] += 1
    acc["tool_latency_ms"] += latency_ms or 0
    acc["already_called"] += 1 if already_called else 0
    acc["tool_errors"] += 1 if error else 0
    acc["tools"] = list(acc.get("tools", [])) + [tool.name]
    _save_acc(state, acc)
    return None


# =============================================================================
# ADK callbacks — stages (Point A)
# =============================================================================


def before_agent(callback_context):
    callback_context.state[f"temp:obs:stage_started:{callback_context.agent_name}"] = time.perf_counter()
    return None


def after_agent(callback_context):
    state = callback_context.state
    stage = callback_context.agent_name
    started = state.get(f"temp:obs:stage_started:{stage}")
    latency_ms = round((time.perf_counter() - started) * 1000) if started else None

    output_key = STAGE_OUTPUT_KEYS.get(stage)
    output = state.get(output_key, "") if output_key else ""
    output = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False, default=str)

    fields: dict[str, Any] = {}
    if stage == "orchestrator_agent":
        fields["safety_status"] = parse_safety_status(output)
        fields["intent"] = parse_intent(output)
        fields["parse_ok"] = fields["safety_status"] is not None and fields["intent"] is not None
    elif stage == "feature_agent":
        fields["response_type"] = parse_response_type(output)
        fields["parse_ok"] = fields["response_type"] is not None
    elif stage == "report_agent":
        fields["parse_ok"] = bool(re.search(r"STATUS\s*:", output))
    else:
        fields["parse_ok"] = bool(output.strip())

    emit(
        "stage",
        stage=stage,
        latency_ms=latency_ms,
        output_chars=len(output),
        empty_output=not output.strip(),
        **fields,
        **_ctx_common(callback_context),
    )

    acc = _acc(state)
    acc["stages"] = list(acc.get("stages", [])) + [stage]
    _save_acc(state, acc)
    return None


def stage_callbacks() -> dict[str, Any]:
    """Keyword arguments to splice into every LlmAgent constructor."""
    return {
        "before_agent_callback": before_agent,
        "after_agent_callback": after_agent,
        "before_model_callback": before_model,
        "after_model_callback": after_model,
        "before_tool_callback": before_tool,
        "after_tool_callback": after_tool,
    }


# =============================================================================
# Turn (root agent) hooks
# =============================================================================


def turn_started(callback_context) -> None:
    state = callback_context.state
    state["temp:obs:turn_started"] = time.perf_counter()
    state[_ACC_KEY] = _fresh_acc()  # reset for this invocation
    if current_trace_id() is None:
        set_trace_id(new_trace_id())


def turn_finished(callback_context, **extra: Any) -> dict[str, Any]:
    state = callback_context.state
    started = state.get("temp:obs:turn_started")
    e2e = round((time.perf_counter() - started) * 1000) if started else None
    acc = _acc(state)

    orchestrator_output = state.get("orchestrator_result", "") or ""
    feature_output = state.get("feature_result", "") or ""
    final = state.get("final_response", "") or ""

    safety = parse_safety_status(orchestrator_output)
    intent = parse_intent(orchestrator_output)
    response_type = parse_response_type(feature_output)

    record = emit(
        "turn",
        e2e_latency_ms=e2e,
        turn_index=state.get("conversation_turn_count"),
        intent=intent or "unknown",
        intent_parse_ok=intent is not None,
        safety_status=safety,
        safety_parse_ok=safety is not None,
        response_type=response_type,
        stages_run=acc.get("stages"),
        llm_calls=acc.get("llm_calls"),
        prompt_tokens=acc.get("prompt_tokens"),
        completion_tokens=acc.get("completion_tokens"),
        llm_latency_ms=acc.get("llm_latency_ms"),
        stage_sum_vs_e2e=(round(acc.get("llm_latency_ms", 0) / e2e, 3) if e2e else None),
        cost_token_priced=round(acc.get("cost_token_priced", 0.0), 8),
        cost_actual=round(acc.get("cost_actual", 0.0), 8) or None,
        cost_compute=round(acc.get("cost_compute", 0.0), 8) or None,
        tool_calls=acc.get("tool_calls"),
        tools=acc.get("tools"),
        tool_latency_ms=acc.get("tool_latency_ms"),
        already_called=acc.get("already_called"),
        tool_errors=acc.get("tool_errors"),
        serpapi_calls=acc.get("serpapi_calls"),
        final_chars=len(final) if isinstance(final, str) else None,
        empty_final=(not final.strip()) if isinstance(final, str) else None,
        **extra,
        **_ctx_common(callback_context),
    )
    return record


# =============================================================================
# Postgres sink
# =============================================================================

TRACES_DDL = """
CREATE TABLE IF NOT EXISTS llm_traces (
    id                BIGSERIAL PRIMARY KEY,
    ts                TIMESTAMPTZ NOT NULL,
    kind              TEXT NOT NULL,
    trace_id          TEXT,
    invocation_id     TEXT,
    session_id        TEXT,
    user_hash         TEXT,
    stage             TEXT,
    name              TEXT,
    model             TEXT,
    latency_ms        INTEGER,
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    cost_token_priced DOUBLE PRECISION,
    cost_compute      DOUBLE PRECISION,
    ok                BOOLEAN,
    attrs             JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_llm_traces_ts ON llm_traces (ts);
CREATE INDEX IF NOT EXISTS idx_llm_traces_kind_ts ON llm_traces (kind, ts);
CREATE INDEX IF NOT EXISTS idx_llm_traces_trace ON llm_traces (trace_id);
"""

_COLUMNS = (
    "ts", "kind", "trace_id", "invocation_id", "session_id", "user_hash", "stage", "name",
    "model", "latency_ms", "prompt_tokens", "completion_tokens", "cost_token_priced",
    "cost_compute", "ok",
)
_NAME_FIELDS = ("tool", "path", "engine")  # which record field fills the `name` column


def _row(record: dict[str, Any]) -> tuple:
    rec = dict(record)
    name_field = next((f for f in _NAME_FIELDS if f in rec), None)
    name = rec.pop(name_field) if name_field else None
    latency = rec.get("latency_ms", rec.get("e2e_latency_ms"))
    row = (
        rec.get("ts"), rec.get("kind"), rec.get("trace_id"), rec.get("invocation_id"),
        rec.get("session_id"), rec.get("user_hash"), rec.get("stage"), name, rec.get("model"),
        latency, rec.get("prompt_tokens"), rec.get("completion_tokens"),
        rec.get("cost_token_priced"), rec.get("cost_compute"), rec.get("ok"),
    )
    for col in _COLUMNS:
        rec.pop(col, None)
    return row + (json.dumps(rec, ensure_ascii=False, default=str),)


class PostgresSink:
    """Batches records on a background thread so no request waits on the DB."""

    def __init__(self, batch_size: int = 100, flush_interval_s: float = 1.0):
        self.queue: queue.Queue = queue.Queue(maxsize=10_000)
        self.batch_size = batch_size
        self.flush_interval_s = flush_interval_s
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._ready = False
        self._last_error_at = 0.0
        self.written = 0
        self.dropped = 0

    def __call__(self, record: dict[str, Any]) -> None:
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            self.dropped += 1

    def start(self) -> "PostgresSink":
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="obs-postgres-sink", daemon=True)
            self._thread.start()
        return self

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)

    def flush(self, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while not self.queue.empty() and time.monotonic() < deadline:
            time.sleep(0.05)

    def _run(self) -> None:
        from seniocare.data.database import get_connection

        while not self._stop.is_set() or not self.queue.empty():
            batch: list[dict[str, Any]] = []
            try:
                batch.append(self.queue.get(timeout=self.flush_interval_s))
            except queue.Empty:
                continue
            while len(batch) < self.batch_size:
                try:
                    batch.append(self.queue.get_nowait())
                except queue.Empty:
                    break
            try:
                conn = get_connection()
                try:
                    cur = conn.cursor()
                    if not self._ready:
                        cur.execute(TRACES_DDL)
                        self._ready = True
                    cur.executemany(
                        "INSERT INTO llm_traces (" + ", ".join(_COLUMNS) + ", attrs) VALUES ("
                        + ", ".join(["%s"] * len(_COLUMNS)) + ", %s::jsonb)",
                        [_row(r) for r in batch],
                    )
                    conn.commit()
                    self.written += len(batch)
                finally:
                    conn.close()
            except Exception as e:  # noqa: BLE001
                self.dropped += len(batch)
                if time.monotonic() - self._last_error_at > 60:
                    self._last_error_at = time.monotonic()
                    logger.warning("llm_traces write failed (%d records dropped): %s", len(batch), str(e)[:200])


_postgres_sink: PostgresSink | None = None


def start_postgres_sink() -> PostgresSink | None:
    """Attach the Postgres sink if enabled and a database is configured. Idempotent."""
    global _postgres_sink
    if _postgres_sink is not None:
        return _postgres_sink
    if not OBS_DB_ENABLED:
        return None
    from seniocare.data.database import DATABASE_URL

    if not (os.environ.get("APP_DATABASE_URL") or DATABASE_URL):
        return None
    _postgres_sink = PostgresSink().start()
    add_sink(_postgres_sink)
    return _postgres_sink


def stop_postgres_sink() -> None:
    global _postgres_sink
    if _postgres_sink is not None:
        _postgres_sink.flush()
        _postgres_sink.stop()
        remove_sink(_postgres_sink)
        _postgres_sink = None


def sink_stats() -> dict[str, Any]:
    if _postgres_sink is None:
        return {"postgres": None}
    return {
        "postgres": {
            "written": _postgres_sink.written,
            "dropped": _postgres_sink.dropped,
            "queued": _postgres_sink.queue.qsize(),
        }
    }
