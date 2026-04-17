"""
Medical Report Analyzer
=======================

Uses llama3.2-vision to extract information from medical report images
(blood tests, X-rays, prescriptions, lab results, etc.).

Features:
- Full text extraction and structured parsing of lab values
- AI-generated health summary describing what the results mean
- Severity classification (NORMAL / ATTENTION / CRITICAL)
- Safety disclaimers automatically appended
- Results stored in the database for historical tracking
"""

import json
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel

from seniocare.image_analysis.common import (
    check_model_available,
    call_ollama_vision,
    parse_json_from_response,
    validate_base64_image,
    strip_base64_prefix,
)


# ---------------------------------------------------------------------------
# Model configuration
# ---------------------------------------------------------------------------
REPORT_VISION_MODEL = "llama3.2-vision"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------
class ReportAnalysisResult(BaseModel):
    """Result of medical report analysis — stored in DB."""
    success: bool
    report_id: Optional[str] = None
    report_type: Optional[str] = None       # blood_test, x_ray, prescription, etc.
    report_date: Optional[str] = None
    key_findings: list[str] = []
    lab_values: dict = {}                    # {"test_name": "value with unit", ...}
    health_summary: Optional[str] = None     # AI-generated plain-language evaluation
    severity_level: Optional[str] = None     # NORMAL / ATTENTION / CRITICAL
    recommendations: list[str] = []
    safety_disclaimers: list[str] = []
    raw_response: Optional[str] = None
    stored_in_db: bool = False
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
def _get_report_extraction_prompt() -> str:
    """First-pass prompt: extract structured data from the medical report image."""
    return """You are a medical report analysis specialist. Analyze this medical report image and extract ALL information.

Return a JSON object with the following structure:

{
    "report_type": "type of report (blood_test, x_ray, prescription, urine_test, lipid_panel, cbc, metabolic_panel, thyroid_panel, other)",
    "date": "date of the report if visible",
    "key_findings": ["list of important findings, abnormal values, or notable observations"],
    "values": {"test_name": "value with unit", "test_name_2": "value with unit"},
    "recommendations": ["any recommendations, notes, or follow-up actions mentioned"]
}

IMPORTANT RULES:
- Extract ALL test values visible in the report
- Flag any values that appear abnormal or out of reference range
- Include reference ranges if visible (e.g. "120 mg/dL (ref: 70-100)")
- Focus especially on:
  * Blood sugar levels (fasting glucose, HbA1c, random glucose)
  * Blood pressure readings
  * Cholesterol (total, HDL, LDL, triglycerides)
  * Kidney function (creatinine, BUN, eGFR)
  * Liver function (ALT, AST, bilirubin, albumin)
  * Complete blood count (WBC, RBC, hemoglobin, platelets)
  * Thyroid function (TSH, T3, T4)
  * Any flagged or highlighted abnormal values
- Be precise — only include information clearly visible in the image
- Respond ONLY with the JSON object, no other text"""


def _get_health_evaluation_prompt(report_data: dict) -> str:
    """Second-pass prompt: evaluate the extracted data and describe health situation."""
    return f"""You are a medical report interpreter for elderly patients. Based on the following extracted medical report data, provide a clear and easy-to-understand health evaluation.

EXTRACTED REPORT DATA:
{json.dumps(report_data, indent=2, ensure_ascii=False)}

Write a comprehensive health summary that:
1. Describes what each test measures and why it matters
2. Explains which values are normal and which are concerning
3. Highlights any values that need immediate attention
4. Provides context about what abnormal values could mean for an elderly patient
5. Suggests general lifestyle recommendations based on the findings

IMPORTANT RULES:
- Write in clear, simple language that a non-medical person can understand
- Do NOT diagnose any condition — only describe what the values suggest
- Do NOT prescribe or recommend any medication
- Always recommend consulting a doctor for abnormal values
- Be reassuring for normal values
- Be informative but not alarming for slightly abnormal values
- Be clear and direct about seriously abnormal values

Return your response as a JSON object:
{{
    "health_summary": "Your detailed health evaluation paragraph(s)",
    "severity_level": "NORMAL or ATTENTION or CRITICAL",
    "additional_recommendations": ["list of additional lifestyle or follow-up recommendations"]
}}

Severity classification:
- NORMAL: All values within acceptable ranges, no concerns
- ATTENTION: Some values slightly out of range, needs monitoring or follow-up
- CRITICAL: One or more values significantly out of range, needs prompt medical attention

Respond ONLY with the JSON object, no other text."""


# ---------------------------------------------------------------------------
# Severity classification (rule-based fallback)
# ---------------------------------------------------------------------------
# Known critical thresholds for common lab values (for elderly patients)
_CRITICAL_THRESHOLDS = {
    "glucose": {"high": 300, "low": 50},
    "fasting glucose": {"high": 200, "low": 50},
    "hba1c": {"high": 10.0},
    "systolic": {"high": 180},
    "diastolic": {"high": 120},
    "creatinine": {"high": 4.0},
    "potassium": {"high": 6.0, "low": 3.0},
    "sodium": {"high": 150, "low": 125},
    "hemoglobin": {"low": 7.0},
    "platelets": {"low": 50},
    "wbc": {"high": 30, "low": 2},
}

