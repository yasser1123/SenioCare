"""Tests for seniocare.observability — no database, no model, no network.

The ADK callback objects are replaced by minimal fakes exposing the attributes
the callbacks read (state, agent_name, invocation_id, session, user_id).
"""

import io
import json
import logging
import time
from types import SimpleNamespace

import pytest

from seniocare import observability as obs


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
class FakeCtx:
    def __init__(self, agent_name="orchestrator_agent", state=None, user_id="user_42", function_call_id=None):
        self.state = state if state is not None else {}
        self.agent_name = agent_name
        self.invocation_id = "inv-1"
        self.session = SimpleNamespace(id="sess-1")
        self.user_id = user_id
        self.function_call_id = function_call_id


@pytest.fixture
def captured():
    records = []
    obs.add_sink(records.append)
    yield records
    obs.remove_sink(records.append)


def _llm_response(prompt=100, completion=20, text="INTENT: meal", partial=False, tool=None):
    parts = [SimpleNamespace(text=text, function_call=None)]
    if tool:
        parts.append(SimpleNamespace(text=None, function_call=SimpleNamespace(name=tool)))
    return SimpleNamespace(
        partial=partial,
        usage_metadata=SimpleNamespace(prompt_token_count=prompt, candidates_token_count=completion),
        content=SimpleNamespace(parts=parts),
        error_code=None,
        error_message=None,
        finish_reason=SimpleNamespace(name="STOP"),
    )


# ---------------------------------------------------------------------------
# emit / sinks / logging
# ---------------------------------------------------------------------------
def test_emit_returns_record_and_feeds_sinks(captured):
    token = obs.set_trace_id("abc123")
    try:
        rec = obs.emit("unit_test", value=1, skipped=None)
    finally:
        obs.reset_trace_id(token)
    assert rec["kind"] == "unit_test" and rec["value"] == 1 and rec["trace_id"] == "abc123"
    assert "skipped" not in rec  # None fields are dropped
    assert captured[-1] is rec


def test_broken_sink_does_not_break_emit(captured):
    def bad(_):
        raise RuntimeError("boom")

    obs.add_sink(bad)
    try:
        rec = obs.emit("unit_test_bad_sink")
    finally:
        obs.remove_sink(bad)
    assert rec["kind"] == "unit_test_bad_sink"
    assert captured[-1] is rec  # the good sink still received it


def test_json_formatter_merges_record_payload():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(obs.JsonFormatter())
    log = logging.getLogger("seniocare.obs.test")
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    try:
        log.info("x", extra={"obs": {"kind": "k", "latency_ms": 5, "arabic": "أهلاً"}})
    finally:
        log.removeHandler(handler)
    line = json.loads(stream.getvalue().strip())
    assert line["kind"] == "k" and line["latency_ms"] == 5 and line["arabic"] == "أهلاً"
    assert "ts" in line and line["level"] == "INFO"


def test_hash_user_id_is_stable_and_not_the_id():
    h = obs.hash_user_id("elder_123")
    assert h == obs.hash_user_id("elder_123")
    assert len(h) == 12 and "elder" not in h
    assert obs.hash_user_id(None) is None


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("text, expected", [
    ("SAFETY_STATUS: ALLOWED\nINTENT: meal", "ALLOWED"),
    ("**SAFETY_STATUS:** EMERGENCY", "EMERGENCY"),
    ("safety_status: blocked", "BLOCKED"),
    ("SAFETY_STATUS： ALLOWED", "ALLOWED"),  # full-width colon
    ("no status here", None),
    ("", None),
    (None, None),
])
def test_parse_safety_status(text, expected):
    assert obs.parse_safety_status(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("INTENT: meal", "meal"),
    ("INTENT: Symptom_Assessment", "symptom_assessment"),
    ("**INTENT:** emergency", "emergency"),
    ("nothing", None),
])
def test_parse_intent(text, expected):
    assert obs.parse_intent(text) == expected


