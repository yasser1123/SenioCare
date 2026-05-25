"""
Seed Reports — Inject sample health reports into the database for testing.

Usage:
    python seed_reports.py                  # Seeds for default user (elder_123)
    python seed_reports.py --user user_456  # Seeds for a specific user
    python seed_reports.py --clear          # Delete all seed data first

This creates realistic report data in both health_reports and
medical_reports tables so the Flutter team can test:
  - GET /reports/{user_id}              (list reports)
  - GET /reports/{user_id}/{report_id}  (report detail)
  - GET /reports/medical/{user_id}      (medical image reports)

WITHOUT needing the AI model to be running.
"""

import argparse
import json
from datetime import datetime, timedelta

from seniocare.data.database import get_connection
from seniocare.tools.reports import ensure_health_reports_table


# =============================================================================
# SAMPLE HEALTH REPORTS (AI-generated style)
# =============================================================================

def _get_sample_health_reports(user_id: str) -> list[dict]:
    """Return sample health reports with realistic Arabic markdown content."""
    now = datetime.now()

    return [
        {
            "report_id": "HR_seed_daily_001",
            "user_id": user_id,
            "report_type": "daily",
            "period_start": (now - timedelta(days=1)).strftime("%Y-%m-%d"),
            "period_end": now.strftime("%Y-%m-%d"),
            "title": "تقرير يومي — أحمد",
            "content": (
                "📊 تقرير يومي — أحمد\n\n"
                "يا فندم، ده ملخص يومك 💚\n\n"
                "📊 نظرة عامة:\n"
                "الحمد لله، اليوم كان كويس. حضرتك اتكلمت مع النظام عن الأكل والأدوية.\n\n"
                "🍽️ التغذية:\n"
                "• اطلعت على وجبة فراخ مشوية مع سلطة خضرا\n"
                "• الوجبة مناسبة لمرضى السكر والضغط\n\n"
                "💊 الأدوية:\n"
                "• Metformin 500mg — الجرعة منتظمة\n"
                "• Lisinopril 10mg — ماشي تمام\n\n"
                "💪 النشاط البدني:\n"
                "• مفيش تمارين اتعملت النهاردة\n"
                "• ننصح بمشي خفيف 15 دقيقة\n\n"
                "📌 التوصيات:\n"
                "1. حافظ على مواعيد الأدوية\n"
                "2. اشرب مية كفاية (8 كوبايات)\n"
                "3. حاول تمشي شوية بكرة الصبح\n\n"
                "ربنا يديم عليك الصحة يا فندم 💚"
            ),
            "overall_status": "good",
            "key_highlights": "[]",
            "recommendations": "[]",
            "doctor_notes": "",
            "generated_at": now.isoformat(),
            "source_data": json.dumps({"report_type": "daily", "seed": True}),
        },
        {
            "report_id": "HR_seed_weekly_001",
            "user_id": user_id,
            "report_type": "weekly",
            "period_start": (now - timedelta(days=7)).strftime("%Y-%m-%d"),
            "period_end": now.strftime("%Y-%m-%d"),
            "title": "تقرير أسبوعي — أحمد",
            "content": (
                "📊 تقرير أسبوعي — أحمد\n\n"
                "يا فندم، ده ملخص الأسبوع اللي فات 💚\n\n"
                "📊 نظرة عامة:\n"
                "الأسبوع ده كان كويس الحمد لله. حضرتك تفاعلت مع النظام 12 مرة "
                "وسألت عن وجبات وتمارين وأدوية.\n\n"
                "🍽️ التغذية:\n"
                "• اطلعت على 5 وجبات صحية خلال الأسبوع\n"
                "• الوجبات كلها مناسبة لحالتك الصحية\n"
                "• نوعت بين فراخ وسمك وخضار — ممتاز 👏\n\n"
                "💪 النشاط البدني:\n"
                "• اطلعت على تمارين مشي خفيف\n"
                "• ننصح تزود المدة لـ 20 دقيقة يومياً\n\n"
                "💊 الأدوية:\n"
                "• Metformin 500mg — منتظم\n"
                "• Lisinopril 10mg — منتظم\n"
                "• ⚠️ تجنب الجريب فروت مع Lisinopril\n\n"
                "🩺 التحاليل:\n"
                "• تحليل دم يوم 2026-05-20:\n"
                "  - السكر: 150 mg/dL (مرتفع شوية)\n"
                "  - HbA1c: 7.2% (محتاج متابعة)\n\n"
                "📌 التوصيات:\n"
                "1. حافظ على نظام الأكل الصحي — شاطر 👏\n"
                "2. زود المشي لـ 20 دقيقة يومياً\n"
                "3. تابع مع الدكتور بخصوص السكر\n"
                "4. اشرب مية كتير — 8 كوبايات على الأقل\n"
                "5. ابعد عن الحاجات المالحة عشان الضغط\n\n"
                "ربنا يديم عليك الصحة يا فندم 💚"
            ),
            "overall_status": "moderate",
            "key_highlights": "[]",
            "recommendations": "[]",
            "doctor_notes": "",
            "generated_at": now.isoformat(),
            "source_data": json.dumps({"report_type": "weekly", "seed": True}),
        },
        {
            "report_id": "HR_seed_monthly_001",
            "user_id": user_id,
            "report_type": "monthly",
            "period_start": (now - timedelta(days=30)).strftime("%Y-%m-%d"),
            "period_end": now.strftime("%Y-%m-%d"),
            "title": "تقرير شهري — أحمد",
            "content": (
                "📈 تقرير شهري — أحمد\n\n"
                "يا فندم، ده ملخص الشهر اللي فات 💚\n\n"
                "📊 نظرة عامة:\n"
                "الشهر ده حضرتك كنت منتظم في التواصل مع النظام الحمد لله. "
                "اتكلمنا 45 مرة عن مواضيع مختلفة.\n\n"
                "🍽️ التغذية (ملخص الشهر):\n"
                "• اطلعت على 22 وجبة صحية\n"
                "• 85% من الوجبات كانت مناسبة لحالتك\n"
                "• نوعت بين البروتينات والخضار — ممتاز\n\n"
                "💪 النشاط البدني:\n"
                "• اطلعت على تمارين 8 مرات\n"
                "• المشي الخفيف هو النشاط الأكتر\n"
                "• ننصح تضيف تمارين تقوية خفيفة\n\n"
                "💊 الأدوية:\n"
                "• Metformin 500mg — انتظام عالي\n"
                "• Lisinopril 10mg — منتظم\n"
                "• ⚠️ اتنبهت لتفاعل مع الجريب فروت\n\n"
                "🩺 التحاليل والفحوصات:\n"
                "• تحليل دم (2026-05-20): سكر 150, HbA1c 7.2%\n"
                "• الاتجاه العام: تحسن طفيف عن الشهر اللي فات\n\n"
                "📌 التوصيات للشهر القادم:\n"
                "1. زود المشي لـ 25 دقيقة يومياً\n"
                "2. تابع مع دكتور السكر بخصوص HbA1c\n"
                "3. حافظ على نظام الأكل الممتاز ده\n"
                "4. اعمل تحليل دم كامل الشهر الجاي\n"
                "5. خلي بالك من الملح والسكريات\n\n"
                "ربنا يديم عليك الصحة ويقويك يا فندم 💚"
            ),
            "overall_status": "good",
            "key_highlights": "[]",
            "recommendations": "[]",
            "doctor_notes": "",
            "generated_at": (now - timedelta(hours=2)).isoformat(),
            "source_data": json.dumps({"report_type": "monthly", "seed": True}),
        },
        {
            "report_id": "HR_seed_emergency_001",
            "user_id": user_id,
            "report_type": "emergency",
            "period_start": now.strftime("%Y-%m-%d"),
            "period_end": now.strftime("%Y-%m-%d"),
            "title": "🚨 تقرير طوارئ — أحمد",
            "content": (
                "🚨 تقرير طوارئ — أحمد\n\n"
                "تم رصد حالة طوارئ أثناء المحادثة ⚠️\n\n"
                "📋 تفاصيل الحالة:\n"
                "• المستخدم اشتكى من ألم شديد في الصدر\n"
                "• مصاحب لضيق في التنفس\n"
                "• الأعراض بدأت من ساعة تقريباً\n\n"
                "🩺 التقييم:\n"
                "• الحالة: حرجة — محتاج تدخل طبي فوري\n"
                "• مع الأخذ في الاعتبار:\n"
                "  - تاريخ مرضي: ضغط عالي + سكر\n"
                "  - أدوية: Metformin + Lisinopril\n\n"
                "🚑 الإجراءات الفورية:\n"
                "1. اتصل بالإسعاف فوراً (123)\n"
                "2. اقعد في وضع مريح — متتحركش كتير\n"
                "3. لو عندك أسبرين — خد حبة تحت اللسان\n"
                "4. افتح الشبابيك عشان تهوية\n"
                "5. خلي حد معاك لحد ما الإسعاف يوصل\n\n"
                "⚠️ تم إرسال إشعار لمقدمي الرعاية\n\n"
                "ربنا يشفيك ويقومك بالسلامة يا فندم 💚"
            ),
            "overall_status": "critical",
            "key_highlights": "[]",
            "recommendations": "[]",
            "doctor_notes": "",
            "generated_at": now.isoformat(),
            "source_data": json.dumps({"report_type": "emergency", "seed": True}),
        },
    ]


