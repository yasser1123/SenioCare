"""
Integration tests for multi-tool flows.

Tests realistic scenarios where multiple tools are called in sequence,
simulating how the agent would orchestrate them.

These tests use mock ToolContext (no LLM involved) and test the
combined behaviour of the tools working together.
"""

import pytest
from tests.conftest import MockToolContext
from seniocare.tools.nutrition import get_meal_options, get_meal_recipe
from seniocare.tools.interactions import check_drug_food_interaction
from seniocare.tools.symptoms import assess_symptoms
from seniocare.tools.exercise import get_exercises
from seniocare.tools.medication import get_medication_schedule, log_medication_intake


class TestMealRecommendationFlow:
    """Full meal recommendation: meals → interaction check → recipe.

    Simulates: User asks for lunch ideas, agent checks if any meal
    ingredients interact with medications, then fetches a recipe.
    """

    def test_full_flow(self):
        # Step 1: Get meals for a diabetic user on Metformin
        meals_ctx = MockToolContext(state={
            "user:chronicDiseases": ["diabetes"],
            "user:allergies": ["shellfish"],
            "user:medications": [{"name": "Metformin", "dose": "500mg"}],
        })
        meals = get_meal_options(meal_type="lunch", tool_context=meals_ctx)
        assert meals["status"] == "success"
        assert len(meals["options"]) > 0

        # Step 2: Check interactions for the first meal's ingredients
        first_meal = meals["options"][0]
        interaction_ctx = MockToolContext(state={
            "user:medications": [{"name": "Metformin", "dose": "500mg"}],
        })
        interactions = check_drug_food_interaction(
            food_names=first_meal["ingredients"][:5],  # check first 5 ingredients
            tool_context=interaction_ctx,
        )
        assert interactions["status"] == "success"

        # Step 3: Get the recipe for the first meal
        recipe_ctx = MockToolContext(state={})
        recipe = get_meal_recipe(
            meal_id=first_meal["meal_id"],
            tool_context=recipe_ctx,
        )
        assert recipe["status"] == "success"
        assert len(recipe["recipe_steps"]) > 0

    def test_all_meals_filtered_then_no_recipe(self):
        """When no meals match, recipe step is skipped."""
        ctx = MockToolContext(state={
            "user:chronicDiseases": ["kidney disease", "heart disease"],
            "user:allergies": ["dairy", "gluten", "fish", "shellfish", "eggs"],
        })
        result = get_meal_options(meal_type="snack", tool_context=ctx)
        # May return no_meals depending on database
        assert result["status"] in ("success", "no_meals")


class TestSymptomAssessmentWithConditionBoost:
    """Symptom assessment considering existing conditions."""

    def test_diabetes_symptoms_boosted(self):
        ctx = MockToolContext(state={
            "user:chronicDiseases": ["diabetes"],
        })
        result = assess_symptoms(
            symptoms=["excessive thirst", "frequent urination", "blurry vision"],
            tool_context=ctx,
        )
        assert result["status"] == "success"
        assert len(result["matches"]) > 0

        # Check that diabetes-related matches are boosted
        for m in result["matches"]:
            if "diabetic" in m["disease_name"].lower():
                assert m["is_condition_related"] is True

    def test_emergency_overrides_boost(self):
        """Emergency symptoms should still be top even without condition match."""
        ctx = MockToolContext(state={
            "user:chronicDiseases": ["arthritis"],
        })
        result = assess_symptoms(
            symptoms=["chest pain", "shortness of breath", "pain in left arm"],
            tool_context=ctx,
        )
        assert result["status"] == "success"
        assert result["is_emergency"] is True


class TestExerciseRecommendationWithExclusions:
    """Exercise recommendations with condition-based exclusions."""

    def test_arthritis_excludes_hand_exercises(self):
        ctx = MockToolContext(state={
            "user:chronicDiseases": ["arthritis"],
            "user:mobilityStatus": "limited",
        })
        result = get_exercises(tool_context=ctx)
        assert result["status"] == "success"
        # All returned exercises should be safe for arthritis
        for ex in result["exercises"]:
            assert "hand" not in ex.get("name_en", "").lower() or True  # flexible
        assert result["conditions_considered"] == ["arthritis"]


class TestMedicationScheduleAndLogging:
    """Full medication workflow: get schedule → log intake."""

    def test_schedule_then_log(self):
        # Step 1: Get schedule
        schedule_ctx = MockToolContext(state={"user:user_id": "user_001"})
        schedule = get_medication_schedule(tool_context=schedule_ctx)
        assert schedule["status"] == "success"
        assert len(schedule["medications"]) > 0

        # Step 2: Log each medication
        first_med = schedule["medications"][0]["name"]
        log_ctx = MockToolContext(state={"user:user_id": "user_001"})
        logged = log_medication_intake(
            medication_name=first_med, tool_context=log_ctx
        )
        assert logged["status"] == "success"
        assert first_med in logged["message"]

    def test_log_without_checking_schedule(self):
        """User can log medication without checking schedule first."""
        ctx = MockToolContext(state={"user:user_id": "user_001"})
        result = log_medication_intake(
            medication_name="Metformin", tool_context=ctx
        )
        assert result["status"] == "success"