def test_parse_response_type():
    assert obs.parse_response_type("RESPONSE_TYPE: meal_recommendation") == "meal_recommendation"
    assert obs.parse_response_type("RESPONSE_TYPE: **blocked**") == "blocked"
    assert obs.parse_response_type("") is None


# ---------------------------------------------------------------------------
# cost
# ---------------------------------------------------------------------------
def test_compute_cost_uses_gpu_rate(monkeypatch):
    monkeypatch.setattr(obs, "MODEL_GPU_USD_PER_HOUR", 0.36)
    assert obs.compute_cost(10_000) == pytest.approx(0.001)  # 10 s at $0.36/h
    monkeypatch.setattr(obs, "MODEL_GPU_USD_PER_HOUR", 0)
    assert obs.compute_cost(10_000) is None
    assert obs.compute_cost(None) is None


def test_token_priced_cost_uses_reference_price_table():
    cost = obs.token_priced_cost(1_000_000, 0)
    # gemini-2.5-flash input is priced; exact value depends on litellm's table, so
    # only assert it is a sensible positive number well under $10 per million.
    assert cost is not None and 0 < cost < 10


def test_actual_model_cost_is_none_for_self_hosted():
    assert obs.actual_model_cost("ollama_chat/gemma4:e4b", 100, 10) is None
    assert obs.actual_model_cost("hosted_vllm/x", 100, 10) is None
    assert obs.actual_model_cost(None, 100, 10) is None


# ---------------------------------------------------------------------------
# callbacks
# ---------------------------------------------------------------------------
def test_model_callbacks_emit_llm_call_with_tokens_and_cost(captured):
    ctx = FakeCtx("feature_agent")
    obs.before_model(ctx, llm_request=None)
    time.sleep(0.01)
    assert obs.after_model(ctx, _llm_response(prompt=1500, completion=200, tool="get_meal_options")) is None

    rec = captured[-1]
    assert rec["kind"] == "llm_call"
    assert rec["stage"] == "feature_agent"
    assert rec["prompt_tokens"] == 1500 and rec["completion_tokens"] == 200
    assert rec["latency_ms"] >= 10
    assert rec["ok"] is True and rec["finish_reason"] == "STOP"
    assert rec["requested_tools"] == ["get_meal_options"]
    assert rec["cost_token_priced"] is not None and rec["cost_token_priced"] > 0
    assert rec["user_hash"] == obs.hash_user_id("user_42")
    assert rec["session_id"] == "sess-1" and rec["invocation_id"] == "inv-1"

    acc = ctx.state[obs._ACC_KEY]
    assert acc["llm_calls"] == 1 and acc["prompt_tokens"] == 1500


def test_partial_streaming_chunks_are_ignored(captured):
    ctx = FakeCtx()
    obs.before_model(ctx, None)
    before = len(captured)
    obs.after_model(ctx, _llm_response(partial=True))
    assert len(captured) == before


def test_tool_callbacks_measure_latency_and_guard_hits(captured):
    ctx = FakeCtx("feature_agent", function_call_id="fc-9")
    tool = SimpleNamespace(name="check_drug_food_interaction")
    obs.before_tool(tool, {"food_names": ["spinach"]}, ctx)
    obs.after_tool(tool, {"food_names": ["spinach"]}, ctx, {"status": "already_called", "message": "x"})
    rec = captured[-1]
    assert rec["kind"] == "tool_call" and rec["tool"] == "check_drug_food_interaction"
    assert rec["already_called"] is True and rec["ok"] is True and rec["args"] == ["food_names"]
    assert isinstance(rec["latency_ms"], int)

    obs.before_tool(tool, {}, ctx)
    obs.after_tool(tool, {}, ctx, {"status": "error", "error": "db down"})
    assert captured[-1]["ok"] is False

    acc = ctx.state[obs._ACC_KEY]
    assert acc["tool_calls"] == 2 and acc["already_called"] == 1 and acc["tool_errors"] == 1
    assert acc["tools"] == ["check_drug_food_interaction"] * 2


