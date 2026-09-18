"""AUDIT C-12 / C-13 / C-14: text normalisation and matching. No DB."""

from seniocare.tools._text import (
    ingredient_contains,
    normalize_drug_name,
    normalize_text,
    phrase_match,
    symptom_matches,
    symptom_synonyms,
    tokens,
)


def test_normalize_text_unifies_arabic_variants():
    assert normalize_text("أَلَمٌ في الصَّدر") == normalize_text("الم في الصدر")
    assert normalize_text("إزاي؟") == "ازاي"
    assert normalize_text("Metformin,  500MG") == "metformin 500mg"


def test_tokens_strip_stop_words_and_arabic_affixes():
    assert tokens("pain in the chest") == ["pain", "chest"]
    assert tokens("وجع في صدري") == ["وجع", "صدر"]
    assert tokens("الصدر") == ["صدر"]


def test_phrase_match_is_word_level_not_substring():
    assert phrase_match("chest pain", "chest pain")
    assert phrase_match("pain in my chest", "chest pain")
    assert not phrase_match("pain", "chest pain")          # C-12: bare 'pain' is not chest pain
    assert phrase_match("severe headache", "sudden severe headache")  # covers 2 of 3 tokens
    assert not phrase_match("headache", "sudden severe headache")      # covers 1 of 3: too weak
    assert phrase_match("headache", "mild headache")
    assert not phrase_match("وجع", "وجع في الصدر")                    # generic token alone
    assert phrase_match("dizzy", "dizziness")               # prefix stem
    assert not phrase_match("peanut", "pea")
    assert phrase_match("وجع في صدري", "وجع الصدر")


def test_symptom_matches_arabic_through_synonyms():
    assert symptom_matches("ألم في الصدر", "chest pain")
    assert symptom_matches("صدري بيوجعني", "chest pain")
    assert symptom_matches("وشي مايل", "face drooping")
    assert symptom_matches("مش قادر اتكلم", "speech difficulty")
    assert symptom_matches("دوخة", "dizziness")
    assert symptom_matches("عطشان اوي", "excessive thirst") or symptom_matches("عطشان اوي", "thirst")
    assert not symptom_matches("دوخة", "chest pain")
    assert not symptom_matches("صداع خفيف", "face drooping")


def test_synonym_table_covers_every_db_phrase():
    import json
    from pathlib import Path

    seeds = json.loads((Path(__file__).resolve().parents[1] / "seniocare/data/seeds/disease_symptoms.json").read_text(encoding="utf-8"))
    db = {s.lower() for d in seeds for s in d["symptoms"]}
    assert db <= set(symptom_synonyms()), sorted(db - set(symptom_synonyms()))


def test_normalize_drug_name_strips_dose_and_form():
    assert normalize_drug_name("Metformin 500mg") == "metformin"
    assert normalize_drug_name("Warfarin 5 mg tabs") == "warfarin"
    assert normalize_drug_name("Lisinopril (10mg, morning)") == "lisinopril"
    assert normalize_drug_name("Aspirin 81 MG tablet daily") == "aspirin"
    assert normalize_drug_name("ميتفورمين") == "ميتفورمين"
    assert normalize_drug_name("") == ""


def test_ingredient_contains_allergen_as_word():
    assert ingredient_contains("cottage cheese", "cheese")
    assert ingredient_contains("whole wheat bread", "wheat")
    assert ingredient_contains("shrimp", "shrimp")
    assert ingredient_contains("grilled shrimp with garlic", "shrimp")
    assert not ingredient_contains("peanut butter", "pea")
    assert not ingredient_contains("chicken breast", "cheese")
