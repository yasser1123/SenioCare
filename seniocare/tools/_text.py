"""
Text normalisation and matching shared by the data tools.

Fixes three families of silent misses found in the audit:
- C-13  the symptom database is English while users write Egyptian Arabic;
- C-14  drug and allergen joins were exact-string ("Metformin 500mg" never
        matched "metformin"; "cheese" never matched "cottage cheese");
- C-12  substring matching over-matched ("pain" inside "chest pain").

Everything here is pure and dependency-free so it can be unit-tested
without a database.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

_TASHKEEL = re.compile(r"[ً-ْٰـ]")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")

# Small stop-word lists; only words that never carry symptom/food meaning.
_STOP_EN = {"in", "of", "the", "a", "an", "and", "or", "is", "are", "has", "have", "with", "my", "i", "at", "to"}
_STOP_AR = {"في", "من", "على", "عند", "عندي", "انا", "أنا", "و", "مع", "ال", "ده", "دي", "كده", "جدا", "اوي", "قوي", "شوية", "حاسس", "حاسه", "بحس", "عايز", "عايزه"}

_AR_PREFIXES = ("وال", "بال", "فال", "كال", "ال", "و", "ب")
_AR_SUFFIXES = ("هما", "كما", "ها", "ات", "ين", "ون", "ية", "ه", "ي", "ك")


def normalize_text(text: str) -> str:
    """Lowercase; strip tashkeel/tatweel and punctuation; unify alef, taa marbuta, alef maqsura, hamza seats."""
    text = unicodedata.normalize("NFC", str(text or ""))
    text = _TASHKEEL.sub("", text)
    text = re.sub(r"[إأآٱ]", "ا", text)
    text = text.replace("ة", "ه").replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي")
    text = _PUNCT.sub(" ", text.lower())
    return _WS.sub(" ", text).strip()


def _strip_arabic_affixes(token: str) -> str:
    if not re.search(r"[ء-ي]", token):
        return token
    for p in _AR_PREFIXES:
        if token.startswith(p) and len(token) - len(p) >= 3:
            token = token[len(p):]
            break
    for s in _AR_SUFFIXES:
        if token.endswith(s) and len(token) - len(s) >= 3:
            token = token[: -len(s)]
            break
    return token


def tokens(text: str) -> list[str]:
    """Content tokens of a phrase, normalised and lightly stemmed (Arabic affixes)."""
    out = []
    for tok in normalize_text(text).split():
        if tok in _STOP_EN or tok in _STOP_AR:
            continue
        out.append(_strip_arabic_affixes(tok))
    return out


def _token_eq(a: str, b: str) -> bool:
    """Equal, or the same stem: a common prefix of at least 4 characters that
    covers all but the last two characters of the shorter token
    (dizzy/dizziness, swell/swelling, sweat/sweating; not pea/peanut)."""
    if a == b:
        return True
    shorter = min(len(a), len(b))
    if shorter < 4:
        return False
    common = 0
    for x, y in zip(a, b):
        if x != y:
            break
        common += 1
    return common >= max(4, shorter - 2)


# Tokens that carry no discriminating meaning on their own: a match must
# include at least one token outside this set, so a bare "pain" or "وجع" does
# not attach itself to every "<body part> pain" symptom (AUDIT C-12).
_GENERIC = {"pain", "pains", "ache", "aches", "severe", "mild", "sudden", "difficulty", "loss", "feeling",
            "الم", "وجع", "شديد", "خفيف", "صعوب", "فقدان", "حاس", "عند"}


def phrase_match(a: str, b: str) -> bool:
    """Word-level match, never a bare substring test.

    True when the phrases are equal after normalisation, or when every content
    token of the shorter phrase occurs in the longer one (same stem), at least
    one matched token is not generic, and the match covers at least half of
    the longer phrase. So 'pain in my chest' matches 'chest pain' and
    'وجع في صدري' matches 'وجع الصدر', but 'pain' matches neither."""
    na, nb = normalize_text(a), normalize_text(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return False
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    matched = [s for s in short if any(_token_eq(s, l) for l in long_)]
    if len(matched) != len(short):
        return False
    if not any(m not in _GENERIC for m in matched):
        return False
    return len(matched) * 2 >= len(long_)


# ---------------------------------------------------------------------------
# Drug names
# ---------------------------------------------------------------------------

_DOSE_RE = re.compile(r"\b\d+([.,]\d+)?\s*(mg|mcg|µg|ug|g|ml|iu|units?|%)\b", re.IGNORECASE)
_FORM_WORDS = {"tablet", "tablets", "tab", "tabs", "capsule", "capsules", "cap", "caps", "pill", "pills",
               "syrup", "injection", "drops", "cream", "xr", "sr", "er", "od", "bd", "tds", "daily",
               "قرص", "اقراص", "أقراص", "كبسوله", "كبسولة", "حبايه", "حباية", "شراب", "حقنه", "حقنة"}


def normalize_drug_name(name: str) -> str:
    """'Metformin 500mg (twice daily)' -> 'metformin'; 'Warfarin 5 mg tabs' -> 'warfarin'."""
    s = re.sub(r"\(.*?\)", " ", str(name or ""))
    s = _DOSE_RE.sub(" ", s)
    s = normalize_text(s)
    words = [w for w in s.split() if w not in _FORM_WORDS and not w.isdigit()]
    return " ".join(words).strip()


# ---------------------------------------------------------------------------
# Allergen / ingredient matching
# ---------------------------------------------------------------------------


def ingredient_contains(ingredient: str, food: str) -> bool:
    """Does an ingredient line contain the allergen food, as a whole word or
    token set? 'cottage cheese' ⊇ 'cheese', 'whole wheat bread' ⊇ 'wheat bread',
    but 'peanut' does not match 'pea'."""
    ti, tf = tokens(ingredient), tokens(food)
    if not ti or not tf:
        return False
    return all(any(_token_eq(f, i) or i == f for i in ti) for f in tf)


# ---------------------------------------------------------------------------
# Symptom synonyms (Arabic -> English database phrases), AUDIT C-13
# ---------------------------------------------------------------------------

_SYNONYMS_PATH = Path(__file__).resolve().parents[1] / "data" / "seeds" / "symptom_synonyms_ar.json"


@lru_cache(maxsize=1)
def symptom_synonyms() -> dict[str, list[str]]:
    """{english db phrase: [arabic/english variants…]} — empty dict if the file is missing."""
    try:
        with open(_SYNONYMS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return {k.lower(): [str(v) for v in vs] for k, vs in data.items() if isinstance(vs, list)}
    except (OSError, ValueError):
        return {}


def symptom_matches(user_symptom: str, db_symptom: str) -> bool:
    """User phrase (Arabic or English) vs a database symptom phrase (English)."""
    if phrase_match(user_symptom, db_symptom):
        return True
    for variant in symptom_synonyms().get(db_symptom.lower(), []):
        if phrase_match(user_symptom, variant):
            return True
    return False
