"""AUDIT C-07 / C-08 / C-10: report data comes from real events, inside the period. No DB, no model."""

from datetime import datetime, timedelta
from types import SimpleNamespace

from seniocare.tools import reports as R


def ev(ts, author=None, text=None, call=None, response=None):
    parts = []
    if text is not None:
        parts.append(SimpleNamespace(text=text, function_call=None, function_response=None))
    if call is not None:
        parts.append(SimpleNamespace(text=None, function_call=SimpleNamespace(name=call[0], args=call[1]), function_response=None))
    if response is not None:
        parts.append(SimpleNamespace(text=None, function_call=None, function_response=SimpleNamespace(name=response[0], response=response[1])))
    return SimpleNamespace(timestamp=ts, author=author, content=SimpleNamespace(parts=parts))


NOW = datetime.now().timestamp()
DAY = 86400


def test_facts_come_from_tool_events():
    events = [
        ev(NOW - 100, "user", "حاسس بدوخة"),
        ev(NOW - 99, "orchestrator_agent", "SAFETY_STATUS: ALLOWED\nINTENT: symptom_assessment"),
        ev(NOW - 98, "feature_agent", call=("assess_symptoms", {"symptoms": ["dizziness", "headache"]})),
        ev(NOW - 97, "feature_agent", response=("assess_symptoms", {"status": "success", "overall_severity": "MONITOR",
                                                                     "is_emergency": False,
                                                                     "matches": [{"disease_name": "mild dehydration", "confidence": 33.3}]})),
        ev(NOW - 96, "feature_agent", response=("get_meal_options", {"status": "success", "options": [{"name_ar": "شوربة عدس"}]})),
        ev(NOW - 95, "feature_agent", response=("check_drug_food_interaction", {"status": "success",
                                                                                 "harmful_interactions": [{"drug": "warfarin", "food": "spinach", "severity": "severe"}]})),
        ev(NOW - 94, "feature_agent", response=("get_exercises", {"status": "success", "exercises": [{"name_ar": "مشي"}]})),
    ]
    f = R.extract_session_facts(events, None, None, "s1")
    assert f["turns_in_period"] == 1 and f["sessions_in_period"] == 1
    assert "symptom_assessment" in f["conversation_topics"] and "حاسس بدوخة" in f["conversation_topics"]
    assert [x["symptom"] for x in f["symptoms_reported"] if "symptom" in x] == ["dizziness", "headache"]
    assert any(x.get("top_match") == "mild dehydration" for x in f["symptoms_reported"])
    assert f["meals_accessed"][0]["meal"] == "شوربة عدس"
    assert f["interaction_warnings"][0]["food"] == "spinach"
    assert f["exercises_accessed"][0]["exercise"] == "مشي"
    assert f["emergency_events"] == []


def test_period_filter_excludes_old_events():
    old = ev(NOW - 40 * DAY, "user", "old message")
    new = ev(NOW - 1 * DAY, "user", "new message")
    start, end = R._date_bounds((datetime.now() - timedelta(days=7)).date().isoformat(), datetime.now().date().isoformat())
    f = R.extract_session_facts([old, new], start, end)
    assert f["conversation_topics"] == ["new message"] and f["turns_in_period"] == 1


def test_emergency_events_detected_from_either_signal():
    events = [ev(NOW - 5, "orchestrator_agent", "**SAFETY_STATUS:** EMERGENCY\n**INTENT:** emergency")]
    f = R.extract_session_facts(events)
    assert len(f["emergency_events"]) == 1 and f["emergency_events"][0]["session_id"] == ""


def test_date_bounds_cover_the_whole_end_day():
    start, end = R._date_bounds("2026-09-01", "2026-09-01")
    assert end - start > DAY - 1


def test_status_parsing_unknown_not_moderate():
    status, content, _ = R._parse_markdown_report("# تقرير\nno status line here", "daily", {"name": "x"})
    assert status == "unknown" and "no status line" in content
    status, content, _ = R._parse_markdown_report("**STATUS:** Concerning\n# تقرير\nbody", "daily", {"name": "x"})
    assert status == "concerning" and "STATUS" not in content
    status, _, _ = R._parse_markdown_report("STATUS: excellent\nbody", "daily", None)
    assert status == "unknown"  # not one of the four allowed values
