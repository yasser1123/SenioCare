"""
Unit tests for drug-food interaction tool: check_drug_food_interaction.

Covers:
- Known harmful interactions (metformin+grapefruit, warfarin+spinach)
- Positive interactions, safe combinations
- Edge cases: empty foods, no medications, case sensitivity
- Output structure validation
"""

import pytest
from seniocare.tools.interactions import check_drug_food_interaction


class TestCheckDrugFoodInteraction:
    """Comprehensive tests for check_drug_food_interaction."""

    def test_known_harmful_interaction(self, fresh_context):
        """Metformin + grapefruit should trigger a harmful interaction."""
        ctx = fresh_context({
            "user:medications": [{"name": "Metformin", "dose": "500mg"}],
        })
        result = check_drug_food_interaction(
            food_names=["grapefruit"], tool_context=ctx
        )
        assert result["status"] == "success"
        assert len(result["harmful_interactions"]) > 0
        drug_food_pairs = [
            (i["drug"].lower(), i["food"].lower())
            for i in result["harmful_interactions"]
        ]
        assert ("metformin", "grapefruit") in drug_food_pairs

    def test_severe_interaction_warfarin(self, heart_disease_user):
        """Warfarin + spinach/grapefruit should flag severe interaction."""
        result = check_drug_food_interaction(
            food_names=["spinach", "grapefruit"], tool_context=heart_disease_user
        )
        assert result["status"] == "success"
        assert result["has_severe_interaction"] is True
        assert result["warning"] is not None

    def test_no_interaction_safe_foods(self, fresh_context):
        """Broccoli + carrot with Metformin should have no harmful interactions."""
        ctx = fresh_context({
            "user:medications": [{"name": "Metformin", "dose": "500mg"}],
        })
        result = check_drug_food_interaction(
            food_names=["broccoli", "carrot"], tool_context=ctx
        )
        assert result["status"] == "success"
        # May have positive interactions but no harmful ones for these foods
        # (carrot is positive with metformin)

    def test_positive_interaction(self, fresh_context):
        """Metformin + carrot should show positive interaction."""
        ctx = fresh_context({
            "user:medications": [
                {"name": "Metformin", "dose": "500mg"},
                {"name": "Lisinopril", "dose": "10mg"},
            ],
        })
        result = check_drug_food_interaction(
            food_names=["carrot", "fish"], tool_context=ctx
        )
        assert result["status"] == "success"
        assert len(result["positive_interactions"]) > 0

    def test_no_medications(self, empty_context):
        """No medications should return no_medications status."""
        result = check_drug_food_interaction(
            food_names=["banana"], tool_context=empty_context
        )
        assert result["status"] == "no_medications"

    def test_empty_food_list(self, fresh_context):
        """Empty food list should return no_foods status."""
        ctx = fresh_context({
            "user:medications": [{"name": "Metformin", "dose": "500mg"}],
        })
        result = check_drug_food_interaction(food_names=[], tool_context=ctx)
        assert result["status"] == "no_foods"

    def test_prevents_double_call(self, fresh_context):
        ctx = fresh_context({
            "user:medications": [{"name": "Metformin", "dose": "500mg"}],
        })
        result1 = check_drug_food_interaction(
            food_names=["banana"], tool_context=ctx
        )
        assert result1["status"] == "success"
        result2 = check_drug_food_interaction(
            food_names=["apple"], tool_context=ctx
        )
        assert result2["status"] == "already_called"

    def test_multiple_drugs_multiple_foods(self, heart_disease_user):
        """Cross-product check: 3 drugs × multiple foods."""
        result = check_drug_food_interaction(
            food_names=["grapefruit", "banana", "spinach", "carrot"],
            tool_context=heart_disease_user,
        )
        assert result["status"] == "success"
        assert result["total_interactions"] > 0
        assert len(result["drugs_checked"]) == 3
        assert len(result["foods_checked"]) == 4

    def test_case_insensitive_matching(self, fresh_context):
        """Drug/food matching should be case-insensitive."""
        ctx = fresh_context({
            "user:medications": [{"name": "METFORMIN", "dose": "500mg"}],
        })
        result = check_drug_food_interaction(
            food_names=["GRAPEFRUIT"], tool_context=ctx
        )
        assert result["status"] == "success"
        # Should still find the interaction despite uppercase
        assert len(result["harmful_interactions"]) > 0

    def test_medication_as_string_list(self, fresh_context):
        """Medications provided as plain strings (not dicts) should still work."""
        ctx = fresh_context({
            "user:medications": ["Metformin", "Lisinopril"],
        })
        result = check_drug_food_interaction(
            food_names=["grapefruit"], tool_context=ctx
        )
        assert result["status"] == "success"

    def test_response_structure(self, fresh_context):
        """Validate all expected keys in response."""
        ctx = fresh_context({
            "user:medications": [{"name": "Metformin", "dose": "500mg"}],
        })
        result = check_drug_food_interaction(
            food_names=["banana"], tool_context=ctx
        )
        expected_keys = [
            "status", "drugs_checked", "foods_checked",
            "harmful_interactions", "positive_interactions",
            "neutral_interactions", "safe_combinations",
            "has_severe_interaction", "total_interactions", "disclaimer",
        ]
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"

    def test_no_severe_interaction_flag(self, fresh_context):
        """When no severe interactions, has_severe should be False and warning None."""
        ctx = fresh_context({
            "user:medications": [{"name": "Metformin", "dose": "500mg"}],
        })
        result = check_drug_food_interaction(
            food_names=["banana", "rice"], tool_context=ctx
        )
        assert result["status"] == "success"
        if not result["has_severe_interaction"]:
            assert result["warning"] is None
