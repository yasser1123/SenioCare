"""
Unit tests for the image_analysis modules (no model invocation).

Tests only the pure functions: base64 validation, JSON parsing,
medication response parsing, report parsing, severity classification,
and database storage/retrieval.

All tests run WITHOUT Ollama or any AI model.
"""

import json
import base64
import pytest

from seniocare.image_analysis.common import (
    validate_base64_image,
    strip_base64_prefix,
    parse_json_from_response,
)
from seniocare.image_analysis.medication_analyzer import _parse_medication_response
from seniocare.image_analysis.report_analyzer import (
    _parse_extraction_response,
    _parse_evaluation_response,
    evaluate_severity_from_values,
    _extract_numeric,
    _store_report_in_db,
    get_user_reports,
)


# ===========================================================================
# Base64 Validation
# ===========================================================================
class TestValidateBase64Image:

    def test_valid_base64(self):
        valid = base64.b64encode(b"fake image data").decode()
        assert validate_base64_image(valid) is True

    def test_valid_with_png_data_url_prefix(self):
        raw = base64.b64encode(b"fake png data").decode()
        with_prefix = f"data:image/png;base64,{raw}"
        assert validate_base64_image(with_prefix) is True

    def test_valid_with_jpeg_data_url_prefix(self):
        raw = base64.b64encode(b"fake jpeg data").decode()
        with_prefix = f"data:image/jpeg;base64,{raw}"
        assert validate_base64_image(with_prefix) is True

    def test_invalid_base64(self):
        assert validate_base64_image("not-valid-base64!!!") is False

    def test_empty_string(self):
        assert validate_base64_image("") is False

    def test_whitespace_only(self):
        assert validate_base64_image("   ") is False

    def test_very_short_base64(self):
        """1 byte encoded should still be valid."""
        short = base64.b64encode(b"x").decode()
        assert validate_base64_image(short) is True


# ===========================================================================
# Strip Base64 Prefix
# ===========================================================================
class TestStripBase64Prefix:

    def test_with_png_prefix(self):
        assert strip_base64_prefix("data:image/png;base64,ABC123") == "ABC123"

    def test_with_jpeg_prefix(self):
        assert strip_base64_prefix("data:image/jpeg;base64,XYZ") == "XYZ"

    def test_without_prefix(self):
        assert strip_base64_prefix("ABC123") == "ABC123"

    def test_preserves_content_after_first_comma(self):
        """Only split on the first comma."""
        result = strip_base64_prefix("data:image/png;base64,ABC,DEF")
        assert result == "ABC,DEF"


