"""Nutrition tool - provides condition-aware meal options from the database."""

import json
from google.adk.tools import ToolContext
from seniocare.data.database import get_connection


def get_meal_options(meal_type: str, tool_context: ToolContext) -> dict:
    """
    Returns meal options appropriate for the user's health conditions,
    allergies, and drug interactions.

    Reads conditions, allergies, and medications from tool_context.state
    (populated by the backend from the user profile).

    Args:
        meal_type: Type of meal - breakfast, lunch, dinner, or snack.
        tool_context: The tool context for state access.

    Returns:
        dict: Compact meal options with key nutrition info (max 3).
    """
    # Prevent multiple calls in the same turn
    if tool_context.state.get("_meal_tool_called"):
        return {
            "status": "already_called",
            "message": "تم استدعاء هذه الأداة بالفعل. استخدم النتيجة السابقة لصياغة التوصية."
        }
    tool_context.state["_meal_tool_called"] = True

    # Read user profile from state
    conditions = tool_context.state.get("user:chronicDiseases", [])
    allergies = tool_context.state.get("user:allergies", [])

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Step 1: Get all meals of the requested type
        cursor.execute(
            "SELECT * FROM meals WHERE meal_type = %s",
            (meal_type.lower(),)
        )
        all_meals = [dict(row) for row in cursor.fetchall()]

        if not all_meals:
            return {
                "status": "no_meals",
                "meal_type": meal_type,
                "options": [],
                "message": f"لا توجد وجبات متاحة من نوع {meal_type}"
            }

        # Step 2: Apply condition-based nutrient filtering
        filtered_meals = all_meals
        applied_rules = []

        for condition in conditions:
            cursor.execute(
                "SELECT * FROM condition_dietary_rules WHERE condition = %s",
                (condition.lower(),)
            )
            rule = cursor.fetchone()
            if rule:
                rule = dict(rule)
                max_values = json.loads(rule["max_values"]) if rule["max_values"] else {}
                applied_rules.append({
                    "condition": condition,
                    "max_values": max_values
                })

                # Filter meals that exceed the max values
                new_filtered = []
                for meal in filtered_meals:
                    passes = True
                    for nutrient, max_val in max_values.items():
                        meal_value = meal.get(nutrient, 0)
                        if meal_value is not None and meal_value > max_val:
                            passes = False
                            break
                    if passes:
                        new_filtered.append(meal)
                filtered_meals = new_filtered

        # Step 3: Exclude meals containing allergens
        excluded_by_allergy = []
        if allergies:
            placeholders = ','.join('%s' for _ in allergies)
            cursor.execute(
                f"SELECT DISTINCT food_name FROM food_allergens WHERE allergen IN ({placeholders})",
                [a.lower() for a in allergies]
            )
            allergen_foods = {row["food_name"].lower() for row in cursor.fetchall()}

            safe_meals = []
            for meal in filtered_meals:
                ingredients = json.loads(meal["ingredients"])
                ingredient_names = [i.lower() for i in ingredients]
                conflicting = [f for f in allergen_foods if f in ingredient_names]
                if conflicting:
                    excluded_by_allergy.append({
                        "meal": meal["name_ar"],
                        "reason": f"يحتوي على مسبب حساسية: {', '.join(conflicting)}"
                    })
                else:
                    safe_meals.append(meal)
            filtered_meals = safe_meals

        # Step 4: Format compact results (max 3 meals)
        options = []
        for meal in filtered_meals[:3]:
            ingredients = json.loads(meal["ingredients"])
            options.append({
                "meal_id": meal["meal_id"],
                "name_ar": meal["name_ar"],
                "category": meal["category"],
                "ingredients": ingredients,
                "nutrition": {
                    "energy_kcal": meal["energy_kcal"],
                    "protein_g": meal["protein_g"],
                    "fat_g": meal["fat_g"],
                    "carbohydrate_g": meal["carbohydrate_g"],
                    "sodium_mg": meal["sodium_mg"],
                    "sugar_g": meal["sugar_g"],
                },
                "prep_time": meal["prep_time"],
                "notes_ar": meal["notes_ar"],
            })

        return {
            "status": "success",
            "meal_type": meal_type,
            "conditions_applied": [r["condition"] for r in applied_rules],
            "allergies_excluded": allergies,
            "options": options,
            "excluded_by_allergy": excluded_by_allergy if excluded_by_allergy else None,
            "total_found": len(options),
            "disclaimer": "استشر طبيبك قبل تغيير نظامك الغذائي"
        }

    finally:
        conn.close()


def get_meal_recipe(meal_id: str, tool_context: ToolContext) -> dict:
    """
    Returns the full recipe for a specific meal by its ID.

    This should be called AFTER get_meal_options to get the complete
    recipe details (cooking steps, tips, full nutrition, ingredients)
    for a selected meal.

    Args:
        meal_id: The ID of the meal (e.g., "M005").
        tool_context: The tool context for state access.

    Returns:
        dict: Full recipe with steps, tips, ingredients, and nutrition.
    """
    # Prevent multiple calls in the same turn
    if tool_context.state.get("_recipe_tool_called"):
        return {
            "status": "already_called",
            "message": "تم استدعاء أداة الوصفة بالفعل. استخدم النتيجة السابقة."
        }
    tool_context.state["_recipe_tool_called"] = True

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM meals WHERE meal_id = %s", (meal_id,))
        meal = cursor.fetchone()

        if not meal:
            return {
                "status": "not_found",
                "message": f"لم يتم العثور على وجبة بالمعرف {meal_id}"
            }

        meal = dict(meal)
        ingredients = json.loads(meal["ingredients"])
        recipe_steps = json.loads(meal["recipe_steps"]) if meal["recipe_steps"] else []

        return {
            "status": "success",
            "meal_id": meal["meal_id"],
            "name_ar": meal["name_ar"],
            "name_en": meal["name_en"],
            "category": meal["category"],
            "ingredients": ingredients,
            "recipe_steps": recipe_steps,
            "recipe_tips": meal["recipe_tips"],
            "nutrition": {
                "energy_kcal": meal["energy_kcal"],
                "protein_g": meal["protein_g"],
                "fat_g": meal["fat_g"],
                "carbohydrate_g": meal["carbohydrate_g"],
                "fiber_g": meal["fiber_g"],
                "sodium_mg": meal["sodium_mg"],
                "sugar_g": meal["sugar_g"],
            },
            "prep_time": meal["prep_time"],
            "notes_ar": meal["notes_ar"],
        }

    finally:
        conn.close()
