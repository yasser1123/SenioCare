"""Image analysis storage tools — stores medical report results from Gemma 4 analysis.

Gemma 4 handles image analysis natively via run_sse (text + image in one prompt).
These tools are ONLY for storing structured results to the database after the
model has already analyzed the image.
"""

import json
import uuid
from datetime import datetime

from google.adk.tools import ToolContext
from seniocare.data.database import get_connection


async def store_medical_report(
    report_type: str,
    key_findings: list,
    lab_values: dict,
    health_summary: str,
    severity_level: str,
    recommendations: list,
    tool_context: ToolContext,
) -> dict:
    """Store analyzed medical report results in the database.

    Called by the Feature Agent AFTER Gemma 4 has analyzed a medical
    report image. The model extracts the data, this tool stores it.

    Args:
        report_type: Type of report (blood_test, x_ray, prescription, etc.)
        key_findings: List of important findings from the report.
        lab_values: Dict of test names to values with units.
        health_summary: AI-generated plain-language health evaluation.
        severity_level: NORMAL, ATTENTION, or CRITICAL.
        recommendations: List of actionable recommendations.
        tool_context: The tool context for state access.

    Returns:
        dict: Confirmation with report_id and storage status.
    """
    # Prevent multiple calls in the same turn
    if tool_context.state.get("_store_report_tool_called"):
        return {
            "status": "already_called",
            "message": "تم حفظ التقرير الطبي بالفعل. استخدم النتيجة السابقة.",
        }
    tool_context.state["_store_report_tool_called"] = True

    user_id = tool_context.state.get("user:user_id", "unknown")
    report_id = f"RPT_{uuid.uuid4().hex[:12]}"

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO medical_reports
            (report_id, user_id, report_type, report_date, key_findings,
             lab_values, health_summary, severity_level, recommendations,
             scanned_at, raw_response)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (report_id) DO NOTHING
            """,
            (
                report_id,
                user_id,
                report_type,
                datetime.now().strftime("%Y-%m-%d"),
                json.dumps(key_findings, ensure_ascii=False),
                json.dumps(lab_values, ensure_ascii=False),
                health_summary,
                severity_level,
                json.dumps(recommendations, ensure_ascii=False),
                datetime.now().isoformat(),
                "",  # raw_response not needed — Gemma 4 handles inline
            ),
        )

        conn.commit()
        conn.close()

        return {
            "status": "success",
            "report_id": report_id,
            "message": f"تم حفظ التقرير الطبي بنجاح (ID: {report_id})",
            "severity_level": severity_level,
            "stored_in_db": True,
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": str(e),
            "stored_in_db": False,
        }


def get_user_medical_reports(user_id: str) -> list[dict]:
    """Retrieve all previously analyzed medical reports for a user.

    Args:
        user_id: The user's identifier.

    Returns:
        List of report records from the database.
    """
    try:
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
