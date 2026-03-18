"""
Unit tests for symptom assessment tool: assess_symptoms.

Covers:
- Emergency detection (stroke, heart attack)
- Normal symptom matching, condition boost
- Edge cases: single vague symptom, mixed severities, empty symptoms
- Helper functions: _fuzzy_symptom_match, _condition_relates_to_disease
"""

import pytest
from seniocare.tools.symptoms import (
    assess_symptoms,
    _fuzzy_symptom_match,
    _condition_relates_to_disease,
)


# ===========================================================================
# assess_symptoms
# ===========================================================================
class TestAssessSymptoms:
    """Comprehensive tests for assess_symptoms."""

    def test_emergency_stroke(self, fresh_context):
        """Stroke symptoms should trigger EMERGENCY."""
        ctx = fresh_context()
        result = assess_symptoms(
            symptoms=["sudden severe headache", "face drooping", "arm weakness", "speech difficulty"],
            tool_context=ctx,
        )
        assert result["status"] == "success"
        assert result["is_emergency"] is True
        assert result["overall_severity"] == "EMERGENCY"
        assert result["emergency_action"] is not None
        assert result["matches"][0]["disease_name"] == "stroke"

    def test_emergency_heart_attack(self, fresh_context):
        """Heart attack symptoms should trigger EMERGENCY."""
        ctx = fresh_context()
        result = assess_symptoms(
            symptoms=["chest pain", "shortness of breath", "pain in left arm", "cold sweat"],
            tool_context=ctx,
        )
        assert result["status"] == "success"
        assert result["is_emergency"] is True
        assert result["matches"][0]["disease_name"] == "heart attack"
        assert len(result["matches"][0]["precautions"]) > 0

    def test_normal_symptoms(self, fresh_context):
        """Mild symptoms should return NORMAL or MONITOR severity."""
        ctx = fresh_context()
        result = assess_symptoms(
            symptoms=["runny nose", "sneezing", "itchy eyes", "nasal congestion"],
            tool_context=ctx,
        )
        assert result["status"] == "success"
        top = result["matches"][0]
        assert top["severity"] in ("NORMAL", "MONITOR"), (
            f"Top match '{top['disease_name']}' severity={top['severity']}, expected NORMAL/MONITOR"
        )

    def test_no_symptoms(self, empty_context):
        """Empty symptoms list should return no_symptoms."""
        result = assess_symptoms(symptoms=[], tool_context=empty_context)
        assert result["status"] == "no_symptoms"
        assert result["matches"] == []

    def test_condition_boost_diabetes(self):
        """Diabetes user reporting diabetes symptoms should get higher confidence."""
        from tests.conftest import MockToolContext

        # Use symptoms that strongly match diabetes complications (DIS007)
        # but DON'T overlap with emergency diseases (stroke/heart attack)
        # to avoid them ranking above diabetes in the top-3
        diabetes_symptoms = [
            "excessive thirst", "frequent urination",
            "slow healing wounds", "tingling in hands", "tingling in feet",
        ]

        ctx_no_conditions = MockToolContext(state={"user:chronicDiseases": []})
        result_no_boost = assess_symptoms(
            symptoms=diabetes_symptoms,
            tool_context=ctx_no_conditions,
        )

        ctx_diabetes = MockToolContext(state={"user:chronicDiseases": ["diabetes"]})
        result_boosted = assess_symptoms(
            symptoms=diabetes_symptoms,
            tool_context=ctx_diabetes,
        )

        assert result_no_boost["status"] == "success"
        assert result_boosted["status"] == "success"

        # Find diabetes matches in both (may be named "diabetes complications")
        no_boost_conf = None
        boosted_conf = None
        for m in result_no_boost["matches"]:
            if "diabet" in m["disease_name"].lower():
                no_boost_conf = m["confidence"]
        for m in result_boosted["matches"]:
            if "diabet" in m["disease_name"].lower():
                boosted_conf = m["confidence"]

        # At minimum, the boosted version should find a diabetes-related match
        assert boosted_conf is not None, (
            f"Boosted should match diabetes. Matches: {[m['disease_name'] for m in result_boosted['matches']]}"
        )
        # The boosted match should be condition-related
        for m in result_boosted["matches"]:
            if "diabet" in m["disease_name"].lower():
                assert m["is_condition_related"] is True

        # If both have the match, boosted confidence should be higher
        if no_boost_conf is not None and boosted_conf is not None:
            assert boosted_conf > no_boost_conf, (
                f"Boosted ({boosted_conf}) should be > non-boosted ({no_boost_conf})"
            )

    def test_prevents_double_call(self, fresh_context):
        ctx = fresh_context()
        result1 = assess_symptoms(symptoms=["headache"], tool_context=ctx)
        assert result1["status"] == "success"
        result2 = assess_symptoms(symptoms=["nausea"], tool_context=ctx)
        assert result2["status"] == "already_called"

    def test_single_vague_symptom(self, fresh_context):
        """A single vague symptom should match but with low confidence."""
        ctx = fresh_context()
        result = assess_symptoms(symptoms=["feeling tired"], tool_context=ctx)
        # May or may not match — but should not crash
        assert result["status"] == "success"
        if result["matches"]:
            assert result["matches"][0]["confidence"] < 80

    def test_symptoms_matching_multiple_severities(self, fresh_context):
        """Mix of emergency + normal symptoms — EMERGENCY should be top."""
        ctx = fresh_context()
        result = assess_symptoms(
            symptoms=["chest pain", "shortness of breath", "runny nose"],
            tool_context=ctx,
        )
        assert result["status"] == "success"
        # Emergency symptoms should rank higher
        if result["matches"]:
            assert result["overall_severity"] in ("EMERGENCY", "URGENT")

    def test_max_3_matches(self, fresh_context):
        """Should never return more than 3 matches."""
        ctx = fresh_context()
        result = assess_symptoms(
            symptoms=["headache", "dizziness", "nausea", "fatigue", "blurry vision"],
            tool_context=ctx,
        )
        assert result["status"] == "success"
        assert len(result["matches"]) <= 3

    def test_precautions_included(self, fresh_context):
        """Matched diseases should have precautions."""
        ctx = fresh_context()
        result = assess_symptoms(
            symptoms=["chest pain", "shortness of breath", "pain in left arm"],
            tool_context=ctx,
        )
        assert result["status"] == "success"
        for match in result["matches"]:
            if match["confidence"] > 20:
                assert len(match["precautions"]) > 0, (
                    f"Disease '{match['disease_name']}' should have precautions"
                )

    def test_emergency_action_message(self, fresh_context):
        """EMERGENCY results should include emergency phone number."""
        ctx = fresh_context()
        result = assess_symptoms(
            symptoms=["sudden severe headache", "face drooping", "arm weakness"],
            tool_context=ctx,
        )
        if result["is_emergency"]:
            assert "123" in result["emergency_action"]

    def test_disclaimer_always_present(self, fresh_context):
        ctx = fresh_context()
        result = assess_symptoms(symptoms=["headache"], tool_context=ctx)
        assert result["status"] == "success"
        assert result["disclaimer"] is not None
        assert len(result["disclaimer"]) > 0

    def test_total_matches_count(self, fresh_context):
        """total_matches should be >= len(matches) (matches is limited to 3)."""
        ctx = fresh_context()
        result = assess_symptoms(
            symptoms=["headache", "dizziness", "nausea", "fatigue"],
            tool_context=ctx,
        )
        assert result["status"] == "success"
        assert result["total_matches"] >= len(result["matches"])

    def test_match_structure(self, fresh_context):
        """Validate all expected fields in each match."""
        ctx = fresh_context()
        result = assess_symptoms(
            symptoms=["chest pain", "shortness of breath"],
            tool_context=ctx,
        )
        assert result["status"] == "success"
        for match in result["matches"]:
            assert "disease_id" in match
            assert "disease_name" in match
            assert "severity" in match
            assert "matched_symptoms" in match
            assert "confidence" in match
            assert "precautions" in match
            assert "is_condition_related" in match


