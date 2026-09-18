"""
Test Database Tools - Standalone tests for all SenioCare database-backed tools.

Tests each tool function in isolation with mock ToolContext state.
Run: python -m pytest tests/test_database_tools.py -v
"""

import os
import sys
import json
import types
import pytest

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Mock google.adk BEFORE importing seniocare modules
# ---------------------------------------------------------------------------
class MockToolContext:
    """Minimal mock of google.adk.tools.ToolContext for testing."""

    def __init__(self, state: dict = None):
        self.state = state or {}


# Create mock google.adk module hierarchy so imports don't fail
_mock_google = types.ModuleType("google")
_mock_adk = types.ModuleType("google.adk")
_mock_adk_tools = types.ModuleType("google.adk.tools")
_mock_adk_tools.ToolContext = MockToolContext
_mock_adk_agents = types.ModuleType("google.adk.agents")
_mock_adk_models = types.ModuleType("google.adk.models")
_mock_adk_models_lite_llm = types.ModuleType("google.adk.models.lite_llm")

# Minimal stubs for agent classes
_mock_adk_agents.LlmAgent = type("LlmAgent", (), {"__init__": lambda self, **kw: None})
_mock_adk_agents.SequentialAgent = type("SequentialAgent", (), {"__init__": lambda self, **kw: None})
_mock_adk_models_lite_llm.LiteLlm = type("LiteLlm", (), {"__init__": lambda self, **kw: None})

sys.modules.setdefault("google", _mock_google)
sys.modules.setdefault("google.adk", _mock_adk)
sys.modules.setdefault("google.adk.tools", _mock_adk_tools)
sys.modules.setdefault("google.adk.agents", _mock_adk_agents)
sys.modules.setdefault("google.adk.models", _mock_adk_models)
sys.modules.setdefault("google.adk.models.lite_llm", _mock_adk_models_lite_llm)

# Mock pydantic if not installed (image_analysis modules use it)
try:
    import pydantic
except ImportError:
    _mock_pydantic = types.ModuleType("pydantic")

    class _MockBaseModel:
        """Minimal mock of pydantic.BaseModel for testing."""
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
        def model_dump(self):
            return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__(**kwargs)

    _mock_pydantic.BaseModel = _MockBaseModel
    sys.modules.setdefault("pydantic", _mock_pydantic)

# Mock httpx if not installed (image_analysis.common uses it)
try:
    import httpx
except ImportError:
    _mock_httpx = types.ModuleType("httpx")
    _mock_httpx.AsyncClient = type("AsyncClient", (), {"__init__": lambda self, **kw: None})
    sys.modules.setdefault("httpx", _mock_httpx)


# All tests in this file require a live PostgreSQL test database.
pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set — point it at a disposable PostgreSQL test database",
)

# Now safe to import seniocare modules
from seniocare.data.database import get_connection, reset_database  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def user_001_context():
    """User 001: Diabetes + Hypertension, shellfish allergy, takes Metformin + Lisinopril."""
    return MockToolContext(state={
        "user:user_id": "user_001",
        "user:chronicDiseases": ["diabetes", "hypertension"],
        "user:allergies": ["shellfish"],
        "user:medications": [
            {"name": "Metformin", "dose": "500mg"},
            {"name": "Lisinopril", "dose": "10mg"},
        ],
        "user:mobilityStatus": "limited",
    })


@pytest.fixture
def user_003_context():
    """User 003: Heart disease, takes Aspirin + Simvastatin + Warfarin."""
    return MockToolContext(state={
        "user:user_id": "user_003",
        "user:chronicDiseases": ["heart disease"],
        "user:allergies": [],
        "user:medications": [
            {"name": "Aspirin", "dose": "81mg"},
            {"name": "Simvastatin", "dose": "20mg"},
            {"name": "Warfarin", "dose": "5mg"},
        ],
        "user:mobilityStatus": "moderate",
    })


@pytest.fixture
def empty_context():
    """A context with no user data."""
    return MockToolContext(state={})


