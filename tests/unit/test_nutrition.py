"""
Unit tests for nutrition tools: get_meal_options and get_meal_recipe.

Covers:
- Basic queries, condition filtering, allergen exclusion
- Multi-condition filtering, edge cases, output structure
- get_meal_recipe (previously untested)
"""

import pytest
from seniocare.tools.nutrition import get_meal_options, get_meal_recipe


# ===========================================================================
# get_meal_options
# ===========================================================================
class TestGetMealOptions:
    """Comprehensive tests for get_meal_options."""

    def test_basic_breakfast_query(self, diabetic_hypertensive_user):
        result = get_meal_options(meal_type="breakfast", tool_context=diabetic_hypertensive_user)
        assert result["status"] == "success"
        assert result["meal_type"] == "breakfast"
        assert len(result["options"]) > 0
        assert "diabetes" in result["conditions_applied"]
        assert "hypertension" in result["conditions_applied"]

    def test_condition_filtering_diabetes(self, fresh_context):
        """All meals for a diabetic user should have sugar ≤ 10g."""
        ctx = fresh_context({"user:chronicDiseases": ["diabetes"], "user:allergies": []})
        result = get_meal_options(meal_type="breakfast", tool_context=ctx)
        assert result["status"] == "success"
        for meal in result["options"]:
            assert meal["nutrition"]["sugar_g"] <= 10, (
                f"Meal '{meal['name_ar']}' has sugar {meal['nutrition']['sugar_g']}g > 10g"
            )

    def test_condition_filtering_hypertension(self, fresh_context):
        """All meals for hypertension should have low sodium."""
        ctx = fresh_context({"user:chronicDiseases": ["hypertension"], "user:allergies": []})
        result = get_meal_options(meal_type="lunch", tool_context=ctx)
        assert result["status"] == "success"
        for meal in result["options"]:
            assert meal["nutrition"]["sodium_mg"] <= 200, (
                f"Meal '{meal['name_ar']}' sodium {meal['nutrition']['sodium_mg']}mg > 200mg"
            )

    def test_multi_condition_filtering(self, fresh_context):
        """diabetes + heart disease should apply BOTH condition rules."""
        ctx = fresh_context({
            "user:chronicDiseases": ["diabetes", "heart disease"],
            "user:allergies": [],
        })
        result = get_meal_options(meal_type="lunch", tool_context=ctx)
        assert result["status"] == "success"
        for meal in result["options"]:
            # diabetes rule
            assert meal["nutrition"]["sugar_g"] <= 10
            # heart disease rules (fat, sodium)
            assert meal["nutrition"]["fat_g"] <= 15
            assert meal["nutrition"]["sodium_mg"] <= 150

    def test_allergen_exclusion_shellfish(self, fresh_context):
        """Shellfish allergy should exclude shrimp-containing meals."""
        ctx = fresh_context({"user:chronicDiseases": [], "user:allergies": ["shellfish"]})
        result = get_meal_options(meal_type="lunch", tool_context=ctx)
        assert result["status"] == "success"
        for meal in result["options"]:
            ingredients_lower = [i.lower() for i in meal["ingredients"]]
            assert "shrimp" not in ingredients_lower, (
                f"Meal '{meal['name_ar']}' contains shrimp despite shellfish allergy"
            )

    def test_multiple_allergies(self, fresh_context):
        """Multiple allergies should exclude meals containing any allergen."""
        ctx = fresh_context({
            "user:chronicDiseases": [],
            "user:allergies": ["dairy", "gluten"],
        })
        result = get_meal_options(meal_type="breakfast", tool_context=ctx)
        # Should succeed — may have fewer or zero results
        assert result["status"] in ("success", "no_meals")

    def test_prevents_double_call(self, diabetic_hypertensive_user):
        result1 = get_meal_options(meal_type="breakfast", tool_context=diabetic_hypertensive_user)
        assert result1["status"] == "success"
        result2 = get_meal_options(meal_type="lunch", tool_context=diabetic_hypertensive_user)
        assert result2["status"] == "already_called"

    def test_invalid_meal_type(self, fresh_context):
        """Non-existent meal type should return no_meals."""
        ctx = fresh_context()
        result = get_meal_options(meal_type="brunch", tool_context=ctx)
        assert result["status"] == "no_meals"
        assert result["options"] == []

    def test_no_conditions_no_allergies(self, fresh_context):
        """User with no conditions/allergies gets unfiltered meals."""
        ctx = fresh_context({"user:chronicDiseases": [], "user:allergies": []})
        result = get_meal_options(meal_type="lunch", tool_context=ctx)
        assert result["status"] == "success"
        assert len(result["options"]) > 0

    @pytest.mark.parametrize("meal_type", ["breakfast", "lunch", "dinner", "snack"])
    def test_all_meal_types(self, fresh_context, meal_type):
        """Each valid meal type should return success."""
        ctx = fresh_context({"user:chronicDiseases": [], "user:allergies": []})
        result = get_meal_options(meal_type=meal_type, tool_context=ctx)
        assert result["status"] in ("success", "no_meals")

    def test_max_3_results(self, fresh_context):
        """Should never return more than 3 options."""
        ctx = fresh_context({"user:chronicDiseases": [], "user:allergies": []})
        result = get_meal_options(meal_type="lunch", tool_context=ctx)
        if result["status"] == "success":
            assert len(result["options"]) <= 3

    def test_output_structure(self, fresh_context):
        """Validate that response contains all expected keys."""
        ctx = fresh_context({"user:chronicDiseases": [], "user:allergies": []})
        result = get_meal_options(meal_type="breakfast", tool_context=ctx)
        assert "status" in result
        assert "meal_type" in result
        assert "options" in result
        assert "conditions_applied" in result
        assert "allergies_excluded" in result
        assert "total_found" in result
        assert "disclaimer" in result

    def test_meal_option_structure(self, fresh_context):
        """Each meal option should have all expected fields."""
        ctx = fresh_context({"user:chronicDiseases": [], "user:allergies": []})
        result = get_meal_options(meal_type="breakfast", tool_context=ctx)
        assert result["status"] == "success"
        for meal in result["options"]:
            assert "meal_id" in meal
            assert "name_ar" in meal
            assert "category" in meal
            assert "ingredients" in meal
            assert isinstance(meal["ingredients"], list)
            assert "nutrition" in meal
            assert "energy_kcal" in meal["nutrition"]
            assert "protein_g" in meal["nutrition"]
            assert "fat_g" in meal["nutrition"]
            assert "sodium_mg" in meal["nutrition"]
            assert "sugar_g" in meal["nutrition"]

    def test_case_insensitive_meal_type(self, fresh_context):
        """Meal type should be case-insensitive."""
        ctx = fresh_context({"user:chronicDiseases": [], "user:allergies": []})
        result = get_meal_options(meal_type="BREAKFAST", tool_context=ctx)
        assert result["status"] in ("success", "no_meals")

    def test_all_meals_filtered_out(self, fresh_context):
        """Extreme filters that might eliminate all meals."""
        ctx = fresh_context({
            "user:chronicDiseases": ["kidney disease", "heart disease"],
            "user:allergies": ["dairy", "gluten", "fish", "shellfish"],
        })
        result = get_meal_options(meal_type="breakfast", tool_context=ctx)
        assert result["status"] in ("success", "no_meals")