_ATTENTION_THRESHOLDS = {
    "glucose": {"high": 140, "low": 70},
    "fasting glucose": {"high": 126, "low": 70},
    "hba1c": {"high": 7.0},
    "total cholesterol": {"high": 240},
    "ldl": {"high": 160},
    "triglycerides": {"high": 200},
    "systolic": {"high": 140},
    "diastolic": {"high": 90},
    "creatinine": {"high": 1.5},
    "alt": {"high": 56},
    "ast": {"high": 40},
    "hemoglobin": {"low": 10.0},
    "tsh": {"high": 5.0, "low": 0.4},
}


def _extract_numeric(value_str: str) -> Optional[float]:
    """Try to extract a numeric value from a lab result string."""
    import re
    match = re.search(r"(\d+\.?\d*)", str(value_str))
    if match:
        return float(match.group(1))
    return None


def evaluate_severity_from_values(lab_values: dict) -> str:
    """
    Rule-based severity classification as a fallback.

    Checks extracted lab values against known thresholds.
    Returns: 'NORMAL', 'ATTENTION', or 'CRITICAL'
    """
    severity = "NORMAL"

    for test_name, value_str in lab_values.items():
        numeric = _extract_numeric(value_str)
        if numeric is None:
            continue

        test_key = test_name.lower().strip()

        # Check critical thresholds
        for threshold_key, limits in _CRITICAL_THRESHOLDS.items():
            if threshold_key in test_key:
                if "high" in limits and numeric >= limits["high"]:
                    return "CRITICAL"
                if "low" in limits and numeric <= limits["low"]:
                    return "CRITICAL"

        # Check attention thresholds
        for threshold_key, limits in _ATTENTION_THRESHOLDS.items():
            if threshold_key in test_key:
                if "high" in limits and numeric >= limits["high"]:
                    severity = "ATTENTION"
                if "low" in limits and numeric <= limits["low"]:
                    severity = "ATTENTION"

    return severity


# ---------------------------------------------------------------------------
# Safety disclaimers
# ---------------------------------------------------------------------------
_SAFETY_DISCLAIMERS = [
    "⚕️ This analysis is generated by AI and is NOT a medical diagnosis.",
    "👨‍⚕️ Always consult your doctor before making any health decisions based on these results.",
    "📋 Take this report to your next doctor's appointment for professional interpretation.",
    "⚠️ If you experience any severe symptoms, seek immediate medical attention.",
]


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------
def _parse_extraction_response(raw_response: str) -> dict:
    """Parse the first-pass extraction response."""
    try:
        data = parse_json_from_response(raw_response)
        return {
            "report_type": data.get("report_type", "unknown"),
            "date": data.get("date"),
            "key_findings": data.get("key_findings", []),
            "values": data.get("values", {}),
            "recommendations": data.get("recommendations", []),
        }
    except (json.JSONDecodeError, KeyError, ValueError):
        return {
            "report_type": "unknown",
            "date": None,
            "key_findings": [],
            "values": {},
            "recommendations": [],
        }


def _parse_evaluation_response(raw_response: str) -> dict:
    """Parse the second-pass health evaluation response."""
    try:
        data = parse_json_from_response(raw_response)
        return {
            "health_summary": data.get("health_summary", ""),
            "severity_level": data.get("severity_level", "NORMAL"),
            "additional_recommendations": data.get("additional_recommendations", []),
        }
    except (json.JSONDecodeError, KeyError, ValueError):
        return {
            "health_summary": raw_response,
            "severity_level": "NORMAL",
            "additional_recommendations": [],
        }