# =============================================================================
# SAMPLE MEDICAL REPORTS (from image analysis)
# =============================================================================

def _get_sample_medical_reports(user_id: str) -> list[dict]:
    """Return sample medical reports from image analysis."""
    now = datetime.now()

    return [
        {
            "report_id": "MR_seed_blood_001",
            "user_id": user_id,
            "report_type": "blood_test",
            "report_date": (now - timedelta(days=4)).strftime("%Y-%m-%d"),
            "key_findings": (
                "1. Fasting Glucose: 150 mg/dL (مرتفع — الطبيعي 70-100)\n"
                "2. HbA1c: 7.2% (مرتفع — الهدف أقل من 7%)\n"
                "3. Total Cholesterol: 195 mg/dL (طبيعي)\n"
                "4. Blood Pressure: 135/85 mmHg (مرتفع قليلاً)\n"
                "5. Creatinine: 1.0 mg/dL (طبيعي)"
            ),
            "lab_values": json.dumps([
                {"name": "Glucose (Fasting)", "value": "150", "unit": "mg/dL", "status": "high", "reference": "70-100"},
                {"name": "HbA1c", "value": "7.2", "unit": "%", "status": "high", "reference": "<7.0"},
                {"name": "Total Cholesterol", "value": "195", "unit": "mg/dL", "status": "normal", "reference": "<200"},
                {"name": "Blood Pressure", "value": "135/85", "unit": "mmHg", "status": "borderline", "reference": "<130/80"},
                {"name": "Creatinine", "value": "1.0", "unit": "mg/dL", "status": "normal", "reference": "0.7-1.3"},
            ]),
            "health_summary": "السكر التراكمي مرتفع شوية ومحتاج متابعة. الكولسترول والكلى طبيعي الحمد لله.",
            "severity_level": "moderate",
            "recommendations": "متابعة السكر التراكمي مع الدكتور، الالتزام بالميتفورمين، تقليل السكريات والنشويات",
            "scanned_at": (now - timedelta(days=4)).isoformat(),
            "raw_response": "",
        },
        {
            "report_id": "MR_seed_cbc_001",
            "user_id": user_id,
            "report_type": "cbc",
            "report_date": (now - timedelta(days=10)).strftime("%Y-%m-%d"),
            "key_findings": (
                "1. Hemoglobin: 13.5 g/dL (طبيعي)\n"
                "2. WBC: 7,200/μL (طبيعي)\n"
                "3. Platelets: 250,000/μL (طبيعي)\n"
                "4. RBC: 4.8 million/μL (طبيعي)"
            ),
            "lab_values": json.dumps([
                {"name": "Hemoglobin", "value": "13.5", "unit": "g/dL", "status": "normal", "reference": "13-17"},
                {"name": "WBC", "value": "7200", "unit": "/μL", "status": "normal", "reference": "4000-11000"},
                {"name": "Platelets", "value": "250000", "unit": "/μL", "status": "normal", "reference": "150000-400000"},
                {"name": "RBC", "value": "4.8", "unit": "M/μL", "status": "normal", "reference": "4.5-5.5"},
            ]),
            "health_summary": "صورة الدم الكاملة طبيعية تماماً الحمد لله. مفيش أنيميا أو مشاكل.",
            "severity_level": "normal",
            "recommendations": "لا يوجد إجراء مطلوب — النتائج ممتازة",
            "scanned_at": (now - timedelta(days=10)).isoformat(),
            "raw_response": "",
        },
    ]


