"""Drug-Food Interaction tool - checks for interactions between user's drugs and foods."""

from google.adk.tools import ToolContext
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
    # Prevent multiple calls in the same turn
    if tool_context.state.get("_interaction_tool_called"):
        return {
            "status": "already_called",
            "message": "تم استدعاء هذه الأداة بالفعل. استخدم النتيجة السابقة."
        }
    tool_context.state["_interaction_tool_called"] = True

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

    # Extract drug names from medications (handle both string list and dict list)
    drug_names = []
    for med in user_medications:
        if isinstance(med, dict):
            drug_names.append(med.get("name", "").lower())
        else:
            drug_names.append(str(med).lower())

    food_names_lower = [f.lower() for f in food_names]

    conn = get_connection()
    cursor = conn.cursor()

    try:
        interactions_found = []
        safe_combinations = []

        # Query for each drug-food combination
        for drug in drug_names:
            for food in food_names_lower:
                cursor.execute("""
                    SELECT * FROM drug_food_interactions
                    WHERE LOWER(drug_name) = %s AND LOWER(food_name) = %s
                """, (drug, food))

                rows = cursor.fetchall()
                if rows:
                    for row in rows:
                        row = dict(row)
                        interactions_found.append({
                            "drug": row["drug_name"],
                            "food": row["food_name"],
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