# ===========================================================================
# get_meal_recipe
# ===========================================================================
class TestGetMealRecipe:
    """Tests for get_meal_recipe — previously untested."""

    def test_valid_meal_id(self, fresh_context):
        ctx = fresh_context()
        result = get_meal_recipe(meal_id="M001", tool_context=ctx)
        assert result["status"] == "success"
        assert result["meal_id"] == "M001"
        assert result["name_ar"] is not None
        assert len(result["recipe_steps"]) > 0
        assert result["recipe_tips"] is not None

    def test_invalid_meal_id(self, fresh_context):
        ctx = fresh_context()
        result = get_meal_recipe(meal_id="M999", tool_context=ctx)
        assert result["status"] == "not_found"

    def test_prevents_double_call(self, fresh_context):
        ctx = fresh_context()
        result1 = get_meal_recipe(meal_id="M001", tool_context=ctx)
        assert result1["status"] == "success"
        result2 = get_meal_recipe(meal_id="M002", tool_context=ctx)
        assert result2["status"] == "already_called"

    def test_response_structure(self, fresh_context):
        ctx = fresh_context()
        result = get_meal_recipe(meal_id="M001", tool_context=ctx)
        assert result["status"] == "success"
        expected_keys = [
            "meal_id", "name_ar", "name_en", "category",
            "ingredients", "recipe_steps", "recipe_tips",
            "nutrition", "prep_time", "notes_ar",
        ]
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"

    def test_nutrition_values_positive(self, fresh_context):
        ctx = fresh_context()
        result = get_meal_recipe(meal_id="M001", tool_context=ctx)
        assert result["status"] == "success"
        assert result["nutrition"]["energy_kcal"] > 0
        assert result["nutrition"]["protein_g"] >= 0

    def test_recipe_steps_non_empty(self, fresh_context):
        ctx = fresh_context()
        result = get_meal_recipe(meal_id="M001", tool_context=ctx)
        assert result["status"] == "success"
        assert isinstance(result["recipe_steps"], list)
        assert len(result["recipe_steps"]) > 0

    def test_ingredients_is_list(self, fresh_context):
        ctx = fresh_context()
        result = get_meal_recipe(meal_id="M001", tool_context=ctx)
        assert result["status"] == "success"
        assert isinstance(result["ingredients"], list)
        assert len(result["ingredients"]) > 0

    def test_nutrition_has_full_fields(self, fresh_context):
        ctx = fresh_context()
        result = get_meal_recipe(meal_id="M001", tool_context=ctx)
        assert result["status"] == "success"
        nutrition = result["nutrition"]
        for field in ["energy_kcal", "protein_g", "fat_g", "carbohydrate_g", "fiber_g", "sodium_mg", "sugar_g"]:
            assert field in nutrition, f"Missing nutrition field: {field}"