def test_stage_callbacks_parse_orchestrator_output(captured):
    ctx = FakeCtx("orchestrator_agent")
    obs.before_agent(ctx)
    ctx.state["orchestrator_result"] = "SAFETY_STATUS: EMERGENCY\nINTENT: emergency\nTASK_PLAN: none"
    obs.after_agent(ctx)
    rec = captured[-1]
    assert rec["kind"] == "stage" and rec["stage"] == "orchestrator_agent"
    assert rec["safety_status"] == "EMERGENCY" and rec["intent"] == "emergency" and rec["parse_ok"] is True
    assert rec["empty_output"] is False

    ctx2 = FakeCtx("orchestrator_agent")
    obs.before_agent(ctx2)
    ctx2.state["orchestrator_result"] = "I think this is about food."
    obs.after_agent(ctx2)
    assert captured[-1]["parse_ok"] is False and "intent" not in captured[-1]


def test_turn_record_aggregates_everything(captured):
    ctx = FakeCtx("seniocare", state={"conversation_turn_count": 2})
    obs.turn_started(ctx)

    obs.before_agent(FakeCtx("orchestrator_agent", state=ctx.state))
    obs.before_model(ctx, None)
    obs.after_model(ctx, _llm_response(prompt=1000, completion=50, text="SAFETY_STATUS: ALLOWED\nINTENT: meal"))
    ctx.state["orchestrator_result"] = "SAFETY_STATUS: ALLOWED\nINTENT: meal"
    obs.after_agent(FakeCtx("orchestrator_agent", state=ctx.state))

    tool = SimpleNamespace(name="get_meal_options")
    tctx = FakeCtx("feature_agent", state=ctx.state, function_call_id="fc-1")
    obs.before_tool(tool, {}, tctx)
    obs.after_tool(tool, {}, tctx, {"status": "success"})
    ctx.state["feature_result"] = "RESPONSE_TYPE: meal_recommendation"
    ctx.state["final_response"] = "اتفضل يا حضرتك"

    rec = obs.turn_finished(ctx, emergency_triggered=False)
    assert rec["kind"] == "turn"
    assert rec["intent"] == "meal" and rec["safety_status"] == "ALLOWED"
    assert rec["intent_parse_ok"] is True and rec["safety_parse_ok"] is True
    assert rec["response_type"] == "meal_recommendation"
    assert rec["stages_run"] == ["orchestrator_agent"]
    assert rec["llm_calls"] == 1 and rec["prompt_tokens"] == 1000 and rec["completion_tokens"] == 50
    assert rec["tool_calls"] == 1 and rec["tools"] == ["get_meal_options"] and rec["already_called"] == 0
    assert rec["turn_index"] == 2 and rec["empty_final"] is False
    assert rec["emergency_triggered"] is False
    assert isinstance(rec["e2e_latency_ms"], int)


def test_turn_started_resets_accumulator():
    ctx = FakeCtx(state={obs._ACC_KEY: {"llm_calls": 99}})
    obs.turn_started(ctx)
    assert ctx.state[obs._ACC_KEY]["llm_calls"] == 0


def test_stage_callbacks_bundle_has_all_six_slots():
    cb = obs.stage_callbacks()
    assert set(cb) == {
        "before_agent_callback", "after_agent_callback",
        "before_model_callback", "after_model_callback",
        "before_tool_callback", "after_tool_callback",
    }


# ---------------------------------------------------------------------------
# postgres sink row mapping (no DB needed)
# ---------------------------------------------------------------------------
def test_row_mapping_puts_unknown_fields_in_attrs():
    rec = {"ts": "t", "kind": "tool_call", "trace_id": "tr", "tool": "get_exercises",
           "latency_ms": 12, "ok": True, "already_called": False, "args": ["mobility"]}
    row = obs._row(rec)
    assert row[1] == "tool_call" and row[7] == "get_exercises" and row[9] == 12 and row[14] is True
    attrs = json.loads(row[-1])
    assert attrs == {"already_called": False, "args": ["mobility"]}


def test_row_mapping_uses_e2e_latency_for_turns():
    row = obs._row({"ts": "t", "kind": "turn", "e2e_latency_ms": 4321})
    assert row[9] == 4321
