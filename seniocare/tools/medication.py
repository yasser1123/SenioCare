"""Medication tool - manages medication schedules and logging from the database."""

import json
from datetime import datetime
from google.adk.tools import ToolContext
from seniocare.data.database import get_connection


def get_medication_schedule(tool_context: ToolContext) -> dict:
    """
    Returns the medication schedule for the current user.

    Reads user_id from tool_context.state (populated by the backend).

    Args:
        tool_context: The tool context for state access.

    Returns:
        dict: Medication schedule with next doses.
    """
    # Prevent multiple calls in the same turn
    if tool_context.state.get("_medication_tool_called"):
        return {
            "status": "already_called",
            "message": "تم استدعاء هذه الأداة بالفعل. استخدم النتيجة السابقة لصياغة التوصية."
        }
    tool_context.state["_medication_tool_called"] = True

    user_id = tool_context.state.get("user:user_id", "")
    if not user_id:
        return {
            "status": "error",
            "error_message": "لم يتم تحديد معرف المستخدم"
        }

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "SELECT * FROM medications WHERE user_id = ?",
            (user_id,)
        )
        rows = cursor.fetchall()

        if not rows:
            return {
                "status": "error",
                "error_message": f"لم يتم العثور على جدول أدوية للمستخدم '{user_id}'"
            }

        medications = []
        for row in rows:
            row = dict(row)
            schedule = json.loads(row["schedule"])
            medications.append({
                "name": row["name"],
                "dose": row["dose"],
                "schedule": schedule,
                "purpose_ar": row["purpose_ar"],
                "purpose_en": row["purpose_en"],
                "instructions_ar": row["instructions_ar"],
                "instructions_en": row["instructions_en"],
            })

        # Find next doses
        current_hour = datetime.now().hour
        next_doses = []
        for med in medications:
            for time_str in med["schedule"]:
                hour = int(time_str.split(":")[0])
                if hour > current_hour:
                    next_doses.append({
                        "medication": med["name"],
                        "dose": med["dose"],
                        "time": time_str,
                        "instructions_ar": med["instructions_ar"],
                    })

        return {
            "status": "success",
            "user_id": user_id,
            "medications": medications,
            "next_doses": next_doses[:5] if next_doses else "لا توجد جرعات متبقية اليوم"
        }

    finally:
        conn.close()


def log_medication_intake(medication_name: str, tool_context: ToolContext) -> dict:
    """
    Logs that a user has taken their medication.

    Reads user_id from tool_context.state.

    Args:
        medication_name: Name of the medication taken.
        tool_context: The tool context for state access.

    Returns:
        dict: Confirmation of logging.
    """
    # Prevent multiple calls in the same turn
    if tool_context.state.get("_log_medication_tool_called"):
        return {
            "status": "already_called",
            "message": "تم تسجيل الدواء بالفعل. لا حاجة لتكرار التسجيل."
        }
    tool_context.state["_log_medication_tool_called"] = True

    user_id = tool_context.state.get("user:user_id", "")
    timestamp = datetime.now().isoformat()

    # In production, this would write to a database log table
    return {
        "status": "success",
        "message": f"تم تسجيل تناول {medication_name}",
        "timestamp": timestamp,
        "user_id": user_id
    }
