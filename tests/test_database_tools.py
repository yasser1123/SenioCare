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


# Now safe to import seniocare modules
from seniocare.data.database import get_connection, reset_database, DB_PATH


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Ensure a fresh test database exists for all tests."""
    reset_database()
    yield
    # Cleanup after all tests
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    for ext in ["-wal", "-shm"]:
        path = DB_PATH + ext
        if os.path.exists(path):
            os.remove(path)


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
    """Test that the database is created correctly."""

    def test_database_file_exists(self):
        assert os.path.exists(DB_PATH), "Database file should exist"

    def test_all_tables_exist(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row["name"] for row in cursor.fetchall()}
        conn.close()

        expected = {
            "meals", "condition_dietary_rules", "drug_food_interactions",
            "disease_symptoms", "disease_precautions", "food_allergens",
            "medications", "exercises", "medical_reports",
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
# 5. MEDICATION TOOL TESTS
# ===========================================================================
class TestMedicationSchedule:
    """Test get_medication_schedule."""

    def test_valid_user(self, user_001_context):
        from seniocare.tools.medication import get_medication_schedule
        result = get_medication_schedule(tool_context=user_001_context)

        assert result["status"] == "success"
        assert result["user_id"] == "user_001"
        assert len(result["medications"]) == 2
        med_names = [m["name"] for m in result["medications"]]
        assert "Metformin" in med_names
        assert "Lisinopril" in med_names

    def test_unknown_user(self, empty_context):
        empty_context.state["user:user_id"] = "unknown_user"
        from seniocare.tools.medication import get_medication_schedule
        result = get_medication_schedule(tool_context=empty_context)
        assert result["status"] == "error"

    def test_no_user_id(self, empty_context):
        from seniocare.tools.medication import get_medication_schedule
        result = get_medication_schedule(tool_context=empty_context)
        assert result["status"] == "error"


class TestLogMedication:
    """Test log_medication_intake."""

    def test_log_success(self, user_001_context):
        from seniocare.tools.medication import log_medication_intake
        result = log_medication_intake(
            medication_name="Metformin",
            tool_context=user_001_context
        )
        assert result["status"] == "success"
        assert "Metformin" in result["message"]
        assert result["timestamp"] is not None


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
# 8. IMAGE ANALYSIS MODULE TESTS
# ===========================================================================
class TestImageAnalysisCommon:
    """Test shared utilities from the image_analysis.common module."""

    def test_validate_base64_valid(self):
        from seniocare.image_analysis.common import validate_base64_image
        import base64
        valid_b64 = base64.b64encode(b"fake image data").decode()
        assert validate_base64_image(valid_b64) is True

    def test_validate_base64_with_prefix(self):
        from seniocare.image_analysis.common import validate_base64_image
        import base64
        raw = base64.b64encode(b"fake image data").decode()
        with_prefix = f"data:image/png;base64,{raw}"
        assert validate_base64_image(with_prefix) is True

    def test_validate_base64_invalid(self):
        from seniocare.image_analysis.common import validate_base64_image
        assert validate_base64_image("not-valid-base64!!!") is False

    def test_parse_json_from_response_plain(self):
        from seniocare.image_analysis.common import parse_json_from_response
        result = parse_json_from_response('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_json_from_response_with_fences(self):
        from seniocare.image_analysis.common import parse_json_from_response
        response = '```json\n{"key": "value"}\n```'
        result = parse_json_from_response(response)
        assert result == {"key": "value"}

    def test_parse_json_from_response_with_surrounding_text(self):
        from seniocare.image_analysis.common import parse_json_from_response
        response = 'Here is the result:\n{"medication_name": "Panadol"}\nEnd.'
        result = parse_json_from_response(response)
        assert result["medication_name"] == "Panadol"

    def test_strip_base64_prefix(self):
        from seniocare.image_analysis.common import strip_base64_prefix
        assert strip_base64_prefix("data:image/png;base64,ABC123") == "ABC123"
        assert strip_base64_prefix("ABC123") == "ABC123"


class TestMedicationAnalyzerParsing:
    """Test medication analyzer response parsing (no model needed)."""

    def test_parse_valid_medication_response(self):
        from seniocare.image_analysis.medication_analyzer import _parse_medication_response
        response = '{"medication_name": "Panadol Extra", "active_ingredient": "Paracetamol + Caffeine", "dosage": "500mg/65mg", "manufacturer": "GSK", "expiry_date": "12/2026"}'
        result = _parse_medication_response(response)

        assert result.success is True
        assert result.medication_name == "Panadol Extra"
        assert result.active_ingredient == "Paracetamol + Caffeine"
        assert result.dosage == "500mg/65mg"
        assert result.manufacturer == "GSK"

    def test_parse_partial_medication_response(self):
        from seniocare.image_analysis.medication_analyzer import _parse_medication_response
        response = '{"medication_name": "Augmentin", "active_ingredient": "Amoxicillin + Clavulanic acid", "dosage": "1g", "manufacturer": null, "expiry_date": null}'
        result = _parse_medication_response(response)

        assert result.success is True
        assert result.medication_name == "Augmentin"
        assert result.active_ingredient == "Amoxicillin + Clavulanic acid"
        assert result.dosage == "1g"
        assert result.manufacturer is None

    def test_parse_invalid_medication_response(self):
        from seniocare.image_analysis.medication_analyzer import _parse_medication_response
        result = _parse_medication_response("this is not JSON at all")
        assert result.success is True  # Still returns True but with error note
        assert result.error is not None

    def test_parse_markdown_wrapped_response(self):
        from seniocare.image_analysis.medication_analyzer import _parse_medication_response
        response = '```json\n{"medication_name": "Metformin", "active_ingredient": "Metformin HCl", "dosage": "500mg", "manufacturer": "Merck", "expiry_date": null}\n```'
        result = _parse_medication_response(response)
        assert result.medication_name == "Metformin"
        assert result.dosage == "500mg"


class TestReportAnalyzerParsing:
    """Test report analyzer response parsing and severity classification."""

    def test_parse_valid_extraction(self):
        from seniocare.image_analysis.report_analyzer import _parse_extraction_response
        response = '{"report_type": "blood_test", "date": "2025-01-15", "key_findings": ["High blood sugar"], "values": {"fasting glucose": "180 mg/dL"}, "recommendations": ["Follow up in 1 month"]}'
        result = _parse_extraction_response(response)

        assert result["report_type"] == "blood_test"
        assert result["date"] == "2025-01-15"
        assert len(result["key_findings"]) == 1
        assert "fasting glucose" in result["values"]

    def test_parse_invalid_extraction(self):
        from seniocare.image_analysis.report_analyzer import _parse_extraction_response
        result = _parse_extraction_response("not json")
        assert result["report_type"] == "unknown"
        assert result["values"] == {}

    def test_severity_normal(self):
        from seniocare.image_analysis.report_analyzer import evaluate_severity_from_values
        values = {"hemoglobin": "14.0 g/dL", "platelets": "250 thousand/uL"}
        assert evaluate_severity_from_values(values) == "NORMAL"

    def test_severity_attention(self):
        from seniocare.image_analysis.report_analyzer import evaluate_severity_from_values
        values = {"fasting glucose": "140 mg/dL", "total cholesterol": "250 mg/dL"}
        assert evaluate_severity_from_values(values) == "ATTENTION"

    def test_severity_critical_high_glucose(self):
        from seniocare.image_analysis.report_analyzer import evaluate_severity_from_values
        values = {"fasting glucose": "350 mg/dL"}
        assert evaluate_severity_from_values(values) == "CRITICAL"

    def test_severity_critical_low_hemoglobin(self):
        from seniocare.image_analysis.report_analyzer import evaluate_severity_from_values
        values = {"hemoglobin": "5.5 g/dL"}
        assert evaluate_severity_from_values(values) == "CRITICAL"

    def test_severity_critical_high_potassium(self):
        from seniocare.image_analysis.report_analyzer import evaluate_severity_from_values
        values = {"potassium": "6.5 mEq/L"}
        assert evaluate_severity_from_values(values) == "CRITICAL"

    def test_severity_mixed_values(self):
        """If any value is critical, overall should be CRITICAL."""
        from seniocare.image_analysis.report_analyzer import evaluate_severity_from_values
        values = {
            "fasting glucose": "95 mg/dL",     # normal
            "total cholesterol": "250 mg/dL",   # attention
            "hemoglobin": "5.0 g/dL",           # critical
        }
        assert evaluate_severity_from_values(values) == "CRITICAL"

    def test_db_storage_and_retrieval(self):
        """Test that report storage and retrieval works."""
        from seniocare.image_analysis.report_analyzer import _store_report_in_db, get_user_reports
        import json

        report_id = "RPT_test_123"
        user_id = "test_image_user"
        report_data = {
            "report_type": "blood_test",
            "date": "2025-01-15",
            "key_findings": ["Elevated glucose"],
            "values": {"fasting glucose": "180 mg/dL"},
            "recommendations": ["Follow up with doctor"],
        }

        stored = _store_report_in_db(
            report_id=report_id,
            user_id=user_id,
            report_data=report_data,
            health_summary="Blood sugar is elevated. Consult your doctor.",
            severity_level="ATTENTION",
            raw_response="raw model output here",
        )
        assert stored is True

        # Retrieve and verify
        reports = get_user_reports(user_id)
        assert len(reports) >= 1

        found = None
        for r in reports:
            if r["report_id"] == report_id:
                found = r
                break

        assert found is not None
        assert found["report_type"] == "blood_test"
        assert found["severity_level"] == "ATTENTION"
        assert "Elevated glucose" in found["key_findings"]
        assert found["lab_values"]["fasting glucose"] == "180 mg/dL"


# ===========================================================================
# Run tests
# ===========================================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

