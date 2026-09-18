"""Tests for the eval harness's pure parts: parsing, Arabic helpers, assertions, summary.

No model, no database. The runner module imports google.adk lazily, so
this file does not need the ADK mocks either.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("eval_runner", ROOT / "evals" / "runner.py")
runner = importlib.util.module_from_spec(spec)
sys.modules["eval_runner"] = runner
spec.loader.exec_module(runner)

Case, Result = runner.Case, runner.Result


def mk_case(**kw) -> Case:
    base = dict(id="c1", input="x", locale="ar-EG", category="meal", expect={}, assertion="structural", profile="p")
    base.update(kw)
    return Case.from_dict(base)


def mk_result(case: Case, orchestrator="", feature="", final="", tools=(), tool_records=(), error=None, state=None) -> Result:
    r = Result(case_id=case.id, category=case.category, assertion=case.assertion, profile=case.profile, run_id="t", input=case.input)
    r.stages = {"orchestrator": {"text": orchestrator}, "feature": {"text": feature}, "formatter": {"text": final}}
    r.final_response = final
    r.tools_called = list(tools)
    r.tool_records = list(tool_records)
    r.parsed = {
        "safety_status": runner.extract_safety_status(orchestrator),
        "intent": runner.extract_intent(orchestrator),
        "response_type": runner.extract_response_type(feature),
    }
    r.parsed_tolerant = runner._tolerant_parse(orchestrator, feature)
    r.error = error
    r.state_snapshot = state or {}
    return r


# ---------------------------------------------------------------------------
# cases
# ---------------------------------------------------------------------------
def test_case_requires_input_or_turns():
    with pytest.raises(ValueError, match="input\\|turns"):
        Case.from_dict(dict(id="x", category="c", assertion="structural", profile="p"))


def test_scenario_materialises_turn_cases():
    c = mk_case(input=None, turns=[{"input": "a", "expect": {"intent": "meal"}}, {"input": "b", "assertion": "human"}])
    assert c.is_scenario
    t1, t2 = c.turn_case(0), c.turn_case(1)
    assert t1.id == "c1#t1" and t1.expect == {"intent": "meal"} and t1.assertion == "structural"
    assert t2.id == "c1#t2" and t2.assertion == "human" and t2.locale == "ar-EG"


def test_scenario_rejects_turn_without_input():
    with pytest.raises(ValueError, match="turns"):
        mk_case(input=None, turns=[{"expect": {}}])


# ---------------------------------------------------------------------------
# parsing: production regexes vs tolerant
# ---------------------------------------------------------------------------
def test_production_parser_is_strict_and_tolerant_parser_recovers():
    text = "**SAFETY_STATUS:** ALLOWED\n**INTENT:** meal"
    assert runner.extract_intent(text) == "unknown"          # bold breaks the production regex (AUDIT C-03)
    assert runner.extract_safety_status(text) == "unknown"
    tol = runner._tolerant_parse(text, "")
    assert tol["intent"] == "meal" and tol["safety_status"] == "ALLOWED"


# ---------------------------------------------------------------------------
# arabic helpers
# ---------------------------------------------------------------------------
def test_normalize_arabic_unifies_common_variants():
    assert runner.normalize_arabic("أكْلَة") == runner.normalize_arabic("اكله")
    assert runner.normalize_arabic("إزاي") == runner.normalize_arabic("ازاي")
    assert runner.normalize_arabic("مستشفى") == runner.normalize_arabic("مستشفي")
    assert runner.normalize_arabic("ABC") == "abc"


def test_script_ratio():
    ratio, ar, la = runner.script_ratio("أهلاً حضرتك، اتفضل 123")
    assert ratio == 1.0 and la == 0 and ar > 0
    ratio, _, _ = runner.script_ratio("Hello يا فندم")
    assert 0 < ratio < 1


# ---------------------------------------------------------------------------
# structural
# ---------------------------------------------------------------------------
def test_structural_happy_path():
    c = mk_case(expect={"safety_status": "ALLOWED", "intent": "meal", "response_type": "meal_recommendation",
                        "tools_called": ["get_meal_options"], "tools_not_called": ["search_web"]})
    r = mk_result(c, orchestrator="SAFETY_STATUS: ALLOWED\nINTENT: meal", feature="RESPONSE_TYPE: meal_recommendation ...",
                  final="اتفضل يا حضرتك", tools=["get_meal_options", "get_meal_recipe"])
    out = runner.assert_structural(c, r)
    assert all(a["passed"] for a in out), out
    names = {a["name"] for a in out}
    assert {"safety_status", "intent", "response_type", "tools_called", "tools_not_called", "final_nonempty", "feature_output_nonempty"} <= names


def test_structural_flags_forbidden_tool_and_empty_feature():
    c = mk_case(category="emergency", expect={"safety_status": "EMERGENCY", "intent": "emergency", "tools_not_called": ["get_meal_options"]})
    r = mk_result(c, orchestrator="SAFETY_STATUS: EMERGENCY\nINTENT: emergency", final="اتصل بـ 123", tools=["get_meal_options"])
    out = {a["name"]: a for a in runner.assert_structural(c, r)}
    assert out["tools_not_called"]["passed"] is False and "get_meal_options" in out["tools_not_called"]["detail"]

    c2 = mk_case(expect={"safety_status": "ALLOWED", "intent": "meal"})
    r2 = mk_result(c2, orchestrator="SAFETY_STATUS: ALLOWED\nINTENT: meal", feature="", final="كلام حلو")
    out2 = {a["name"]: a for a in runner.assert_structural(c2, r2)}
    assert out2["feature_output_nonempty"]["passed"] is False  # FINDINGS F-04


def test_structural_guard_hit_detection():
    c = mk_case(expect={"tools_not_already_called": ["get_meal_options"]})
    r = mk_result(c, tools=["get_meal_options"], tool_records=[{"tool": "get_meal_options", "already_called": True, "status": "already_called"}])
    out = {a["name"]: a for a in runner.assert_structural(c, r)}
    assert out["tools_not_already_called"]["passed"] is False and "guard hit" in out["tools_not_already_called"]["detail"]

    r2 = mk_result(c, tools=["get_meal_options"], tool_records=[{"tool": "get_meal_options", "already_called": False, "status": "success"}])
    assert {a["name"]: a for a in runner.assert_structural(c, r2)}["tools_not_already_called"]["passed"] is True

    r3 = mk_result(c, tools=[], tool_records=[])
    assert "not called at all" in {a["name"]: a for a in runner.assert_structural(c, r3)}["tools_not_already_called"]["detail"]


def test_structural_state_checks_with_arabic_normalisation():
    c = mk_case(expect={"state_checks": [
        {"path": "user:preferences.food_likes", "contains": "كشري"},
        {"path": "user:preferences.food_dislikes", "not_contains": "كشري"},
        {"path": "conversation_turn_count", "equals": 2},
    ]})
    r = mk_result(c, state={"user:preferences": {"food_likes": ["الكُشَري"], "food_dislikes": []}, "conversation_turn_count": 2})
    out = runner.assert_structural(c, r)
    assert all(a["passed"] for a in out), out


def test_structural_reports_runner_error_first():
    c = mk_case(expect={"intent": "meal"})
    r = mk_result(c, error="Traceback...\nRuntimeError: boom")
    out = runner.assert_structural(c, r)
    assert out == [{"name": "no_error", "passed": False, "detail": "RuntimeError: boom"}]


# ---------------------------------------------------------------------------
# keyword / language / human / evaluate
# ---------------------------------------------------------------------------
def test_keyword_uses_normalisation_both_sides():
    c = mk_case(assertion="keyword", expect={"must_contain": ["123", "إسعاف"], "must_not_contain": ["جمبري"]})
    r = mk_result(c, final="اتصل بالاسعاف على 123 حالاً")
    out = {a["name"]: a for a in runner.assert_keyword(c, r)}
    assert all(a["passed"] for a in out.values()), out


def test_language_script_check_and_dialect_score():
    c = mk_case(assertion="language", expect={"language": "ar-EG"})
    r = mk_result(c, final="أهلاً يا حضرتك، عايز تاكل إيه دلوقتي؟")
    out = {a["name"]: a for a in runner.assert_language(c, r)}
    assert out["arabic_script"]["passed"] is True
    assert out["egyptian_markers"]["passed"] is None and "egyptian=" in out["egyptian_markers"]["detail"]

    r_en = mk_result(c, final="Sure! Here are some lunch options for you.")
    assert {a["name"]: a for a in runner.assert_language(c, r_en)}["arabic_script"]["passed"] is False


def test_human_runs_structural_but_stays_pending():
    c = mk_case(assertion="human", category="emergency", expect={"safety_status": "EMERGENCY"})
    r = mk_result(c, orchestrator="SAFETY_STATUS: EMERGENCY\nINTENT: emergency", final="اتصل 123")
    out = runner.evaluate(c, r)
    names = [a["name"] for a in out]
    assert "human_review" in names and "safety_status" in names
    assert next(a for a in out if a["name"] == "human_review")["passed"] is None


def test_evaluate_appends_keyword_and_language_when_declared():
    c = mk_case(expect={"intent": "meal", "must_contain": ["غدا"], "language": "ar-EG"})
    r = mk_result(c, orchestrator="INTENT: meal", final="اتفضل غدا خفيف يا حضرتك")
    names = {a["name"] for a in runner.evaluate(c, r)}
    assert "intent" in names and "contains 'غدا'" in names and "arabic_script" in names


def test_judge_without_configuration_is_pending():
    c = mk_case(assertion="judge")
    r = mk_result(c, final="x")
    out = runner.assert_judge(c, r)
    assert out[0]["passed"] is None


def test_judge_min_score_gates():
    c = mk_case(assertion="judge", expect={"judge_min_score": 4})
    r = mk_result(c, final="x")
    r.judge = {"rubric": "tone_and_dialect", "score": 3, "rationale": "stiff"}
    assert runner.assert_judge(c, r)[0]["passed"] is False
    r.judge["score"] = 5
    assert runner.assert_judge(c, r)[0]["passed"] is True


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------
def test_summary_confusion_matrix_and_rates():
    c_ok = mk_case(id="a", expect={"safety_status": "ALLOWED", "intent": "meal", "tools_called": ["get_meal_options"]})
    c_em = mk_case(id="b", category="emergency", assertion="human", expect={"safety_status": "EMERGENCY", "intent": "emergency"})
    c_bl = mk_case(id="c", category="blocked", expect={"safety_status": "BLOCKED", "intent": "blocked"})
    r_ok = mk_result(c_ok, orchestrator="SAFETY_STATUS: ALLOWED\nINTENT: meal", feature="RESPONSE_TYPE: x", final="ok", tools=["get_meal_options"])
    r_em = mk_result(c_em, orchestrator="SAFETY_STATUS: ALLOWED\nINTENT: symptom_assessment", final="ok")  # under-escalated
    r_bl = mk_result(c_bl, orchestrator="**SAFETY_STATUS:** BLOCKED\n**INTENT:** blocked", final="ok")   # unparsed by production
    r_ok.metrics = {"turn": {"prompt_tokens": 1000, "completion_tokens": 100, "cost_token_priced": 0.001},
                    "llm": [{"stage": "orchestrator_agent", "latency_ms": 100, "prompt_tokens": 500}]}
    r_ok.e2e_latency_ms, r_em.e2e_latency_ms, r_bl.e2e_latency_ms = 1000, 2000, 3000
    for c, r in ((c_ok, r_ok), (c_em, r_em), (c_bl, r_bl)):
        r.assertions = runner.evaluate(c, r)
    s = runner.build_summary([r_ok, r_em, r_bl], {"a": c_ok, "b": c_em, "c": c_bl}, "run", "test")
    assert s["safety"]["matrix"]["ALLOWED"]["ALLOWED"] == 1
    assert s["safety"]["matrix"]["EMERGENCY"]["ALLOWED"] == 1 and s["safety"]["under_escalated"] == 1
    assert s["safety"]["matrix"]["BLOCKED"]["unknown"] == 1
    assert s["routing"]["correct"] == 1 and s["routing"]["cases"] == 3
    assert s["rates"]["intent_unknown_n"] == 1 and s["rates"]["parser_loss_n"] == 1
    assert s["tools"]["recall"] == 1.0 and s["tools"]["precision"] == 1.0
    assert s["latency"]["e2e_p50_ms"] == 2000 and s["tokens"]["prompt_per_turn_avg"] == 1000
    assert s["human_pending"] == 1
    md = runner.summary_markdown(s, [r_ok, r_em, r_bl])
    assert "Safety status" in md and "under-escalated emergencies: **1**" in md
