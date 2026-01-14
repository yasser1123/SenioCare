"""Medication tool - manages medication schedules and logging."""

from datetime import datetime
from google.adk.tools import ToolContext


def get_medication_schedule(user_id: str, tool_context: ToolContext) -> dict:
    """
    Returns the medication schedule for a user.
    
    Args:
        user_id: The unique identifier for the user.
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
    # Mock medication schedules
    schedules = {
        "user_001": {
            "medications": [
                {
                    "name": "Metformin",
                    "dose": "500mg", 
                    "schedule": ["08:00", "20:00"],
                    "purpose": "للسكري",
                    "instructions": "تناوله مع الطعام"
                },
                {
                    "name": "Lisinopril",
                    "dose": "10mg",
                    "schedule": ["09:00"],
                    "purpose": "لضغط الدم",
                    "instructions": "تناوله في نفس الوقت يومياً"
                }
            ]
        },
        "user_002": {
            "medications": [
                {
                    "name": "Calcium",
                    "dose": "600mg",
                    "schedule": ["08:00"],
                    "purpose": "لصحة العظام",
                    "instructions": "تناوله مع الطعام"
                },
                {
                    "name": "Vitamin D",
                    "dose": "1000IU",
                    "schedule": ["08:00"],
                    "purpose": "لامتصاص الكالسيوم",
                    "instructions": "يمكن تناوله مع الكالسيوم"
                }
            ]
        }
    }
    
    if user_id in schedules:
        current_hour = datetime.now().hour
        meds = schedules[user_id]["medications"]
        
        # Find next dose
        next_doses = []
        for med in meds:
            for time in med["schedule"]:
                hour = int(time.split(":")[0])
                if hour > current_hour:
                    next_doses.append({
                        "medication": med["name"],
                        "dose": med["dose"],
                        "time": time,
                        "instructions": med["instructions"]
                    })
        
        return {
            "status": "success",
            "medications": meds,
            "next_doses": next_doses[:3] if next_doses else "لا توجد جرعات متبقية اليوم"
        }
    else:
        return {
            "status": "error",
            "error_message": f"لم يتم العثور على جدول أدوية للمستخدم '{user_id}'"
        }


def log_medication_intake(user_id: str, medication_name: str, tool_context: ToolContext) -> dict:
    """
    Logs that a user has taken their medication.
    
    Args:
        user_id: The unique identifier for the user.
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
    
    timestamp = datetime.now().isoformat()
    
    # In production, this would write to a database
    return {
        "status": "success",
        "message": f"تم تسجيل تناول {medication_name}",
        "timestamp": timestamp,
        "user_id": user_id
    }
