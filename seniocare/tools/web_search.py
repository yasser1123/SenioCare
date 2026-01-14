"""Web search tool - searches for medical information from trusted sources."""

from google.adk.tools import ToolContext


def search_medical_info(query: str, tool_context: ToolContext) -> dict:
    """
    Searches for medical information from trusted sources.
    
    Args:
        query: The medical question or topic to search for.
        tool_context: The tool context for state access.
        
    Returns:
        dict: Search results with citations from trusted medical sources.
    """
    # Prevent multiple calls in the same turn
    if tool_context.state.get("_search_tool_called"):
        return {
            "status": "already_called",
            "message": "تم استدعاء هذه الأداة بالفعل. استخدم النتيجة السابقة لصياغة التوصية."
        }
    tool_context.state["_search_tool_called"] = True
    knowledge_base = {
        "diabetes": {
            "summary": "مرض السكري هو حالة تؤثر على كيفية تعامل الجسم مع سكر الدم (الجلوكوز).",
            "key_points": [
                "حافظ على مستوى السكر في الدم بين 80-130 قبل الوجبات",
                "تناول الأدوية في مواعيدها المحددة",
                "تجنب السكريات والنشويات الزائدة",
                "مارس المشي الخفيف يومياً"
            ],
            "when_to_see_doctor": [
                "إذا كان مستوى السكر أعلى من 300 أو أقل من 70",
                "إذا شعرت بعطش شديد أو تبول متكرر",
                "إذا شعرت بدوخة أو ارتباك"
            ],
            "source": "Mayo Clinic, WHO Guidelines"
        },
        "hypertension": {
            "summary": "ارتفاع ضغط الدم هو حالة يكون فيها ضغط الدم مرتفعاً باستمرار.",
            "key_points": [
                "الضغط الطبيعي أقل من 120/80",
                "قلل من الملح في الطعام",
                "تجنب التوتر والإجهاد",
                "تناول أدوية الضغط بانتظام"
            ],
            "when_to_see_doctor": [
                "إذا كان الضغط أعلى من 180/120",
                "إذا شعرت بصداع شديد مفاجئ",
                "إذا شعرت بألم في الصدر أو ضيق في التنفس"
            ],
            "source": "American Heart Association, WHO"
        },
        "arthritis": {
            "summary": "التهاب المفاصل هو التهاب في واحد أو أكثر من المفاصل.",
            "key_points": [
                "حافظ على وزن صحي لتقليل الضغط على المفاصل",
                "مارس تمارين خفيفة بانتظام",
                "استخدم الكمادات الدافئة لتخفيف الألم",
                "تناول أدوية الالتهاب حسب وصفة الطبيب"
            ],
            "when_to_see_doctor": [
                "إذا زاد الألم بشكل كبير",
                "إذا لاحظت تورماً أو احمراراً جديداً",
                "إذا لم تستطع تحريك المفصل"
            ],
            "source": "Arthritis Foundation, NIH"
        }
    }
    
    # Simple keyword matching
    query_lower = query.lower()
    results = []
    
    for topic, info in knowledge_base.items():
        if topic in query_lower or any(word in query_lower for word in topic.split()):
            results.append({
                "topic": topic,
                "information": info
            })
    
    if results:
        return {
            "status": "success",
            "results": results,
            "disclaimer": "هذه المعلومات للتثقيف فقط وليست بديلاً عن استشارة الطبيب"
        }
    else:
        return {
            "status": "no_results",
            "message": "لم نجد معلومات محددة. يُرجى استشارة طبيبك للحصول على معلومات دقيقة.",
            "suggestion": "جرب البحث عن: السكري، ضغط الدم، التهاب المفاصل"
        }
