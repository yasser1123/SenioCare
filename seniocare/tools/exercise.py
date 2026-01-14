"""Exercise tool - provides safe exercises based on mobility and conditions."""

from google.adk.tools import ToolContext


def get_exercises(mobility_level: str, conditions: list, tool_context: ToolContext) -> dict:
    """
    Returns safe exercises appropriate for the user's mobility level and conditions.
    
    Args:
        mobility_level: User's mobility - "limited", "moderate", or "good".
        conditions: List of health conditions to consider.
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
    conditions = conditions or []
    
    # Exercise database by mobility level
    exercises = {
        "limited": [
            {
                "name": "تمارين التنفس العميق",
                "name_en": "Deep Breathing Exercises",
                "type": "seated",
                "duration": "5 دقائق",
                "steps": [
                    "اجلس بشكل مريح",
                    "تنفس ببطء من الأنف لمدة 4 ثواني",
                    "احبس النفس لمدة 4 ثواني",
                    "أخرج النفس من الفم لمدة 6 ثواني",
                    "كرر 5 مرات"
                ],
                "benefits": "يقلل التوتر ويحسن الأكسجين في الدم",
                "safety": "توقف إذا شعرت بدوخة"
            },
            {
                "name": "تمارين الكاحل",
                "name_en": "Ankle Circles",
                "type": "seated",
                "duration": "3 دقائق",
                "steps": [
                    "اجلس على كرسي ثابت",
                    "ارفع قدمك قليلاً عن الأرض",
                    "أدر الكاحل في دوائر 10 مرات",
                    "بدل الاتجاه",
                    "كرر مع القدم الأخرى"
                ],
                "benefits": "يحسن الدورة الدموية في الساقين",
                "safety": "لا تفرط في الحركة"
            }
        ],
        "moderate": [
            {
                "name": "المشي في المكان",
                "name_en": "Marching in Place",
                "type": "standing",
                "duration": "5 دقائق",
                "steps": [
                    "قف بجانب كرسي للاستناد",
                    "ارفع ركبتك اليمنى",
                    "أنزلها وارفع ركبتك اليسرى",
                    "استمر ببطء لمدة 5 دقائق"
                ],
                "benefits": "يحسن اللياقة القلبية والتوازن",
                "safety": "استخدم الكرسي للتوازن"
            },
            {
                "name": "تمارين رفع الذراعين",
                "name_en": "Arm Raises",
                "type": "standing",
                "duration": "3 دقائق",
                "steps": [
                    "قف أو اجلس بشكل مستقيم",
                    "ارفع ذراعيك للأمام ببطء",
                    "ارفعهما فوق رأسك",
                    "أنزلهما ببطء",
                    "كرر 10 مرات"
                ],
                "benefits": "يقوي عضلات الكتف والذراع",
                "safety": "لا ترفع أعلى من راحتك"
            }
        ],
        "good": [
            {
                "name": "المشي الخفيف",
                "name_en": "Light Walking",
                "type": "walking",
                "duration": "15-20 دقيقة",
                "steps": [
                    "اختر مكاناً مستوياً وآمناً",
                    "امشِ بخطوات ثابتة",
                    "حافظ على وتيرة مريحة",
                    "استرح كل 5 دقائق إذا لزم الأمر"
                ],
                "benefits": "يحسن صحة القلب والمزاج",
                "safety": "تجنب الأسطح غير المستوية"
            }
        ]
    }
    
    # Get exercises for mobility level
    level = mobility_level.lower() if mobility_level else "limited"
    recommended = exercises.get(level, exercises["limited"])
    
    # Filter based on conditions
    if "arthritis" in [c.lower() for c in conditions]:
        recommended = [e for e in recommended if e["type"] in ["seated", "standing"]]
    
    return {
        "status": "success",
        "mobility_level": level,
        "exercises": recommended[:2],  # Return max 2 exercises
        "general_advice": "استشر طبيبك قبل بدء أي برنامج تمارين جديد",
        "warning": "توقف فوراً إذا شعرت بألم في الصدر أو ضيق في التنفس"
    }