# ===========================================================================
# _fuzzy_symptom_match
# ===========================================================================
class TestFuzzySymptomMatch:
    """Tests for the helper function _fuzzy_symptom_match."""

    def test_exact_match(self):
        assert _fuzzy_symptom_match("headache", "headache") is True

    def test_keyword_overlap(self):
        """Overlapping keywords should match."""
        assert _fuzzy_symptom_match("blurry vision", "vision blurry") is True

    def test_partial_overlap(self):
        assert _fuzzy_symptom_match("severe chest pain", "chest pain") is True

    def test_no_match(self):
        assert _fuzzy_symptom_match("headache", "leg pain") is False

    def test_stop_words_ignored(self):
        """Stop words should not count towards the match."""
        # "the" and "in" are stop words
        result = _fuzzy_symptom_match("pain in the chest", "chest pain")
        assert result is True

    def test_single_word(self):
        assert _fuzzy_symptom_match("nausea", "nausea") is True

    def test_completely_different(self):
        assert _fuzzy_symptom_match("fever", "broken bone") is False


# ===========================================================================
# _condition_relates_to_disease
# ===========================================================================
class TestConditionRelatesToDisease:
    """Tests for the helper function _condition_relates_to_disease."""

    def test_diabetes_related(self):
        assert _condition_relates_to_disease("diabetes", "diabetic complications") is True
        assert _condition_relates_to_disease("diabetes", "blood sugar emergency") is True

    def test_hypertension_related(self):
        assert _condition_relates_to_disease("hypertension", "hypertensive crisis") is True
        assert _condition_relates_to_disease("hypertension", "blood pressure emergency") is True

    def test_heart_disease_related(self):
        assert _condition_relates_to_disease("heart disease", "cardiac arrest") is True

    def test_unrelated(self):
        assert _condition_relates_to_disease("diabetes", "broken bone") is False
        assert _condition_relates_to_disease("arthritis", "heart attack") is False

    def test_unknown_condition(self):
        """Condition not in the map should return False."""
        assert _condition_relates_to_disease("migraine", "heart attack") is False
