"""
The user's health profile as a compact text block for the LLM prompts.

The profile arrives through POST /set-user-profile and lives in ``user:*``
session state. The tools always read it from state, but until this module no
prompt contained it: the Orchestrator was asked to reproduce a "full user
profile" it had never been shown, and in run C it invented medications the
user does not take (docs/RESULTS.md, content-safety review). The block is
rendered in code, once per turn, by populate_user_data() and templated into
the Orchestrator, Feature and Formatter prompts as {user_profile_block}.

Pure: no ADK imports, safe to unit-test.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

KEY_PROFILE_BLOCK = "user_profile_block"
KEY_MEMORY_FACTS = "user:memory_facts"

# How many remembered facts are shown to the model (newest first).
MAX_FACTS_IN_PROMPT = 15

_NONE = "none recorded"

_PREF_LABELS = (
    ("food_likes", "likes (food)"),
    ("food_dislikes", "dislikes (food)"),
    ("exercise_likes", "likes (exercise)"),
    ("exercise_dislikes", "dislikes (exercise)"),
    ("general_likes", "likes (general)"),
    ("general_dislikes", "dislikes (general)"),
)


def _join(items: Iterable[Any]) -> str:
    vals = [str(i).strip() for i in (items or []) if str(i).strip()]
    return ", ".join(vals) if vals else _NONE


def _medications(meds: Any) -> str:
    out = []
    for m in meds or []:
        if isinstance(m, Mapping):
            name = str(m.get("name", "")).strip()
            if not name:
                continue
            extra = " ".join(str(m.get(k, "")).strip() for k in ("dose", "frequency") if m.get(k))
            out.append(f"{name} {extra}".strip())
        elif str(m).strip():
            out.append(str(m).strip())
    return ", ".join(out) if out else _NONE


def medication_names(state: Mapping[str, Any]) -> list[str]:
    """Names of the medications on the user's profile."""
    names = []
    for m in state.get("user:medications") or []:
        name = m.get("name") if isinstance(m, Mapping) else m
        if name and str(name).strip():
            names.append(str(name).strip())
    return names


def addressing_rule(gender: Any) -> str:
    g = str(gender or "").strip().lower()
    if g in ("male", "m", "ذكر", "راجل"):
        return "male: address him with masculine forms (e.g. حضرتك، اتفضل، خلّي بالك)"
    if g in ("female", "f", "أنثى", "ست"):
        return "female: address her with feminine forms (e.g. حضرتك، اتفضلي، خلّي بالك)"
    return "unknown: use gender-neutral forms (حضرتك) and avoid gendered verbs"


def render_profile_block(state: Mapping[str, Any]) -> str:
    """Render the profile, preferences and remembered facts as a prompt block."""
    if not state.get("user:user_id"):
        return (
            "PROFILE: NOT AVAILABLE for this user.\n"
            "Do NOT assume any condition, medication or allergy. Give general, safe advice only,\n"
            "and gently suggest completing the health profile in the app."
        )

    lines = [f"NAME: {state.get('user:user_name') or _NONE}"]
    age = state.get("user:age")
    lines.append(f"AGE: {age if age not in (None, '') else _NONE}")
    lines.append(f"GENDER: {addressing_rule(state.get('user:gender'))}")
    w, h = state.get("user:weight"), state.get("user:height")
    if w or h:
        lines.append(f"WEIGHT/HEIGHT: {w or '?'} kg / {h or '?'} cm")
    lines.append(f"CHRONIC CONDITIONS: {_join(state.get('user:chronicDiseases'))}")
    lines.append(f"CURRENT MEDICATIONS (the ONLY medications this user takes): {_medications(state.get('user:medications'))}")
    lines.append(f"ALLERGIES: {_join(state.get('user:allergies'))}")
    lines.append(f"MOBILITY: {state.get('user:mobilityStatus') or _NONE}")
    if state.get("user:bloodType"):
        lines.append(f"BLOOD TYPE: {state.get('user:bloodType')}")

    prefs = state.get("user:preferences") or {}
    pref_parts = [f"{label}: {_join(prefs.get(key))}" for key, label in _PREF_LABELS if prefs.get(key)]
    lines.append("PREFERENCES: " + ("; ".join(pref_parts) if pref_parts else _NONE))

    facts = [f for f in (state.get(KEY_MEMORY_FACTS) or []) if isinstance(f, Mapping) and f.get("fact")]
    if facts:
        lines.append("REMEMBERED FROM EARLIER CONVERSATIONS (newest first):")
        for f in list(reversed(facts))[:MAX_FACTS_IN_PROMPT]:
            date = str(f.get("date", ""))[:10]
            lines.append(f"  - {f['fact']}" + (f" ({date})" if date else ""))

    return "\n".join(lines)