# ---------------------------------------------------------------------------
# Database storage
# ---------------------------------------------------------------------------
def _store_report_in_db(
    report_id: str,
    user_id: str,
    report_data: dict,
    health_summary: str,
    severity_level: str,
    raw_response: str,
) -> bool:
    """Store the analyzed report in the medical_reports table."""
    try:
        from seniocare.data.database import get_connection

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO medical_reports
            (report_id, user_id, report_type, report_date, key_findings,
             lab_values, health_summary, severity_level, recommendations,
             scanned_at, raw_response)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (report_id) DO UPDATE SET
                report_type = EXCLUDED.report_type,
                key_findings = EXCLUDED.key_findings,
                lab_values = EXCLUDED.lab_values,
                health_summary = EXCLUDED.health_summary,
                severity_level = EXCLUDED.severity_level,
                recommendations = EXCLUDED.recommendations,
                scanned_at = EXCLUDED.scanned_at,
                raw_response = EXCLUDED.raw_response
            """,
            (
                report_id,
                user_id,
                report_data.get("report_type", "unknown"),
                report_data.get("date"),
                json.dumps(report_data.get("key_findings", []), ensure_ascii=False),
                json.dumps(report_data.get("values", {}), ensure_ascii=False),
                health_summary,
                severity_level,
                json.dumps(report_data.get("recommendations", []), ensure_ascii=False),
                datetime.now().isoformat(),
                raw_response,
            ),
        )

        conn.commit()
        conn.close()
        return True

    except Exception:
        return False


# ---------------------------------------------------------------------------
# Main analysis function
# ---------------------------------------------------------------------------
async def analyze_medical_report(
    image_base64: str,
    user_id: str,
) -> ReportAnalysisResult:
    """
    Analyze a medical report image: extract data, evaluate health, store in DB.

    Uses llama3.2-vision for image understanding.
    Two-pass analysis:
        1. Extract structured data (lab values, findings, type)
        2. Evaluate health situation and classify severity

    Args:
        image_base64: Base64 encoded image of the medical report
        user_id: User identifier for DB storage

    Returns:
        ReportAnalysisResult with full analysis, summary, and severity
    """
    # Validate image
    if not validate_base64_image(image_base64):
        return ReportAnalysisResult(
            success=False,
            error="Invalid base64 image data",
        )

    # Check model availability
    model_available = await check_model_available(REPORT_VISION_MODEL)
    if not model_available:
        return ReportAnalysisResult(
            success=False,
            error=(
                f"Vision model '{REPORT_VISION_MODEL}' not available. "
                f"Please run: ollama pull {REPORT_VISION_MODEL}"
            ),
        )

    try:
        # Clean the base64 string
        clean_b64 = strip_base64_prefix(image_base64)

        # ── PASS 1: Extract structured data from the report image ──
        raw_extraction = await call_ollama_vision(
            model_name=REPORT_VISION_MODEL,
            image_base64=clean_b64,
            prompt=_get_report_extraction_prompt(),
            temperature=0.1,
        )

        report_data = _parse_extraction_response(raw_extraction)

        # ── PASS 2: Evaluate health situation from extracted data ──
        raw_evaluation = await call_ollama_vision(
            model_name=REPORT_VISION_MODEL,
            image_base64=clean_b64,
            prompt=_get_health_evaluation_prompt(report_data),
            temperature=0.3,  # slightly more creative for health summaries
        )

        evaluation = _parse_evaluation_response(raw_evaluation)

        # Combine recommendations from both passes
        all_recommendations = list(set(
            report_data.get("recommendations", [])
            + evaluation.get("additional_recommendations", [])
        ))

        # Determine severity: use AI assessment, fallback to rule-based
        ai_severity = evaluation.get("severity_level", "NORMAL")
        rule_severity = evaluate_severity_from_values(report_data.get("values", {}))

        # Use the MORE severe of the two assessments (safety first)
        severity_order = {"NORMAL": 0, "ATTENTION": 1, "CRITICAL": 2}
        final_severity = (
            ai_severity
            if severity_order.get(ai_severity, 0) >= severity_order.get(rule_severity, 0)
            else rule_severity
        )

        # Generate report ID and store in DB
        report_id = f"RPT_{uuid.uuid4().hex[:12]}"
        health_summary = evaluation.get("health_summary", "")

        stored = _store_report_in_db(
            report_id=report_id,
            user_id=user_id,
            report_data={**report_data, "recommendations": all_recommendations},
            health_summary=health_summary,
            severity_level=final_severity,
            raw_response=raw_extraction,
        )

        return ReportAnalysisResult(
            success=True,
            report_id=report_id,
            report_type=report_data.get("report_type"),
            report_date=report_data.get("date"),
            key_findings=report_data.get("key_findings", []),
            lab_values=report_data.get("values", {}),
            health_summary=health_summary,
            severity_level=final_severity,
            recommendations=all_recommendations,
            safety_disclaimers=_SAFETY_DISCLAIMERS,
            raw_response=raw_extraction,
            stored_in_db=stored,
        )

    except Exception as e:
        return ReportAnalysisResult(
            success=False,
            error=str(e),
        )


# ---------------------------------------------------------------------------
# Retrieval helper
# ---------------------------------------------------------------------------
def get_user_reports(user_id: str) -> list[dict]:
    """
    Retrieve all previously analyzed reports for a user.

    Args:
        user_id: The user's identifier

    Returns:
        List of report records from the database
    """
    try:
        from seniocare.data.database import get_connection

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM medical_reports WHERE user_id = %s ORDER BY scanned_at DESC",
            (user_id,),
        )
        rows = cursor.fetchall()
        conn.close()

        reports = []
        for row in rows:
            row = dict(row)
            row["key_findings"] = json.loads(row.get("key_findings", "[]"))
            row["lab_values"] = json.loads(row.get("lab_values", "{}"))
            row["recommendations"] = json.loads(row.get("recommendations", "[]"))
            reports.append(row)

        return reports

    except Exception:
        return []
