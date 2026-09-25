"""
Output check: medicines named in a reply that the user does not take.

In run C two replies named Losartan to a user whose profile lists Metformin
and Lisinopril, and both passed every assertion. A reply may name a medicine
only if it is on the user's profile or a tool result named it (e.g. an
interaction warning); anything else is flagged, logged, and followed by a
short correction that lists the medicines actually on file.

Detection only: the lexicon (data/seeds/medication_lexicon.json) is never
used to suggest a medicine. Pure: no ADK imports.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from seniocare.tools._text import normalize_text

_LEXICON = Path(__file__).resolve().parent / "data" / "seeds" / "medication_lexicon.json"


@lru_cache(maxsize=1)
def _alias_index() -> list[tuple[re.Pattern, str]]:
    """(compiled alias pattern, generic name), longest aliases first."""
    data = json.loads(_LEXICON.read_text(encoding="utf-8"))
    pairs = []
    for generic, aliases in data.items():
        if generic.startswith("_"):
            continue
        for alias in {generic, *aliases}:
            norm = normalize_text(alias)
            if len(norm) >= 3:
                pairs.append((norm, generic))
    pairs.sort(key=lambda p: -len(p[0]))
    # Arabic words take clitics (بالميتفورمين, والأسبرين): allow a short prefix.
    return [(re.compile(rf"(?<![\w])(?:[وبلفك]?ال|[وبلفك])?{re.escape(a)}(?![\w])"), g) for a, g in pairs]


def generic_names(text: str) -> set[str]:
    """Generic names of every lexicon medicine mentioned in `text`."""
    norm = " " + normalize_text(text or "") + " "
    found = set()
    for rx, generic in _alias_index():
        if rx.search(norm):
            found.add(generic)
    return found


def to_generic(names: Iterable[str]) -> set[str]:
    out = set()
    for n in names or []:
        g = generic_names(str(n))
        out |= g if g else {normalize_text(str(n))}
    return out


def unlisted_medications(reply: str, profile_medications: Iterable[str], tool_text: str = "") -> list[str]:
    """Medicines named in `reply` that are neither on the profile nor in any tool output."""
    allowed = to_generic(profile_medications) | generic_names(tool_text)
    return sorted(generic_names(reply) - allowed)


def correction_note(profile_medications: Iterable[str]) -> str:
    meds = [str(m) for m in profile_medications or [] if str(m).strip()]
    listed = "، ".join(meds) if meds else "مفيش أدوية مسجلة"
    return (
        f"⚠️ ملحوظة: الأدوية المسجلة في ملفك هي: {listed}. "
        "لو بتاخد دوا تاني، ضيفه في ملفك في التطبيق، ومتغيرش أي دوا من غير ما تكلم الدكتور."
    )
