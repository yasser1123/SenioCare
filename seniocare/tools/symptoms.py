"""Symptom Assessment tool - matches symptoms to diseases with severity classification."""

import json
from google.adk.tools import ToolContext
from seniocare.data.database import get_connection


def assess_symptoms(symptoms: list, tool_context: ToolContext) -> dict:
    """
    Matches user-reported symptoms against the disease database and returns
    possible conditions with severity classification.

    Also considers the user's existing conditions (from tool_context.state)
    to weigh related diseases higher in the ranking.

    Args:
        symptoms: List of symptom strings reported by the user
                  (e.g., ["severe headache", "dizziness", "blurry vision"]).
        tool_context: The tool context for state access.

    Returns:
        dict: Assessment results with matched diseases, confidence, and severity.
    """
    # Prevent multiple calls in the same turn
    if tool_context.state.get("_symptom_tool_called"):
        return {
            "status": "already_called",
            "message": "تم استدعاء هذه الأداة بالفعل. استخدم النتيجة السابقة."
        }
    tool_context.state["_symptom_tool_called"] = True

    if not symptoms:
        return {
            "status": "no_symptoms",
            "message": "لم يتم تحديد أعراض للتقييم",
            "matches": []
        }

    # Read user's existing conditions from state
    existing_conditions = tool_context.state.get("user:chronicDiseases", [])
    existing_conditions_lower = [c.lower() for c in existing_conditions]

    # Normalize input symptoms
    symptoms_lower = [s.lower().strip() for s in symptoms]

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Get all diseases with their symptoms
        cursor.execute("SELECT * FROM disease_symptoms")
        all_diseases = [dict(row) for row in cursor.fetchall()]

        matches = []

        for disease in all_diseases:
            disease_symptoms = json.loads(disease["symptoms"])
            disease_symptoms_lower = [s.lower() for s in disease_symptoms]

            # Calculate symptom match
            matched_symptoms = []
            for user_symptom in symptoms_lower:
                for db_symptom in disease_symptoms_lower:
                    # Flexible matching: check if user symptom is contained in
                    # DB symptom or vice versa (handles partial matches)
                    if (user_symptom in db_symptom or
                            db_symptom in user_symptom or
                            _fuzzy_symptom_match(user_symptom, db_symptom)):
                        matched_symptoms.append({
                            "reported": user_symptom,
                            "matched_to": db_symptom
                        })
                        break  # Don't double-count

            if not matched_symptoms:
                continue

            # Calculate base confidence
            match_count = len(matched_symptoms)
            total_disease_symptoms = len(disease_symptoms)
            base_confidence = (match_count / total_disease_symptoms) * 100

            # Boost confidence if disease is related to existing conditions
            condition_boost = 0
            is_condition_related = False
            disease_name_lower = disease["disease_name"].lower()

            for condition in existing_conditions_lower:
                # Check if the disease name or description relates to existing condition
                description = (disease.get("description") or "").lower()
                if (condition in disease_name_lower or
                        condition in description or
                        _condition_relates_to_disease(condition, disease_name_lower)):
                    condition_boost = 15  # 15% boost for related conditions
                    is_condition_related = True
                    break

            final_confidence = min(100, base_confidence + condition_boost)

            # Get precautions
            cursor.execute(
                "SELECT precaution FROM disease_precautions WHERE disease_id = %s",
                (disease["disease_id"],)
            )
            precautions = [row["precaution"] for row in cursor.fetchall()]

            matches.append({
                "disease_id": disease["disease_id"],
                "disease_name": disease["disease_name"],
                "severity": disease["severity"],
                "description": disease["description"],
                "matched_symptoms": matched_symptoms,
                "match_count": match_count,
                "total_symptoms": total_disease_symptoms,
                "confidence": round(final_confidence, 1),
                "is_condition_related": is_condition_related,
                "precautions": precautions,
            })

        # Sort by: severity priority first, then confidence
        severity_order = {"EMERGENCY": 0, "URGENT": 1, "MONITOR": 2, "NORMAL": 3}
        matches.sort(key=lambda m: (severity_order.get(m["severity"], 4), -m["confidence"]))

        # Determine overall assessment severity
        if matches:
            top_severity = matches[0]["severity"]
        else:
            top_severity = "UNKNOWN"

        # Limit to top 5 matches
        top_matches = matches[:3]

        return {
            "status": "success",
            "reported_symptoms": symptoms,
            "existing_conditions": existing_conditions,
            "overall_severity": top_severity,
            "matches": top_matches,
            "total_matches": len(matches),
            "is_emergency": top_severity == "EMERGENCY",
            "emergency_action": "اتصل بالطوارئ فوراً (123)" if top_severity == "EMERGENCY" else None,
            "disclaimer": "هذا التقييم للإرشاد فقط وليس تشخيصاً طبياً. استشر طبيبك فوراً."
        }

    finally:
        conn.close()


def _fuzzy_symptom_match(symptom1: str, symptom2: str) -> bool:
    """
    Check if two symptom strings are similar enough to be considered a match.
    Uses keyword overlap approach.
    """
    # Split into words and check for significant overlap
    words1 = set(symptom1.split())
    words2 = set(symptom2.split())

    # Remove common stop words
    stop_words = {"in", "of", "the", "a", "an", "and", "or", "is", "are", "has", "have"}
    words1 = words1 - stop_words
    words2 = words2 - stop_words

    if not words1 or not words2:
        return False

    # Check if at least half of the shorter set overlaps
    overlap = words1 & words2
    min_len = min(len(words1), len(words2))

    return len(overlap) >= max(1, min_len * 0.5)


def _condition_relates_to_disease(condition: str, disease_name: str) -> bool:
    """
    Check if a health condition is related to a disease name.
    Maps common conditions to their related disease patterns.
    """
    condition_disease_map = {
        "diabetes": ["diabetes", "blood sugar", "glucose", "diabetic"],
        "hypertension": ["hypertension", "blood pressure", "hypertensive"],
        "heart disease": ["heart", "cardiac", "cardiovascular"],
        "arthritis": ["arthritis", "joint", "rheumatoid"],
        "kidney disease": ["kidney", "renal"],
        "asthma": ["asthma", "respiratory", "breathing"],
        "osteoporosis": ["osteoporosis", "bone"],
    }

    related_terms = condition_disease_map.get(condition, [])
    return any(term in disease_name for term in related_terms)
