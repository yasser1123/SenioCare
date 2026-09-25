"""Medicines named in a reply but not on the profile are flagged (run C: Losartan to a Lisinopril user)."""

from seniocare.medcheck import correction_note, generic_names, unlisted_medications

PROFILE = ["Metformin", "Lisinopril"]


def test_run_c_losartan_case_is_flagged():
    reply = "الأكلة دي آمنة مع الميتفورمين واللوسارتان اللي حضرتك بتاخدهم."
    assert unlisted_medications(reply, PROFILE) == ["losartan"]


def test_profile_medicines_and_their_brands_are_allowed():
    reply = "خد بالك إن الجلوكوفاج (Metformin) والـ Zestril ماشيين كويس مع الأكلة دي."
    assert unlisted_medications(reply, PROFILE) == []


def test_a_medicine_named_by_a_tool_result_is_allowed():
    reply = "الجريب فروت ممكن يتعارض مع الوارفارين."
    tool = '{"interactions": [{"drug_name": "warfarin", "food_name": "grapefruit"}]}'
    assert unlisted_medications(reply, PROFILE, tool) == []
    assert unlisted_medications(reply, PROFILE) == ["warfarin"]


def test_arabic_clitics_and_english_names_are_detected():
    assert generic_names("بالأسبرين") == {"aspirin"}
    assert generic_names("take your Concor") == {"bisoprolol"}


def test_ordinary_replies_are_not_flagged():
    reply = "يا حاج أحمد، الغدا النهارده: فراخ مشوية مع رز بني وسلطة. قلل الملح عشان الضغط والسكر."
    assert generic_names(reply) == set()


def test_correction_note_lists_what_is_on_file():
    assert "Metformin، Lisinopril" in correction_note(PROFILE)
    assert "مفيش أدوية مسجلة" in correction_note([])
