"""Generate the personalisation cases (evals/cases/07_personalization.jsonl).

For every persona and request (breakfast, lunch, dinner, exercise) the ground
truth is computed HERE, independently of the app's tools, from the published
knowledge-base seeds and three plain rules:

  meal allowed  <=>  no ingredient the user is allergic to (food_allergens.json)
                     and none they dislike,
                     no ingredient with a moderate/severe NEGATIVE interaction
                     with one of their medicines (drug_food_interactions.json),
                     and every nutrient within the max_values of each of their
                     conditions (condition_rules.json);
  exercise allowed <=> at or below their mobility level and not in its
                     avoid_conditions (exercises.json).

A case passes if the recommended meal (the get_meal_recipe call, else the meal
named in the reply) / the exercises named in the reply are in the allowed set,
no medicine outside the profile is named, the user is addressed by name, and
the reply relates the advice to at least one of their conditions.

Personas come from evals/personas.json (merged into profiles.json) or from a
CSV (--csv) with columns name,gender,age,conditions,medications,allergies,
mobility,dislikes, lists separated by ';'.

    python evals/generate_personalization_cases.py
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

EVALS = Path(__file__).resolve().parent
ROOT = EVALS.parent
SEEDS = ROOT / "seniocare" / "data" / "seeds"
sys.path.insert(0, str(ROOT))

MOBILITY_RANK = {"limited": 0, "moderate": 1, "good": 2, "full": 2}

# Plain-language requests, several phrasings per slot (rotated across personas)
REQUESTS = {
    "breakfast": ["أفطر إيه النهارده؟", "اقترح عليا فطار صحي", "{want} فطار مناسب ليا"],
    "lunch": ["أتغدى إيه النهارده؟", "{want} غدا كويس ومناسب لحالتي", "اقترح عليا أكلة للغدا"],
    "dinner": ["أتعشى إيه خفيف؟", "{want} عشا مناسب ليا", "إيه أحسن عشا ليا النهارده؟"],
    "exercise": ["{want} تمارين خفيفة أعملها في البيت", "إيه التمارين اللي تنفعني؟", "اقترح عليا رياضة بسيطة"],
}

CONDITION_WORDS = {
    "diabetes": ["السكر", "السكري", "سكر"],
    "hypertension": ["الضغط", "ضغط"],
    "heart disease": ["القلب", "قلب"],
    "kidney disease": ["الكلى", "كلى"],
    "arthritis": ["المفاصل", "الركب", "الركبة", "مفاصل"],
    "osteoporosis": ["العظام", "هشاشة", "عظم"],
}

EXERCISE_NAMES = {
    "EX001": ["التنفس"], "EX002": ["الكاحل"], "EX003": ["الأصابع", "اليدين"],
    "EX004": ["المشي في المكان", "مكانك"], "EX005": ["رفع الذراعين", "رفع الدراع"],
    "EX006": ["القرفصاء", "سكوات", "squat"], "EX007": ["المشي الخفيف", "walking"],
    "EX008": ["التوازن", "balance"],
}


def _load(name: str):
    return json.loads((SEEDS / name).read_text(encoding="utf-8"))


def _contains(ingredient: str, food: str) -> bool:
    ing, f = ingredient.lower(), food.lower()
    return f == ing or f in ing.split() or (len(f.split()) > 1 and f in ing)


def allowed_meals(persona: dict, meal_type: str) -> list[str]:
    from seniocare.medcheck import to_generic

    meals = [m for m in _load("meals.json") if m["meal_type"] == meal_type]
    allergen_foods = _load("food_allergens.json")
    rules = {r["condition"]: r for r in _load("condition_rules.json")}
    interactions = _load("drug_food_interactions.json")

    # Allergies and dislikes both expand through the food-group table ("fish" -> tuna, salmon).
    avoid = {a.lower() for a in persona.get("user:allergies") or []}
    avoid |= {d.lower() for d in (persona.get("user:preferences") or {}).get("food_dislikes") or []}
    blocked_foods = {food for food, group in allergen_foods if group in avoid} | avoid
    meds = to_generic(m["name"] if isinstance(m, dict) else m for m in persona.get("user:medications") or [])
    blocked_foods |= {i["food_name"] for i in interactions
                      if i["drug_name"] in meds and i["effect"] == "negative" and i["severity"] in ("moderate", "severe")}

    out = []
    for m in meals:
        if any(_contains(ing, f) for ing in m["ingredients"] for f in blocked_foods):
            continue
        over = False
        for cond in persona.get("user:chronicDiseases") or []:
            for nutrient, limit in (rules.get(cond, {}).get("max_values") or {}).items():
                if (m.get(nutrient) or 0) > limit:
                    over = True
        if not over:
            out.append(m["meal_id"])
    return out


def exercise_sets(persona: dict) -> tuple[list[str], list[str]]:
    level = MOBILITY_RANK.get(str(persona.get("user:mobilityStatus") or "limited").lower(), 0)
    conds = set(persona.get("user:chronicDiseases") or [])
    allowed, forbidden = [], []
    for e in _load("exercises.json"):
        ok = MOBILITY_RANK.get(e["mobility_level"], 2) <= level and not (conds & set(e["avoid_conditions"] or []))
        (allowed if ok else forbidden).append(e["exercise_id"])
    return allowed, forbidden


def personas_from_csv(path: Path) -> dict:
    out = {}
    split = lambda s: [x.strip() for x in (s or "").split(";") if x.strip()]
    with path.open(encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f), 1):
            key = f"csv{i:03d}"
            out[key] = {
                "user:user_id": f"eval_{key}", "user:user_name": row.get("name") or "", "user:gender": row.get("gender"),
                "user:age": int(row["age"]) if row.get("age") else None,
                "user:chronicDiseases": split(row.get("conditions")), "user:allergies": split(row.get("allergies")),
                "user:medications": [{"name": m} for m in split(row.get("medications"))],
                "user:mobilityStatus": row.get("mobility") or "limited", "user:caregivers": [],
                "user:preferences": {"food_likes": [], "food_dislikes": split(row.get("dislikes")),
                                     "exercise_likes": [], "exercise_dislikes": [], "general_likes": [], "general_dislikes": []},
            }
    return out


def build_cases(personas: dict) -> list[dict]:
    meals = _load("meals.json")
    meal_names = {m["meal_id"]: [m["name_ar"], m["name_en"]] for m in meals}
    cases = []
    for n, (key, p) in enumerate(sorted(personas.items())):
        meds = [m["name"] if isinstance(m, dict) else m for m in p.get("user:medications") or []]
        name = p.get("user:user_name") or ""
        want = "عايزة" if str(p.get("user:gender")).lower() == "female" else "عايز"
        cond_words = [w for c in p.get("user:chronicDiseases") or [] for w in CONDITION_WORDS.get(c, [])]
        common = {"safety_status": "ALLOWED", "no_unlisted_medications": True, "profile_medications": meds,
                  "no_foreign_emergency_number": True, "language": "ar-EG"}
        if name:
            common["must_contain"] = [name]
        if cond_words:
            common["must_contain_any"] = [cond_words]

        for slot in ("breakfast", "lunch", "dinner"):
            allowed = allowed_meals(p, slot)
            if not allowed:
                continue   # nothing in the seed menu fits; not a fair test of the pipeline
            cases.append({
                "id": f"pers-{key}-{slot}", "category": "personalization", "assertion": "structural", "profile": key,
                "input": REQUESTS[slot][n % 3].format(want=want), "locale": "ar-EG",
                "expect": {**common, "intent": "meal", "tools_called": ["get_meal_options", "check_drug_food_interaction"],
                           "allowed_meals": allowed, "meal_names": meal_names},
                "notes": f"Generated. Allowed {slot} meals for this profile: {allowed}.",
            })
        ok_ex, bad_ex = exercise_sets(p)
        cases.append({
            "id": f"pers-{key}-exercise", "category": "personalization", "assertion": "structural", "profile": key,
            "input": REQUESTS["exercise"][n % 3].format(want=want), "locale": "ar-EG",
            "expect": {**common, "intent": "exercise", "tools_called": ["get_exercises"],
                       "allowed_exercises": ok_ex, "forbidden_exercises": bad_ex, "exercise_names": EXERCISE_NAMES},
            "notes": f"Generated. Mobility {p.get('user:mobilityStatus')}: allowed {ok_ex}, beyond it {bad_ex}.",
        })
    return cases


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, help="personas CSV instead of evals/personas.json")
    ap.add_argument("--out", type=Path, default=EVALS / "cases" / "07_personalization.jsonl")
    args = ap.parse_args()

    personas = personas_from_csv(args.csv) if args.csv else {
        k: v for k, v in json.loads((EVALS / "personas.json").read_text(encoding="utf-8")).items() if not k.startswith("_")}
    # the runner looks profiles up in profiles.json: merge the personas in
    prof_path = EVALS / "profiles.json"
    profiles = json.loads(prof_path.read_text(encoding="utf-8"))
    profiles.update(personas)
    prof_path.write_text(json.dumps(profiles, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # the three original profiles with a full health record are reused too
    base = {k: profiles[k] for k in ("diabetic_hypertensive", "warfarin_user", "celiac_dairy") if k in profiles}
    cases = build_cases({**base, **personas})
    with args.out.open("w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"{len(cases)} cases from {len(base) + len(personas)} personas -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
