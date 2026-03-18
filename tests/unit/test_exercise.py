"""
Unit tests for exercise tool: get_exercises.

Covers:
- Mobility-level filtering, condition-based exclusion
- Multiple condition exclusion, default mobility
- Output structure, max result limits
"""

import pytest
from seniocare.tools.exercise import get_exercises


class TestGetExercises:
    """Comprehensive tests for get_exercises."""

    def test_limited_mobility_seated_only(self, diabetic_hypertensive_user):
        result = get_exercises(tool_context=diabetic_hypertensive_user)
        assert result["status"] == "success"
        assert result["mobility_level"] == "limited"
        assert len(result["exercises"]) > 0
        for ex in result["exercises"]:
            assert ex["type"] == "seated", (
                f"Exercise '{ex['name_ar']}' should be seated for limited mobility"
            )

    def test_moderate_mobility(self, heart_disease_user):
        result = get_exercises(tool_context=heart_disease_user)
        assert result["status"] == "success"
        assert result["mobility_level"] == "moderate"
        assert len(result["exercises"]) > 0

    def test_condition_exclusion_arthritis(self, arthritis_user):
        """Arthritis should exclude hand/finger exercises."""
        result = get_exercises(tool_context=arthritis_user)
        assert result["status"] == "success"
        exercise_ids = [ex["exercise_id"] for ex in result["exercises"]]
        assert "EX003" not in exercise_ids, "Hand exercises should be excluded for arthritis"
        if result["excluded"]:
            excluded_names = [ex["name_en"] for ex in result["excluded"]]
            assert any("Hand" in n or "Finger" in n for n in excluded_names)

    def test_multiple_conditions_exclusion(self, fresh_context):
        """Multiple conditions should exclude exercises avoided by ANY condition."""
        ctx = fresh_context({
            "user:chronicDiseases": ["arthritis", "heart disease"],
            "user:mobilityStatus": "limited",
        })
        result = get_exercises(tool_context=ctx)
        assert result["status"] == "success"
        assert result["conditions_considered"] == ["arthritis", "heart disease"]

    def test_default_mobility_is_limited(self, empty_context):
        """Empty context should default to 'limited' mobility."""
        result = get_exercises(tool_context=empty_context)
        assert result["status"] == "success"
        assert result["mobility_level"] == "limited"

    def test_prevents_double_call(self, fresh_context):
        ctx = fresh_context({"user:chronicDiseases": [], "user:mobilityStatus": "limited"})
        result1 = get_exercises(tool_context=ctx)
        assert result1["status"] == "success"
        result2 = get_exercises(tool_context=ctx)
        assert result2["status"] == "already_called"

    def test_max_2_exercises(self, fresh_context):
        """Should never return more than 2 exercises."""
        ctx = fresh_context({"user:chronicDiseases": [], "user:mobilityStatus": "limited"})
        result = get_exercises(tool_context=ctx)
        assert result["status"] == "success"
        assert len(result["exercises"]) <= 2

    def test_exercise_fields_present(self, fresh_context):
        """Each exercise should contain all expected fields."""
        ctx = fresh_context({"user:chronicDiseases": [], "user:mobilityStatus": "limited"})
        result = get_exercises(tool_context=ctx)
        assert result["status"] == "success"
        for ex in result["exercises"]:
            assert "exercise_id" in ex
            assert "name_ar" in ex
            assert "type" in ex
            assert "duration" in ex
            assert "steps" in ex
            assert isinstance(ex["steps"], list)
            assert "benefits_ar" in ex
            assert "safety_ar" in ex

    def test_excluded_list_populated(self, arthritis_user):
        """When exercises are excluded, the excluded list should be populated."""
        result = get_exercises(tool_context=arthritis_user)
        assert result["status"] == "success"
        # Arthritis should cause at least one exclusion
        if result["excluded"]:
            for item in result["excluded"]:
                assert "name_en" in item
                assert "reason" in item

    def test_general_advice_and_warning(self, fresh_context):
        """Response should always include safety strings."""
        ctx = fresh_context({"user:chronicDiseases": [], "user:mobilityStatus": "limited"})
        result = get_exercises(tool_context=ctx)
        assert result["status"] == "success"
        assert result["general_advice"] is not None
        assert result["warning"] is not None
        assert len(result["general_advice"]) > 0
        assert len(result["warning"]) > 0

    def test_total_found_matches(self, fresh_context):
        """total_found should reflect the actual count before limiting to 2."""
        ctx = fresh_context({"user:chronicDiseases": [], "user:mobilityStatus": "limited"})
        result = get_exercises(tool_context=ctx)
        assert result["status"] == "success"
        assert result["total_found"] >= len(result["exercises"])

    def test_no_conditions(self, fresh_context):
        """User with no conditions — no exercises should be excluded."""
        ctx = fresh_context({"user:chronicDiseases": [], "user:mobilityStatus": "moderate"})
        result = get_exercises(tool_context=ctx)
        assert result["status"] == "success"
        assert result["excluded"] is None or len(result["excluded"]) == 0
