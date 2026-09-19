"""AUDIT C-02 / C-03: the routing decision is code, tolerant, and fails safe. No ADK, no DB."""

import pytest

from seniocare.routing import (
    DEFAULT_BLOCKED_MESSAGE,
    DEFAULT_EMERGENCY_MESSAGE,
    EMERGENCY_NUMBER,
    RouteDecision,
    ensure_emergency_number,
    extract_field,
    route,
)

ALLOWED = """---
SAFETY_STATUS: ALLOWED
INTENT: meal
USER_CONTEXT: Ahmed, 72
TASK_PLAN: call get_meal_options(meal_type="lunch")
---"""

EMERGENCY = """---
SAFETY_STATUS: EMERGENCY
INTENT: emergency
USER_CONTEXT: Ahmed, 72
EMERGENCY_MESSAGE: اتصل بـ 123 فوراً.
اقعد ومتتحركش.
---"""

BLOCKED = """SAFETY_STATUS: BLOCKED
INTENT: blocked
BLOCKED_REASON: dosage change request
BLOCKED_MESSAGE: الجرعة لازم الدكتور يحددها."""


def test_allowed_runs_feature():
    d = route(ALLOWED)
    assert d == RouteDecision("ALLOWED", "meal", True, True, None)
    assert d.route == "full"


def test_emergency_bypasses_feature_with_relay_in_formatter_format():
    d = route(EMERGENCY)
    assert d.safety_status == "EMERGENCY" and d.intent == "emergency" and d.run_feature is False
    assert d.route == "bypass_emergency"
    assert d.feature_result.startswith("RESPONSE_TYPE: emergency\nEMERGENCY_MESSAGE: ")
    assert "اتصل بـ 123 فوراً.\nاقعد ومتتحركش." in d.feature_result


def test_blocked_bypasses_feature():
    d = route(BLOCKED)
    assert d.run_feature is False and d.route == "bypass_blocked"
    assert "BLOCKED_REASON: dosage change request" in d.feature_result
    assert "BLOCKED_MESSAGE: الجرعة لازم الدكتور يحددها." in d.feature_result


@pytest.mark.parametrize("text", [
    "**SAFETY_STATUS:** EMERGENCY\n**INTENT:** emergency",   # markdown bold
    "safety_status: emergency\nintent: Emergency",           # case
    "SAFETY_STATUS： EMERGENCY\nINTENT： emergency",           # full-width colon
    "SAFETY_STATUS:EMERGENCY\nINTENT:emergency",             # no space
])
def test_emergency_parses_through_formatting_drift(text):
    assert route(text).safety_status == "EMERGENCY"


def test_either_signal_is_enough():
    # status says ALLOWED but intent says emergency (or vice-versa): take the safe path
    assert route("SAFETY_STATUS: ALLOWED\nINTENT: emergency").run_feature is False
    assert route("SAFETY_STATUS: EMERGENCY\nINTENT: meal").safety_status == "EMERGENCY"
    assert route("INTENT: blocked").run_feature is False


def test_missing_messages_get_safe_defaults():
    d = route("SAFETY_STATUS: EMERGENCY\nINTENT: emergency")
    assert DEFAULT_EMERGENCY_MESSAGE in d.feature_result and "123" in d.feature_result
    d = route("SAFETY_STATUS: BLOCKED\nINTENT: blocked")
    assert DEFAULT_BLOCKED_MESSAGE in d.feature_result


def test_unparseable_fails_open_but_flags_it():
    d = route("I think the user wants food.")
    assert d.run_feature is True and d.parse_ok is False
    assert d.safety_status == "ALLOWED" and d.intent == "unknown"
    d = route("")
    assert d.run_feature is True and d.parse_ok is False


def test_partial_parse_is_flagged_not_blocked():
    d = route("INTENT: meal")            # no safety status line at all
    assert d.run_feature is True and d.parse_ok is False and d.intent == "meal"


def test_extract_field_stops_at_next_field_or_separator():
    text = "EMERGENCY_MESSAGE: line one\nline two\nUSER_CONTEXT: x\n---"
    assert extract_field(text, "EMERGENCY_MESSAGE") == "line one\nline two"
    assert extract_field("nothing", "EMERGENCY_MESSAGE") is None
    assert extract_field("BLOCKED_REASON: **bold**\n---", "BLOCKED_REASON") == "bold"


# --------------------------------------------------------------------------
# FINDINGS F-11: the ambulance number must survive a Formatter that omits it
# --------------------------------------------------------------------------


def test_emergency_number_is_appended_when_the_model_omits_it():
    # The exact failure observed in run C: urgent, correct, no number.
    text = "\U0001f6a8 \u062a\u0646\u0628\u064a\u0647 \u0637\u0648\u0627\u0631\u0626 \u2014 \u0627\u062a\u0635\u0644 \u0628\u0627\u0644\u0625\u0633\u0639\u0627\u0641 \u0641\u0648\u0631\u0627\u064b"
    out = ensure_emergency_number(text)
    assert EMERGENCY_NUMBER in out
    assert out.startswith(text)


def test_emergency_number_is_not_duplicated():
    text = f"\u0627\u062a\u0635\u0644 \u0639\u0644\u0649 {EMERGENCY_NUMBER} \u062d\u0627\u0644\u0627\u064b"
    assert ensure_emergency_number(text) == text
    once = ensure_emergency_number("no number here")
    assert ensure_emergency_number(once) == once
    assert once.count(EMERGENCY_NUMBER) == 1


def test_emergency_number_handles_empty_output():
    assert EMERGENCY_NUMBER in ensure_emergency_number("")
    assert EMERGENCY_NUMBER in ensure_emergency_number(None)


def test_default_emergency_message_carries_the_number():
    assert EMERGENCY_NUMBER in DEFAULT_EMERGENCY_MESSAGE
    assert EMERGENCY_NUMBER in route("SAFETY_STATUS: EMERGENCY\nINTENT: emergency").feature_result
