"""Drug-Food Interaction tool - checks for interactions between user's drugs and foods."""

from google.adk.tools import ToolContext

from seniocare.tools._guards import already_called_this_turn, mark_called
from seniocare.tools._text import normalize_drug_name, normalize_text, phrase_match
from seniocare.data.database import get_connection


def check_drug_food_interaction(food_names: list, tool_context: ToolContext) -> dict:
    """
    Checks if any of the user's current medications interact with specified foods.

    Reads the user's medication list from tool_context.state and checks each
    drug-food combination against the interaction database.

    Args:
        food_names: List of food names to check (e.g., ["grapefruit", "banana"]).
        tool_context: The tool context for state access.

    Returns:
        dict: Interaction results with severity and advice.
    """
    # Prevent multiple calls in the same turn (per-turn guard, AUDIT C-04)
    if already_called_this_turn(tool_context.state, "_interaction_tool_called"):
        return {
            "status": "already_called",
            "message": "تم استدعاء هذه الأداة بالفعل. استخدم النتيجة السابقة."
        }
    mark_called(tool_context.state, "_interaction_tool_called")

    # Read user's medications from state
    user_medications = tool_context.state.get("user:medications", [])
    if not user_medications:
        return {
            "status": "no_medications",
            "message": "لا توجد أدوية مسجلة للمستخدم",
            "interactions": []
        }

    if not food_names:
        return {
            "status": "no_foods",
            "message": "لم يتم تحديد أطعمة للفحص",
            "interactions": []
        }

    # Extract drug names from medications (handle both string list and dict list).
    # Names are normalised ("Metformin 500mg" -> "metformin") so the join is not
    # defeated by dose suffixes or brand/form words (AUDIT C-14).
    drug_names = []
    for med in user_medications:
        raw = med.get("name", "") if isinstance(med, dict) else str(med)
        normalised = normalize_drug_name(raw)
        if normalised and normalised not in drug_names:
            drug_names.append(normalised)

    food_names_lower = [normalize_text(f) for f in food_names if str(f).strip()]

    conn = get_connection()
    cursor = conn.cursor()

    try:
        interactions_found = []
        safe_combinations = []

        # One query for all of the user's drugs (was one query per drug x food,
        # AUDIT R-02); food matching happens in Python at word level so
        # "spinach salad" still hits the "spinach" row.
        cursor.execute(
            "SELECT * FROM drug_food_interactions WHERE LOWER(drug_name) = ANY(%s)",
            (drug_names,),
        )
        rows_by_drug: dict = {}
        for row in cursor.fetchall():
            row = dict(row)
            rows_by_drug.setdefault(normalize_drug_name(row["drug_name"]), []).append(row)

        for drug in drug_names:
            for food in food_names_lower:
                hits = [r for r in rows_by_drug.get(drug, []) if phrase_match(food, r["food_name"])]
                if hits:
                    for row in hits:
                        interactions_found.append({
                            "drug": row["drug_name"],
                            "food": row["food_name"],
                            "food_reported": food,
                            "effect": row["effect"],
                            "severity": row["severity"],
                            "conclusion": row["conclusion"],
                            "advice": row["advice"],
                        })
                else:
                    safe_combinations.append({
                        "drug": drug,
                        "food": food,
                        "status": "no interaction found"
                    })

        # Separate harmful and positive interactions
        harmful = [i for i in interactions_found if i["effect"] == "negative"]
        positive = [i for i in interactions_found if i["effect"] == "positive"]
        neutral = [i for i in interactions_found if i["effect"] == "no_effect"]

        has_severe = any(i["severity"] == "severe" for i in harmful)

        return {
            "status": "success",
            "drugs_checked": drug_names,
            "foods_checked": food_names_lower,
            "harmful_interactions": harmful,
            "positive_interactions": positive,
            "neutral_interactions": neutral,
            "safe_combinations": safe_combinations[:3],  # Limit output
            "has_severe_interaction": has_severe,
            "total_interactions": len(interactions_found),
            "warning": "تحذير: تم العثور على تفاعلات خطيرة مع أدويتك!" if has_severe else None,
            "disclaimer": "استشر طبيبك أو الصيدلي للحصول على معلومات أكثر دقة"
        }

    finally:
        conn.close()
