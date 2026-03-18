"""
Unit tests for medication tools: get_medication_schedule and log_medication_intake.

Covers:
- Valid/invalid user lookups, missing user_id
- Medication fields validation, double-call prevention
- Logging with various states
"""

import pytest
from seniocare.tools.medication import get_medication_schedule, log_medication_intake


# ===========================================================================
# get_medication_schedule
# ===========================================================================
class TestGetMedicationSchedule:
    """Comprehensive tests for get_medication_schedule."""

    def test_valid_user_returns_medications(self, diabetic_hypertensive_user):
        result = get_medication_schedule(tool_context=diabetic_hypertensive_user)
        assert result["status"] == "success"
        assert result["user_id"] == "user_001"
        assert len(result["medications"]) == 2
        med_names = [m["name"] for m in result["medications"]]
        assert "Metformin" in med_names
        assert "Lisinopril" in med_names

    def test_unknown_user(self, fresh_context):
        ctx = fresh_context({"user:user_id": "unknown_user_xyz"})
        result = get_medication_schedule(tool_context=ctx)
        assert result["status"] == "error"

    def test_no_user_id(self, empty_context):
        result = get_medication_schedule(tool_context=empty_context)
        assert result["status"] == "error"

    def test_empty_string_user_id(self, fresh_context):
        """Empty string user_id should be treated as missing."""
        ctx = fresh_context({"user:user_id": ""})
        result = get_medication_schedule(tool_context=ctx)
        assert result["status"] == "error"

    def test_prevents_double_call(self, fresh_context):
        ctx = fresh_context({"user:user_id": "user_001"})
        result1 = get_medication_schedule(tool_context=ctx)
        assert result1["status"] == "success"
        result2 = get_medication_schedule(tool_context=ctx)
        assert result2["status"] == "already_called"

    def test_medication_fields_present(self, diabetic_hypertensive_user):
        result = get_medication_schedule(tool_context=diabetic_hypertensive_user)
        assert result["status"] == "success"
        for med in result["medications"]:
            assert "name" in med
            assert "dose" in med
            assert "schedule" in med
            assert isinstance(med["schedule"], list)
            assert "purpose_ar" in med
            assert "instructions_ar" in med

    def test_user_003_medications(self, heart_disease_user):
        """Heart disease user should have 3 medications."""
        result = get_medication_schedule(tool_context=heart_disease_user)
        assert result["status"] == "success"
        assert result["user_id"] == "user_003"
        assert len(result["medications"]) == 3
        med_names = [m["name"] for m in result["medications"]]
        assert "Aspirin" in med_names
        assert "Simvastatin" in med_names
        assert "Warfarin" in med_names

    def test_next_doses_format(self, diabetic_hypertensive_user):
        result = get_medication_schedule(tool_context=diabetic_hypertensive_user)
        assert result["status"] == "success"
        # next_doses is either a list of dicts or a string message
        next_doses = result["next_doses"]
        assert isinstance(next_doses, (list, str))
        if isinstance(next_doses, list):
            for dose in next_doses:
                assert "medication" in dose
                assert "dose" in dose
                assert "time" in dose


# ===========================================================================
# log_medication_intake
# ===========================================================================
class TestLogMedicationIntake:
    """Comprehensive tests for log_medication_intake."""

    def test_log_success(self, diabetic_hypertensive_user):
        result = log_medication_intake(
            medication_name="Metformin",
            tool_context=diabetic_hypertensive_user,
        )
        assert result["status"] == "success"
        assert "Metformin" in result["message"]
        assert result["timestamp"] is not None

    def test_log_with_no_user_id(self, fresh_context):
        """Logging without user_id should still succeed (logs with empty user_id)."""
        ctx = fresh_context()
        result = log_medication_intake(medication_name="Aspirin", tool_context=ctx)
        assert result["status"] == "success"
        assert result["user_id"] == ""

    def test_log_nonexistent_medication(self, fresh_context):
        """Logging a non-existent medication name still succeeds (no DB validation)."""
        ctx = fresh_context({"user:user_id": "user_001"})
        result = log_medication_intake(
            medication_name="FakeDrug123",
            tool_context=ctx,
        )
        assert result["status"] == "success"
        assert "FakeDrug123" in result["message"]

    def test_prevents_double_call(self, fresh_context):
        ctx = fresh_context({"user:user_id": "user_001"})
        result1 = log_medication_intake(medication_name="Metformin", tool_context=ctx)
        assert result1["status"] == "success"
        result2 = log_medication_intake(medication_name="Lisinopril", tool_context=ctx)
        assert result2["status"] == "already_called"

    def test_log_response_structure(self, fresh_context):
        ctx = fresh_context({"user:user_id": "user_001"})
        result = log_medication_intake(medication_name="Metformin", tool_context=ctx)
        assert "status" in result
        assert "message" in result
        assert "timestamp" in result
        assert "user_id" in result

    def test_log_medication_with_arabic_name(self, fresh_context):
        """Arabic medication name should work fine."""
        ctx = fresh_context({"user:user_id": "user_001"})
        result = log_medication_intake(medication_name="ميتفورمين", tool_context=ctx)
        assert result["status"] == "success"
        assert "ميتفورمين" in result["message"]
