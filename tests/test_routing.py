"""AUDIT C-02 / C-03: the routing decision is code, tolerant, and fails safe. No ADK, no DB."""

import pytest

from seniocare.routing import (
    DEFAULT_BLOCKED_MESSAGE,
    DEFAULT_EMERGENCY_MESSAGE,
    RouteDecision,
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