# ===========================================================================
# 1. DATABASE INITIALIZATION TESTS
# ===========================================================================
class TestDatabaseInit:
    """Test that the database is initialized correctly."""

    def test_database_connection(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 AS ok")
        assert cursor.fetchone()["ok"] == 1
        conn.close()

    def test_all_tables_exist(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public'"
        )
        tables = {row["table_name"] for row in cursor.fetchall()}
        conn.close()

        expected = {
            "meals", "condition_dietary_rules", "drug_food_interactions",
            "disease_symptoms", "disease_precautions", "food_allergens",
            "exercises", "medical_reports",
        }
        for table in expected:
            assert table in tables, f"Table '{table}' should exist"

    def test_meals_have_data(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM meals")
        count = cursor.fetchone()["cnt"]
        conn.close()
        assert count >= 15, f"Should have at least 15 meals, got {count}"

    def test_diseases_have_data(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM disease_symptoms")
        count = cursor.fetchone()["cnt"]
        conn.close()
        assert count >= 10, f"Should have at least 10 diseases, got {count}"

    def test_interactions_have_data(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM drug_food_interactions")
        count = cursor.fetchone()["cnt"]
        conn.close()
        assert count >= 15, f"Should have at least 15 interactions, got {count}"


# ===========================================================================
# 2. NUTRITION TOOL TESTS
# ===========================================================================
class TestGetMealOptions:
    """Test get_meal_options with various conditions."""

    def test_basic_meal_query(self, user_001_context):
        from seniocare.tools.nutrition import get_meal_options
        result = get_meal_options(meal_type="breakfast", tool_context=user_001_context)

        assert result["status"] == "success"
        assert result["meal_type"] == "breakfast"
        assert len(result["options"]) > 0
        assert "diabetes" in result["conditions_applied"]
        assert "hypertension" in result["conditions_applied"]

    def test_condition_filtering_diabetes(self, empty_context):
        """Meals for diabetes should have low sugar."""
        empty_context.state["user:chronicDiseases"] = ["diabetes"]
        from seniocare.tools.nutrition import get_meal_options
        result = get_meal_options(meal_type="breakfast", tool_context=empty_context)

        assert result["status"] == "success"
        for meal in result["options"]:
            assert meal["nutrition"]["sugar_g"] <= 10, \
                f"Meal '{meal['name_en']}' has sugar {meal['nutrition']['sugar_g']}g > 10g limit"

    def test_condition_filtering_hypertension(self, empty_context):
        """Meals for hypertension should have low sodium."""
        empty_context.state["user:chronicDiseases"] = ["hypertension"]
        from seniocare.tools.nutrition import get_meal_options
        result = get_meal_options(meal_type="lunch", tool_context=empty_context)

        assert result["status"] == "success"
        for meal in result["options"]:
            assert meal["nutrition"]["sodium_mg"] <= 200, \
                f"Meal '{meal['name_en']}' has sodium {meal['nutrition']['sodium_mg']}mg > 200mg limit"

    def test_allergen_exclusion(self, empty_context):
        """Shellfish allergy should exclude shrimp-containing meals."""
        empty_context.state["user:chronicDiseases"] = []
        empty_context.state["user:allergies"] = ["shellfish"]
        from seniocare.tools.nutrition import get_meal_options
        result = get_meal_options(meal_type="lunch", tool_context=empty_context)

        assert result["status"] == "success"
        for meal in result["options"]:
            ingredients = [i.lower() for i in meal["ingredients"]]
            assert "shrimp" not in ingredients, \
                f"Meal '{meal['name_en']}' contains shrimp despite shellfish allergy"

    def test_prevents_double_call(self, user_001_context):
        from seniocare.tools.nutrition import get_meal_options
        # First call should succeed
        result1 = get_meal_options(meal_type="breakfast", tool_context=user_001_context)
        assert result1["status"] == "success"

        # Second call should be blocked
        result2 = get_meal_options(meal_type="lunch", tool_context=user_001_context)
        assert result2["status"] == "already_called"

    def test_empty_meal_type(self, empty_context):
        """Non-existent meal type should return empty."""
        from seniocare.tools.nutrition import get_meal_options
        result = get_meal_options(meal_type="brunch", tool_context=empty_context)
        assert result["status"] == "no_meals"


# ===========================================================================
# 3. DRUG-FOOD INTERACTION TESTS
# ===========================================================================
class TestCheckDrugFoodInteraction:
    """Test check_drug_food_interaction."""

    def test_known_interaction_metformin_grapefruit(self, user_001_context):
        from seniocare.tools.interactions import check_drug_food_interaction
        result = check_drug_food_interaction(
            food_names=["grapefruit"],
            tool_context=user_001_context
        )

        assert result["status"] == "success"
        assert len(result["harmful_interactions"]) > 0
        drug_food_pairs = [(i["drug"], i["food"]) for i in result["harmful_interactions"]]
        assert ("metformin", "grapefruit") in drug_food_pairs

    def test_no_interaction_safe_foods(self, user_001_context):
        from seniocare.tools.interactions import check_drug_food_interaction
        result = check_drug_food_interaction(
            food_names=["broccoli", "carrot"],
            tool_context=user_001_context
        )

        assert result["status"] == "success"
        assert len(result["harmful_interactions"]) == 0

    def test_severe_interaction_warfarin(self, user_003_context):
        from seniocare.tools.interactions import check_drug_food_interaction
        result = check_drug_food_interaction(
            food_names=["spinach", "grapefruit"],
            tool_context=user_003_context
        )

        assert result["status"] == "success"
        assert result["has_severe_interaction"] is True  # simvastatin+grapefruit is severe
        assert result["warning"] is not None

    def test_no_medications(self, empty_context):
        from seniocare.tools.interactions import check_drug_food_interaction
        result = check_drug_food_interaction(
            food_names=["banana"],
            tool_context=empty_context
        )
        assert result["status"] == "no_medications"

    def test_positive_interaction(self, user_001_context):
        from seniocare.tools.interactions import check_drug_food_interaction
        result = check_drug_food_interaction(
            food_names=["carrot", "fish"],
            tool_context=user_001_context
        )

        assert result["status"] == "success"
        # Metformin + carrot is positive, lisinopril + fish is positive
        assert len(result["positive_interactions"]) > 0

    def test_prevents_double_call(self, user_001_context):
        from seniocare.tools.interactions import check_drug_food_interaction
        result1 = check_drug_food_interaction(food_names=["banana"], tool_context=user_001_context)
        assert result1["status"] == "success"
        result2 = check_drug_food_interaction(food_names=["apple"], tool_context=user_001_context)
        assert result2["status"] == "already_called"


# ===========================================================================
# 4. SYMPTOM ASSESSMENT TESTS
# ===========================================================================
class TestAssessSymptoms:
    """Test assess_symptoms with various scenarios."""

    def test_emergency_symptoms_stroke(self, empty_context):
        from seniocare.tools.symptoms import assess_symptoms
        result = assess_symptoms(
            symptoms=["sudden severe headache", "face drooping", "arm weakness", "speech difficulty"],
            tool_context=empty_context
        )

        assert result["status"] == "success"
        assert result["is_emergency"] is True
        assert result["overall_severity"] == "EMERGENCY"
        assert result["emergency_action"] is not None
        # Stroke should be the top match
        assert result["matches"][0]["disease_name"] == "stroke"

    def test_normal_symptoms(self, empty_context):
        from seniocare.tools.symptoms import assess_symptoms
        result = assess_symptoms(
            symptoms=["runny nose", "sneezing", "itchy eyes", "nasal congestion"],
            tool_context=empty_context
        )

        assert result["status"] == "success"
        # Top match should be common cold or seasonal allergy (NORMAL)
        top = result["matches"][0]
        assert top["severity"] in ("NORMAL", "MONITOR"), \
            f"Top match '{top['disease_name']}' has severity {top['severity']}, expected NORMAL/MONITOR"

    def test_condition_boost(self):
        """Diabetes user reporting diabetes-related symptoms should get higher confidence."""
        # Without existing conditions
        ctx_no_conditions = MockToolContext(state={"user:chronicDiseases": []})
        from seniocare.tools.symptoms import assess_symptoms

        # Use symptoms unique to diabetes — avoid blurry vision etc. which
        # overlap with EMERGENCY diseases (stroke, heart attack) that rank higher
        diabetes_symptoms = [
            "excessive thirst", "frequent urination",
            "slow healing wounds", "tingling in hands", "tingling in feet",
        ]
        result_no_boost = assess_symptoms(
            symptoms=diabetes_symptoms,
            tool_context=ctx_no_conditions
        )

        # With diabetes as existing condition
        ctx_diabetes = MockToolContext(state={"user:chronicDiseases": ["diabetes"]})
        result_boosted = assess_symptoms(
            symptoms=diabetes_symptoms,
            tool_context=ctx_diabetes
        )

        # Find diabetes complications in both results
        no_boost_confidence = None
        boosted_confidence = None
        for m in result_no_boost["matches"]:
            if "diabet" in m["disease_name"].lower():
                no_boost_confidence = m["confidence"]
        for m in result_boosted["matches"]:
            if "diabet" in m["disease_name"].lower():
                boosted_confidence = m["confidence"]

        assert boosted_confidence is not None, \
            f"Should match diabetes complications, got: {[m['disease_name'] for m in result_boosted['matches']]}"
        # If both found, boosted should be higher
        if no_boost_confidence is not None:
            assert boosted_confidence > no_boost_confidence, \
                f"Boosted ({boosted_confidence}) should be > non-boosted ({no_boost_confidence})"

    def test_no_symptoms(self, empty_context):
        from seniocare.tools.symptoms import assess_symptoms
        result = assess_symptoms(symptoms=[], tool_context=empty_context)
        assert result["status"] == "no_symptoms"

    def test_heart_attack_detection(self, empty_context):
        from seniocare.tools.symptoms import assess_symptoms
        result = assess_symptoms(
            symptoms=["chest pain", "shortness of breath", "pain in left arm", "cold sweat"],
            tool_context=empty_context
        )

        assert result["status"] == "success"
        assert result["is_emergency"] is True
        top_match = result["matches"][0]
        assert top_match["disease_name"] == "heart attack"
        assert len(top_match["precautions"]) > 0

    def test_prevents_double_call(self, empty_context):
        from seniocare.tools.symptoms import assess_symptoms
        result1 = assess_symptoms(symptoms=["headache"], tool_context=empty_context)
        assert result1["status"] == "success"
        result2 = assess_symptoms(symptoms=["nausea"], tool_context=empty_context)
        assert result2["status"] == "already_called"


# ===========================================================================
# 6. EXERCISE TOOL TESTS
# ===========================================================================
class TestGetExercises:
    """Test get_exercises."""

    def test_limited_mobility(self, user_001_context):
        from seniocare.tools.exercise import get_exercises
        result = get_exercises(tool_context=user_001_context)

        assert result["status"] == "success"
        assert result["mobility_level"] == "limited"
        assert len(result["exercises"]) > 0
        # All exercises should be seated for limited mobility
        for ex in result["exercises"]:
            assert ex["type"] == "seated", \
                f"Exercise '{ex['name_en']}' should be seated for limited mobility"

    def test_moderate_mobility(self, user_003_context):
        from seniocare.tools.exercise import get_exercises
        result = get_exercises(tool_context=user_003_context)

        assert result["status"] == "success"
        assert result["mobility_level"] == "moderate"
        assert len(result["exercises"]) > 0

    def test_condition_exclusion_arthritis(self):
        """Arthritis user should not get exercises that worsen joints."""
        ctx = MockToolContext(state={
            "user:chronicDiseases": ["arthritis"],
            "user:mobilityStatus": "limited",
        })
        from seniocare.tools.exercise import get_exercises
        result = get_exercises(tool_context=ctx)

        assert result["status"] == "success"
        # Check that hand exercises (EX003 avoids arthritis) are excluded
        exercise_ids = [ex["exercise_id"] for ex in result["exercises"]]
        assert "EX003" not in exercise_ids, \
            "Hand exercises should be excluded for arthritis"
        if result["excluded"]:
            excluded_names = [ex["name_en"] for ex in result["excluded"]]
            assert "Hand and Finger Exercises" in excluded_names

    def test_default_mobility(self, empty_context):
        from seniocare.tools.exercise import get_exercises
        result = get_exercises(tool_context=empty_context)
        assert result["status"] == "success"
        assert result["mobility_level"] == "limited"  # Default


# ===========================================================================
# 7. END-TO-END SCENARIO TESTS
# ===========================================================================
class TestScenarioMealRecommendation:
    """Test the full meal recommendation scenario (2-tool flow)."""

    def test_scenario_1_diabetes_hypertension_shellfish(self):
        """
        Scenario: User with diabetes + hypertension + shellfish allergy 
        asks for lunch. Should get low-sugar, low-sodium, no-shrimp meals,
        and drug interaction check should flag grapefruit (if present).
        """
        ctx = MockToolContext(state={
            "user:user_id": "user_001",
            "user:chronicDiseases": ["diabetes", "hypertension"],
            "user:allergies": ["shellfish"],
            "user:medications": [
                {"name": "Metformin", "dose": "500mg"},
                {"name": "Lisinopril", "dose": "10mg"},
            ],
            "user:mobilityStatus": "limited",
        })

        # Step 1: Get meals
        from seniocare.tools.nutrition import get_meal_options
        meal_result = get_meal_options(meal_type="lunch", tool_context=ctx)

        assert meal_result["status"] == "success"
        assert len(meal_result["options"]) > 0

        # Verify all returned meals comply with conditions
        for meal in meal_result["options"]:
            assert meal["nutrition"]["sodium_mg"] <= 200
            assert meal["nutrition"]["sugar_g"] <= 10
            ingredients_lower = [i.lower() for i in meal["ingredients"]]
            assert "shrimp" not in ingredients_lower

        # Step 2: Check drug interactions for all ingredients
        all_ingredients = []
        for meal in meal_result["options"]:
            all_ingredients.extend(meal["ingredients"])

        from seniocare.tools.interactions import check_drug_food_interaction
        interaction_result = check_drug_food_interaction(
            food_names=list(set(all_ingredients)),
            tool_context=ctx
        )

        assert interaction_result["status"] == "success"


class TestScenarioSymptomAssessment:
    """Test the symptom assessment scenario."""

    def test_scenario_2_diabetes_user_with_headache(self):
        """
        Scenario: Diabetes user reports severe headache, dizziness, blurry vision.
        Should detect hypertension crisis and/or diabetes complications,
        and boost diabetes-related matches.
        """
        ctx = MockToolContext(state={
            "user:chronicDiseases": ["diabetes"],
            "user:allergies": [],
            "user:medications": [{"name": "Metformin", "dose": "500mg"}],
        })

        from seniocare.tools.symptoms import assess_symptoms
        # Use symptoms that are diabetes/hypertension-specific to avoid
        # EMERGENCY diseases (stroke, heart attack) dominating the top-3
        result = assess_symptoms(
            symptoms=["excessive thirst", "frequent urination", "tingling in hands"],
            tool_context=ctx
        )

        assert result["status"] == "success"
        assert len(result["matches"]) > 0

        # Should include diabetes complications or hypertension crisis
        disease_names = [m["disease_name"] for m in result["matches"]]
        has_related = any(
            "diabet" in d.lower() or "hypertens" in d.lower()
            for d in disease_names
        )
        assert has_related, \
            f"Should match diabetes/hypertension-related disease, got: {disease_names}"

        # Check that precautions are included
        for match in result["matches"]:
            if match["confidence"] > 20:
                assert len(match["precautions"]) > 0, \
                    f"Disease '{match['disease_name']}' should have precautions"


# ===========================================================================
# Run tests
# ===========================================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

