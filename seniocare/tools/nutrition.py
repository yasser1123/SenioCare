"""Nutrition tool - provides condition-aware meal options."""

from google.adk.tools import ToolContext


def get_meal_options(conditions: list, meal_type: str, tool_context: ToolContext) -> dict:
    """
    Returns meal options appropriate for the user's health conditions.
    
    Args:
        conditions: List of health conditions (e.g., ["diabetes", "hypertension"]).
        meal_type: Type of meal - breakfast, lunch, dinner, or snack.
        tool_context: The tool context for state access.
        
    Returns:
        dict: Meal options with recipes and nutritional info.
    """
    # Prevent multiple calls in the same turn
    if tool_context.state.get("_meal_tool_called"):
        return {
            "status": "already_called",
            "message": "تم استدعاء هذه الأداة بالفعل. استخدم النتيجة السابقة لصياغة التوصية."
        }
    tool_context.state["_meal_tool_called"] = True
    # Condition-specific meal database
    meal_database = {
        "diabetes": {
            "breakfast": [
                {"name": "فول مدمس بزيت الزيتون", "name_en": "Foul Medames with Olive Oil",
                 "ingredients": ["فول", "زيت زيتون", "ليمون", "كمون"],
                 "notes": "منخفض السكر، غني بالألياف", "prep_time": "15 min"},
                {"name": "بيض مسلوق مع خبز أسمر", "name_en": "Boiled Eggs with Whole Wheat Bread",
                 "ingredients": ["بيض", "خبز أسمر", "خيار", "طماطم"],
                 "notes": "بروتين عالي، كربوهيدرات معتدلة", "prep_time": "10 min"}
            ],
            "lunch": [
                {"name": "سمك مشوي مع خضار", "name_en": "Grilled Fish with Vegetables",
                 "ingredients": ["سمك", "بروكلي", "جزر", "ليمون"],
                 "notes": "منخفض الدهون، غني بالأوميجا 3", "prep_time": "30 min"}
            ],
            "dinner": [
                {"name": "شوربة عدس", "name_en": "Lentil Soup",
                 "ingredients": ["عدس أصفر", "جزر", "بصل", "كمون", "ليمون"],
                 "notes": "غني بالألياف والبروتين النباتي", "prep_time": "25 min"},
                {"name": "سلطة دجاج مشوي", "name_en": "Grilled Chicken Salad",
                 "ingredients": ["صدور دجاج", "خس", "خيار", "طماطم", "زيت زيتون"],
                 "notes": "منخفض الكربوهيدرات", "prep_time": "20 min"}
            ]
        },
        "hypertension": {
            "dinner": [
                {"name": "سمك مشوي بالأعشاب", "name_en": "Herb-Grilled Fish",
                 "ingredients": ["سمك", "روزماري", "ثوم", "ليمون"],
                 "notes": "بدون ملح، غني بالبوتاسيوم", "prep_time": "25 min"},
                {"name": "خضار مطبوخة على البخار", "name_en": "Steamed Vegetables",
                 "ingredients": ["بروكلي", "جزر", "فاصوليا خضراء"],
                 "notes": "منخفض الصوديوم", "prep_time": "15 min"}
            ]
        },
        "arthritis": {
            "dinner": [
                {"name": "سلمون مشوي", "name_en": "Grilled Salmon",
                 "ingredients": ["سلمون", "زيت زيتون", "كركم", "زنجبيل"],
                 "notes": "مضاد للالتهابات، غني بالأوميجا 3", "prep_time": "20 min"}
            ]
        }
    }
    
    options = []
    for condition in conditions:
        if condition.lower() in meal_database:
            meals = meal_database[condition.lower()].get(meal_type.lower(), [])
            options.extend(meals)
    
    if not options:
        # Default healthy options
        options = [
            {"name": "شوربة خضار", "name_en": "Vegetable Soup",
             "ingredients": ["جزر", "بطاطس", "كوسة", "بصل"],
             "notes": "وجبة صحية متوازنة", "prep_time": "30 min"}
        ]
    
    return {
        "status": "success",
        "meal_type": meal_type,
        "options": options[:3],  # Return max 3 options
        "disclaimer": "استشر طبيبك قبل تغيير نظامك الغذائي"
    }
