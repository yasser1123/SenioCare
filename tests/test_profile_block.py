"""The profile the LLM stages see is rendered in code from user:* state. No ADK, no DB."""

import re
from pathlib import Path

from seniocare.profile import (
    MAX_FACTS_IN_PROMPT,
    addressing_rule,
    medication_names,
    render_profile_block,
)

STATE = {
    "user:user_id": "u1",
    "user:user_name": "أحمد",
    "user:age": 72,
    "user:gender": "male",
    "user:weight": 78.0,
    "user:height": 170.0,
    "user:chronicDiseases": ["diabetes", "hypertension"],
    "user:allergies": ["shellfish"],
    "user:medications": [{"name": "Metformin", "dose": "500mg"}, {"name": "Lisinopril", "dose": "10mg"}],
    "user:mobilityStatus": "limited",
    "user:preferences": {"food_likes": ["chicken"], "food_dislikes": ["fish"]},
}


def test_block_contains_every_profile_fact():
    block = render_profile_block(STATE)
    for fact in ("أحمد", "72", "diabetes", "hypertension", "shellfish",
                 "Metformin 500mg", "Lisinopril 10mg", "limited", "chicken", "fish"):
        assert fact in block, fact
    assert "ONLY medications" in block


def test_no_profile_forbids_assumptions():
    block = render_profile_block({})
    assert "NOT AVAILABLE" in block
    assert "Do NOT assume" in block


def test_empty_fields_are_explicit_not_blank():
    block = render_profile_block({"user:user_id": "u2", "user:medications": []})
    assert "CURRENT MEDICATIONS (the ONLY medications this user takes): none recorded" in block
    assert "ALLERGIES: none recorded" in block


def test_gender_addressing():
    assert "masculine" in addressing_rule("male")
    assert "feminine" in addressing_rule("female")
    assert "neutral" in addressing_rule(None)


def test_medication_names_handles_dicts_and_strings():
    assert medication_names({"user:medications": [{"name": "Warfarin"}, "Aspirin", {"dose": "5mg"}]}) == ["Warfarin", "Aspirin"]


def test_remembered_facts_newest_first_and_capped():
    facts = [{"fact": f"fact {i}", "date": "2026-09-01"} for i in range(MAX_FACTS_IN_PROMPT + 5)]
    block = render_profile_block({**STATE, "user:memory_facts": facts})
    shown = re.findall(r"- fact (\d+)", block)
    assert len(shown) == MAX_FACTS_IN_PROMPT
    assert shown[0] == str(MAX_FACTS_IN_PROMPT + 4)


def test_every_llm_stage_templates_the_profile_block():
    root = Path(__file__).resolve().parents[1] / "seniocare" / "sub_agents"
    for name in ("orchestrator_agent.py", "feature_agent.py", "formatter_agent.py"):
        assert "{user_profile_block}" in (root / name).read_text(encoding="utf-8"), name


def test_orchestrator_no_longer_references_phantom_image_tools():
    text = (Path(__file__).resolve().parents[1] / "seniocare" / "sub_agents" / "orchestrator_agent.py").read_text(encoding="utf-8")
    assert "analyze_medication_image_tool" not in text
    assert "analyze_medical_report_tool" not in text


def test_ablation_withholds_the_block(monkeypatch):
    monkeypatch.setenv("SENIOCARE_PROFILE_IN_PROMPT", "0")
    block = render_profile_block(STATE)
    assert "Metformin" not in block and "not shown" in block