# =============================================================================
# SEED FUNCTIONS
# =============================================================================

def seed_health_reports(user_id: str, clear: bool = False) -> int:
    """Insert sample health reports into the database.

    Args:
        user_id: The user to seed data for.
        clear: If True, delete existing seed data first.

    Returns:
        Number of reports inserted.
    """
    ensure_health_reports_table()
    conn = get_connection()
    cursor = conn.cursor()

    if clear:
        cursor.execute(
            "DELETE FROM health_reports WHERE report_id LIKE 'HR_seed_%%' AND user_id = %s",
            (user_id,),
        )
        print(f"  Cleared existing seed health reports for {user_id}")

    reports = _get_sample_health_reports(user_id)
    inserted = 0

    for r in reports:
        try:
            cursor.execute(
                """
                INSERT INTO health_reports
                    (report_id, user_id, report_type, period_start, period_end,
                     title, content, overall_status, key_highlights,
                     recommendations, doctor_notes, generated_at, source_data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (report_id) DO NOTHING
                """,
                (
                    r["report_id"], r["user_id"], r["report_type"],
                    r["period_start"], r["period_end"],
                    r["title"], r["content"], r["overall_status"],
                    r["key_highlights"], r["recommendations"],
                    r["doctor_notes"], r["generated_at"], r["source_data"],
                ),
            )
            inserted += 1
        except Exception as e:
            print(f"  Warning: {r['report_id']}: {e}")

    conn.commit()
    cursor.close()
    conn.close()
    return inserted