# ===========================================================================
# JSON Parsing from Model Response
# ===========================================================================
class TestParseJsonFromResponse:

    def test_plain_json(self):
        result = parse_json_from_response('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_in_code_fences(self):
        response = '```json\n{"key": "value"}\n```'
        result = parse_json_from_response(response)
        assert result == {"key": "value"}

    def test_json_with_surrounding_text(self):
        response = 'Here is the result:\n{"medication_name": "Panadol"}\nEnd.'
        result = parse_json_from_response(response)
        assert result["medication_name"] == "Panadol"

    def test_invalid_json_raises(self):
        """Completely invalid JSON should raise JSONDecodeError."""
        with pytest.raises(json.JSONDecodeError):
            parse_json_from_response("this has no json at all")

    def test_nested_json(self):
        response = '{"outer": {"inner": "value"}, "list": [1, 2, 3]}'
        result = parse_json_from_response(response)
        assert result["outer"]["inner"] == "value"
        assert result["list"] == [1, 2, 3]

    def test_empty_json_object(self):
        result = parse_json_from_response("{}")
        assert result == {}

    def test_json_with_unicode(self):
        """Arabic/Unicode content should parse correctly."""
        response = '{"name": "ميتفورمين", "dose": "500mg"}'
        result = parse_json_from_response(response)
        assert result["name"] == "ميتفورمين"


# ===========================================================================
# Medication Response Parsing
# ===========================================================================
class TestMedicationParsing:

    def test_valid_full_response(self):
        response = json.dumps({
            "medication_name": "Panadol Extra",
            "active_ingredient": "Paracetamol + Caffeine",
            "dosage": "500mg/65mg",
            "manufacturer": "GSK",
            "expiry_date": "12/2026",
        })
        result = _parse_medication_response(response)
        assert result.success is True
        assert result.medication_name == "Panadol Extra"
        assert result.active_ingredient == "Paracetamol + Caffeine"
        assert result.dosage == "500mg/65mg"
        assert result.manufacturer == "GSK"
        assert result.expiry_date == "12/2026"

    def test_partial_response_nulls(self):
        response = json.dumps({
            "medication_name": "Augmentin",
            "active_ingredient": "Amoxicillin + Clavulanic acid",
            "dosage": "1g",
            "manufacturer": None,
            "expiry_date": None,
        })
        result = _parse_medication_response(response)
        assert result.success is True
        assert result.medication_name == "Augmentin"
        assert result.manufacturer is None
        assert result.expiry_date is None

    def test_invalid_json_fallback(self):
        result = _parse_medication_response("this is not JSON at all")
        assert result.success is True  # Still returns True but with error note
        assert result.error is not None

    def test_markdown_wrapped(self):
        response = '```json\n{"medication_name": "Metformin", "active_ingredient": "Metformin HCl", "dosage": "500mg", "manufacturer": "Merck", "expiry_date": null}\n```'
        result = _parse_medication_response(response)
        assert result.medication_name == "Metformin"
        assert result.dosage == "500mg"

    def test_empty_response(self):
        result = _parse_medication_response("")
        # Should handle gracefully — either parse error or fallback
        assert result.success is True
        assert result.error is not None

    def test_missing_fields_default_none(self):
        """Response with only medication_name should set others to None."""
        response = '{"medication_name": "Aspirin"}'
        result = _parse_medication_response(response)
        assert result.success is True
        assert result.medication_name == "Aspirin"
        assert result.active_ingredient is None
        assert result.dosage is None


# ===========================================================================
# Report Extraction Parsing
# ===========================================================================
class TestReportExtractionParsing:

    def test_valid_extraction(self):
        response = json.dumps({
            "report_type": "blood_test",
            "date": "2025-01-15",
            "key_findings": ["High blood sugar"],
            "values": {"fasting glucose": "180 mg/dL"},
            "recommendations": ["Follow up in 1 month"],
        })
        result = _parse_extraction_response(response)
        assert result["report_type"] == "blood_test"
        assert result["date"] == "2025-01-15"
        assert len(result["key_findings"]) == 1
        assert "fasting glucose" in result["values"]

    def test_invalid_extraction_fallback(self):
        result = _parse_extraction_response("not json")
        assert result["report_type"] == "unknown"
        assert result["values"] == {}
        assert result["key_findings"] == []

    def test_partial_extraction(self):
        """Response with only some fields should fill defaults."""
        response = '{"report_type": "x_ray"}'
        result = _parse_extraction_response(response)
        assert result["report_type"] == "x_ray"
        assert result["key_findings"] == []
        assert result["values"] == {}


# ===========================================================================
# Report Evaluation Parsing
# ===========================================================================
class TestReportEvaluationParsing:

    def test_valid_evaluation(self):
        response = json.dumps({
            "health_summary": "Blood sugar is slightly elevated.",
            "severity_level": "ATTENTION",
            "additional_recommendations": ["Monitor glucose daily"],
        })
        result = _parse_evaluation_response(response)
        assert result["health_summary"] == "Blood sugar is slightly elevated."
        assert result["severity_level"] == "ATTENTION"
        assert len(result["additional_recommendations"]) == 1

    def test_invalid_evaluation_fallback(self):
        result = _parse_evaluation_response("Just a plain text response.")
        assert result["health_summary"] == "Just a plain text response."
        assert result["severity_level"] == "NORMAL"


# ===========================================================================
# Severity Classification
# ===========================================================================
class TestSeverityClassification:

    def test_normal_values(self):
        values = {"hemoglobin": "14.0 g/dL", "platelets": "250 thousand/uL"}
        assert evaluate_severity_from_values(values) == "NORMAL"

    def test_attention_high_glucose(self):
        values = {"fasting glucose": "140 mg/dL"}
        assert evaluate_severity_from_values(values) == "ATTENTION"

    def test_attention_high_cholesterol(self):
        values = {"total cholesterol": "250 mg/dL"}
        assert evaluate_severity_from_values(values) == "ATTENTION"

    def test_critical_very_high_glucose(self):
        values = {"fasting glucose": "350 mg/dL"}
        assert evaluate_severity_from_values(values) == "CRITICAL"

    def test_critical_low_hemoglobin(self):
        values = {"hemoglobin": "5.5 g/dL"}
        assert evaluate_severity_from_values(values) == "CRITICAL"

    def test_critical_high_potassium(self):
        values = {"potassium": "6.5 mEq/L"}
        assert evaluate_severity_from_values(values) == "CRITICAL"

    def test_critical_low_potassium(self):
        values = {"potassium": "2.5 mEq/L"}
        assert evaluate_severity_from_values(values) == "CRITICAL"

    def test_mixed_values_critical_wins(self):
        """If any value is critical, overall should be CRITICAL."""
        values = {
            "fasting glucose": "95 mg/dL",      # normal
            "total cholesterol": "250 mg/dL",    # attention
            "hemoglobin": "5.0 g/dL",            # critical
        }
        assert evaluate_severity_from_values(values) == "CRITICAL"

    def test_no_recognizable_values(self):
        """Non-numeric or unrecognized test names should return NORMAL."""
        values = {"unknown_test": "positive", "another": "negative"}
        assert evaluate_severity_from_values(values) == "NORMAL"

    def test_empty_values(self):
        assert evaluate_severity_from_values({}) == "NORMAL"

    def test_borderline_attention_glucose(self):
        """Exactly at the attention threshold."""
        values = {"fasting glucose": "126 mg/dL"}
        assert evaluate_severity_from_values(values) == "ATTENTION"

    @pytest.mark.parametrize("test_name,value,expected", [
        ("fasting glucose", "250 mg/dL", "CRITICAL"),
        ("hba1c", "11.0 %", "CRITICAL"),
        ("creatinine", "5.0 mg/dL", "CRITICAL"),
        ("wbc", "1.5 thousand/uL", "CRITICAL"),
        ("sodium", "120 mEq/L", "CRITICAL"),
        ("platelets", "40 thousand/uL", "CRITICAL"),
    ])
    def test_all_critical_thresholds(self, test_name, value, expected):
        """Each critical threshold should be detected correctly."""
        assert evaluate_severity_from_values({test_name: value}) == expected


# ===========================================================================
# Extract Numeric Helper
# ===========================================================================
class TestExtractNumeric:

    def test_simple_integer(self):
        assert _extract_numeric("180") == 180.0

    def test_with_unit(self):
        assert _extract_numeric("180 mg/dL") == 180.0

    def test_decimal(self):
        assert _extract_numeric("5.5 g/dL") == 5.5

    def test_with_reference_range(self):
        """Should extract the first number."""
        assert _extract_numeric("120 mg/dL (ref: 70-100)") == 120.0

    def test_no_number(self):
        assert _extract_numeric("positive") is None

    def test_empty_string(self):
        assert _extract_numeric("") is None


# ===========================================================================
# DB Storage and Retrieval
# ===========================================================================
class TestReportDBStorage:

    def test_store_and_retrieve(self):
        report_id = "RPT_unit_test_001"
        user_id = "test_img_user_unit"
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
            health_summary="Blood sugar is elevated.",
            severity_level="ATTENTION",
            raw_response="raw output",
        )
        assert stored is True

        reports = get_user_reports(user_id)
        assert len(reports) >= 1
        found = next((r for r in reports if r["report_id"] == report_id), None)
        assert found is not None
        assert found["report_type"] == "blood_test"
        assert found["severity_level"] == "ATTENTION"

    def test_retrieve_empty_user(self):
        """User with no reports should return empty list."""
        reports = get_user_reports("nonexistent_user_xyz_999")
        assert reports == []

    def test_multiple_reports_ordering(self):
        """Multiple reports should be returned most-recent first."""
        user_id = "test_ordering_user"
        for i in range(3):
            _store_report_in_db(
                report_id=f"RPT_order_{i}",
                user_id=user_id,
                report_data={"report_type": "blood_test", "key_findings": [], "values": {}, "recommendations": []},
                health_summary=f"Report {i}",
                severity_level="NORMAL",
                raw_response="raw",
            )
        reports = get_user_reports(user_id)
        assert len(reports) >= 3
        # Most recent should be first (they were inserted sequentially)
        report_ids = [r["report_id"] for r in reports]
        assert report_ids.index("RPT_order_2") < report_ids.index("RPT_order_0")
