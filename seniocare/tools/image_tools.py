"""Image analysis tools — wraps the medication and report analyzers as ADK tools."""

from google.adk.tools import ToolContext


async def analyze_medication_image_tool(
    image_base64: str,
    tool_context: ToolContext,
) -> dict:
    """
    Analyze a medication box/package image to extract medication info.

    Uses OCR AI (richardyoung/olmocr2:7b-q8) to extract:
    - Medication name
    - Active ingredient
    - Dose / concentration

    Args:
        image_base64: Base64 encoded image of the medication box.
        tool_context: The tool context for state access.

    Returns:
        dict: Extracted medication information (name, active_ingredient, dosage).
    """
    # Prevent multiple calls in the same turn
    if tool_context.state.get("_medication_image_tool_called"):
        return {
            "status": "already_called",
            "message": "تم تحليل صورة الدواء بالفعل. استخدم النتيجة السابقة.",
        }
    tool_context.state["_medication_image_tool_called"] = True

    user_id = tool_context.state.get("user:user_id", "unknown")

    from seniocare.image_analysis.medication_analyzer import analyze_medication_image

    result = await analyze_medication_image(
        image_base64=image_base64,
        user_id=user_id,
    )

    if result.success:
        return {
            "status": "success",
            "medication_name": result.medication_name,
            "active_ingredient": result.active_ingredient,
            "dosage": result.dosage,
            "manufacturer": result.manufacturer,
            "expiry_date": result.expiry_date,
        }
    else:
        return {
            "status": "error",
            "error_message": result.error,
        }


async def analyze_medical_report_tool(
    image_base64: str,
    tool_context: ToolContext,
) -> dict:
    """
    Analyze a medical report image to extract and evaluate health data.

    Uses vision AI (llama3.2-vision) for two-pass analysis:
    1. Extract structured data (lab values, findings, report type)
    2. Evaluate health situation with severity classification

    Results are stored in the database for historical tracking.

    Args:
        image_base64: Base64 encoded image of the medical report.
        tool_context: The tool context for state access.

    Returns:
        dict: Full report analysis with health summary, severity, and recommendations.
    """
    # Prevent multiple calls in the same turn
    if tool_context.state.get("_medical_report_tool_called"):
        return {
            "status": "already_called",
            "message": "تم تحليل التقرير الطبي بالفعل. استخدم النتيجة السابقة.",
        }
    tool_context.state["_medical_report_tool_called"] = True

    user_id = tool_context.state.get("user:user_id", "unknown")

    from seniocare.image_analysis.report_analyzer import analyze_medical_report

    result = await analyze_medical_report(
        image_base64=image_base64,
        user_id=user_id,
    )

    if result.success:
        return {
            "status": "success",
            "report_id": result.report_id,
            "report_type": result.report_type,
            "report_date": result.report_date,
            "key_findings": result.key_findings,
            "lab_values": result.lab_values,
            "health_summary": result.health_summary,
            "severity_level": result.severity_level,
            "recommendations": result.recommendations,
            "safety_disclaimers": result.safety_disclaimers,
            "stored_in_db": result.stored_in_db,
        }
    else:
        return {
            "status": "error",
            "error_message": result.error,
        }
