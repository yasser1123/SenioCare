"""Exercise tool - provides safe exercises based on mobility and conditions from the database."""

import json
from google.adk.tools import ToolContext
from seniocare.data.database import get_connection


def get_exercises(tool_context: ToolContext) -> dict:
    """
    Returns safe exercises appropriate for the user's mobility level and conditions.

    Reads mobility_level and conditions from tool_context.state.

    Args:
        tool_context: The tool context for state access.

    Returns:
        dict: Safe exercise recommendations with instructions.
    """
    # Prevent multiple calls in the same turn
    if tool_context.state.get("_exercise_tool_called"):
        return {
            "status": "already_called",
            "message": "تم استدعاء هذه الأداة بالفعل. استخدم النتيجة السابقة لصياغة التوصية."
        }
    tool_context.state["_exercise_tool_called"] = True

    # Read from state
    mobility_level = tool_context.state.get("user:mobilityStatus", "limited")
    conditions = tool_context.state.get("user:chronicDiseases", [])
    conditions_lower = [c.lower() for c in conditions]

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Get exercises for the user's mobility level
        cursor.execute(
            "SELECT * FROM exercises WHERE mobility_level = ?",
            (mobility_level.lower(),)
        )
        all_exercises = [dict(row) for row in cursor.fetchall()]

        # Filter out exercises that should be avoided for user's conditions
        safe_exercises = []
        excluded_exercises = []

        for exercise in all_exercises:
            avoid_conditions = json.loads(exercise["avoid_conditions"]) if exercise["avoid_conditions"] else []
            avoid_lower = [c.lower() for c in avoid_conditions]

            conflicting = [c for c in conditions_lower if c in avoid_lower]
            if conflicting:
                excluded_exercises.append({
                    "name_en": exercise["name_en"],
                    "reason": f"Not recommended for: {', '.join(conflicting)}"
                })
            else:
                steps = json.loads(exercise["steps"])
                safe_exercises.append({
                    "exercise_id": exercise["exercise_id"],
                    "name_ar": exercise["name_ar"],
                    "type": exercise["exercise_type"],
                    "duration": exercise["duration"],
                    "steps": steps,
                    "benefits_ar": exercise["benefits_ar"],
                    "safety_ar": exercise["safety_ar"],
                })

        return {
            "status": "success",
            "mobility_level": mobility_level,
            "conditions_considered": conditions,
            "exercises": safe_exercises[:2],  # Return max 2 exercises
            "excluded": excluded_exercises if excluded_exercises else None,
            "total_found": len(safe_exercises),
            "general_advice": "استشر طبيبك قبل بدء أي برنامج تمارين جديد",
            "warning": "توقف فوراً إذا شعرت بألم في الصدر أو ضيق في التنفس"
        }

    finally:
        conn.close()
