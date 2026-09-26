"""Deterministic safety layer (seniocare/safety.py): screen, fixed replies, sanitiser.

The pipeline paths that use it run under the real ADK in tests_adk/.
"""

import pytest
from seniocare.safety import (
    AMBULANCE,
    MENTAL_HEALTH_HOTLINE,
    build_emergency_reply,
    build_self_harm_reply,
    has_foreign_emergency_number,
    screen,
    strip_foreign_emergency_numbers,
)

# ------------------------------------------------------------------- screen


@pytest.mark.parametrize("msg,kind", [
    ("عندي ألم شديد في صدري ومش قادر أتنفس", "chest"),
    ("صدري بيوجعني جامد", "chest"),
    ("مش قادر أتنفس خالص", "breathing"),
    ("وشي مايل وإيدي مش بترفع ومش قادر أتكلم كويس", "stroke"),
    ("جدي وقع من على السلم ودماغه بتنزف", "fall_head"),
    ("مش عايز أعيش تاني، تعبت من كل حاجة", "self_harm"),
    ("I want to kill myself", "self_harm"),
    ("خدت علبة البرشام كلها", "poisoning"),
    ("I have chest pain", "chest"),
])
def test_screen_catches_clear_emergencies(msg, kind):
    hit = screen(msg)
    assert hit is not None and hit.kind == kind


@pytest.mark.parametrize("msg", [
    "عايز أكلة كويسة على الغدا",
    "إيه أحسن تمارين لركبتي؟",
    "حاسس بضيق في صدري شوية بس عادي مش حاجة كبيرة",   # ambiguous: left to the Orchestrator
    "إيه أعراض الجلطة؟",
    "أنا زهقان ومليش نفس أعمل حاجة",
    "",
])
def test_screen_leaves_ordinary_and_ambiguous_messages_to_the_llm(msg):
    assert screen(msg) is None


# ------------------------------------------------------------------ replies


def test_emergency_reply_leads_with_the_ambulance_number():
    text = build_emergency_reply("chest", name="أحمد")
    assert text.splitlines()[0].count(AMBULANCE) == 1
    assert "أحمد" in text
    assert not has_foreign_emergency_number(text)


def test_emergency_reply_mentions_caregivers_only_if_there_are_any():
    assert "عن رعايتك" not in build_emergency_reply("generic")
    assert "عن رعايتك" in build_emergency_reply("generic", has_caregivers=True)


def test_self_harm_reply_has_hotline_and_ambulance_and_no_physical_boilerplate():
    for gender in ("male", "female", None):
        text = build_self_harm_reply(name="سعاد", gender=gender)
        assert MENTAL_HEALTH_HOTLINE in text and AMBULANCE in text
        assert "متتحركش" not in text
    assert "حاسة" in build_self_harm_reply(gender="female")


def test_foreign_numbers_are_replaced_and_egyptian_ones_kept():
    assert strip_foreign_emergency_numbers("اتصل بـ 911 أو 112 أو 997") == "اتصل بـ 123 أو 123 أو 123"
    assert strip_foreign_emergency_numbers("الشرطة 122 والمطافي 180") == "الشرطة 122 والمطافي 180"
    assert strip_foreign_emergency_numbers("1120 سعر حراري و 9110") == "1120 سعر حراري و 9110"


@pytest.mark.parametrize("msg", [
    "بفكر أخلص من حياتي، محدش محتاجني",
    "ياريتني أموت، بقيت عبء على ولادي",
    "I don't want to live anymore",
    "نفسي أموت وأرتاح",
])
def test_passive_and_indirect_self_harm_is_screened(msg):
    hit = screen(msg)
    assert hit is not None and hit.kind == "self_harm"


def test_self_harm_reply_speaker_gender_is_consistent():
    # F-21: the assistant speaks as masculine ("مهتم", "موجود"); "سامعاكي" is a
    # feminine speaker form and mixed genders in one sentence.
    from seniocare.safety import build_self_harm_reply
    female = build_self_harm_reply(name="فاطمة", gender="female")
    male = build_self_harm_reply(name="أحمد", gender="male")
    assert "سامعاكي" not in female and "معاكي" in female and "مهتم بيكي" in female
    assert "معاك " in male and "مهتم بيك" in male