def seed_medical_reports(user_id: str, clear: bool = False) -> int:
    """Insert sample medical reports (image analysis) into the database.

    Args:
        user_id: The user to seed data for.
        clear: If True, delete existing seed data first.

    Returns:
        Number of reports inserted.
    """
    conn = get_connection()
    cursor = conn.cursor()

    if clear:
        cursor.execute(
            "DELETE FROM medical_reports WHERE report_id LIKE 'MR_seed_%%' AND user_id = %s",
            (user_id,),
        )
        print(f"  Cleared existing seed medical reports for {user_id}")

    reports = _get_sample_medical_reports(user_id)
    inserted = 0

    for r in reports:
        try:
            cursor.execute(
                """
                INSERT INTO medical_reports
                    (report_id, user_id, report_type, report_date,
                     key_findings, lab_values, health_summary,
                     severity_level, recommendations, scanned_at, raw_response)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (report_id) DO NOTHING
                """,
                (
                    r["report_id"], r["user_id"], r["report_type"],
                    r["report_date"], r["key_findings"], r["lab_values"],
                    r["health_summary"], r["severity_level"],
                    r["recommendations"], r["scanned_at"], r["raw_response"],
                ),
            )
            inserted += 1
        except Exception as e:
            print(f"  Warning: {r['report_id']}: {e}")

    conn.commit()
    cursor.close()
    conn.close()
    return inserted


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Seed report data for testing")
    parser.add_argument("--user", default="elder_123", help="User ID to seed data for (default: elder_123)")
    parser.add_argument("--clear", action="store_true", help="Clear existing seed data first")
    args = parser.parse_args()

    user_id = args.user
    print(f"Seeding report data for user: {user_id}")
    print()

    # Health reports (AI-generated reports)
    count = seed_health_reports(user_id, clear=args.clear)
    print(f"  Health reports: {count} inserted (daily, weekly, monthly, emergency)")

    # Medical reports (image analysis)
    count = seed_medical_reports(user_id, clear=args.clear)
    print(f"  Medical reports: {count} inserted (blood_test, cbc)")

    print()
    print("Done! Test with:")
    print(f"  GET /reports/{user_id}")
    print(f"  GET /reports/{user_id}/HR_seed_daily_001")
    print(f"  GET /reports/{user_id}/HR_seed_weekly_001")
    print(f"  GET /reports/{user_id}/HR_seed_monthly_001")
    print(f"  GET /reports/{user_id}/HR_seed_emergency_001")
    print(f"  GET /reports/medical/{user_id}")


if __name__ == "__main__":
    main()
