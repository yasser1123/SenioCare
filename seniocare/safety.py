"""
Deterministic safety layer around the LLM pipeline. Pure: no ADK imports.

Three things here must never depend on a generative model:

1. ``screen()`` — a keyword screen over the user's own words, run BEFORE the
   Orchestrator. A clear first-person emergency ("صدري بيوجعني", "مش قادر
   أتنفس") or self-harm statement is routed immediately, without waiting for
   an LLM call and independently of whether the Orchestrator's output parses.
   In run A the Orchestrator was truncated on every turn and 4 of 6
   emergencies went unrecognised (docs/RESULTS.md §3).

2. The emergency and self-harm replies. In run C the Formatter gave Egypt's
   ambulance number in 1 of 7 emergency replies, foreign numbers (997, 112,
   911) in 3, and "stay calm, don't move much" to a self-harm disclosure
   (FINDINGS F-11). These replies are now fixed templates: the number first,
   then short first-aid steps chosen by category, then the caregiver line.
   The model decides *that* it is an emergency; code decides *what is said*.

3. ``strip_foreign_emergency_numbers()`` — applied to every reply the user
   sees, so a number that does not work in Egypt is never shown.

Sources for the fixed content: Egypt's ambulance number 123; the Ministry of
Health and Population's 24-hour mental-health hotline 16328 (State
Information Service, 12 Apr 2026). First-aid steps are generic lay steps
(rest, don't drive, note the stroke onset time, press on a wound) and should
be reviewed by a clinician before any real deployment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from seniocare.tools._text import normalize_text

AMBULANCE = "123"
MENTAL_HEALTH_HOTLINE = "16328"

# ---------------------------------------------------------------------------
# 1. Keyword screen
# ---------------------------------------------------------------------------
# Patterns are matched against normalize_text(message): lower-case, no
# tashkeel, alef/taa-marbuta/yaa unified, punctuation removed. So write
# "الم" for "ألم", "اتنفس" for "أتنفس", "ه" for final "ة".

_SCREEN: list[tuple[str, str]] = [
    ("self_harm", r"(عايز|عاوز|عايزه|عاوزه|نفسي|ناوي|ناويه|هقوم)\s+(اموت|انتحر|اقتل نفسي|اخلص (من )?(حياتي|نفسي))"),
    ("self_harm", r"\b(هنتحر|هموت نفسي|انتحار|الانتحار|اقتل نفسي|اذي نفسي|اءذي نفسي)\b"),
    ("self_harm", r"مش (عايز|عاوز|عايزه|عاوزه) (اعيش|اكمل)"),
    ("self_harm", r"اخلص\s+من\s+(حياتي|نفسي|عمري)"),
    ("self_harm", r"(بفكر|افكر|فكرت)\s+(في\s+|ف\s*)?(الانتحار|اموت|انتحر|اقتل نفسي)"),
    ("self_harm", r"(ياريتني|يا ريتني|ياريت|يا ريت)\s+(اموت|مت|كنت مت)"),
    ("self_harm", r"\b(suicide|suicidal|kill myself|end my life|hurt myself|self harm|want to die|don t want to live|dont want to live)\b"),
    ("chest", r"(الم|وجع|ضغط|تقل|نغزه|حرقان)\s+(جامد\s+|شديد\s+)?(في|على|ف)\s+صدري"),
    ("chest", r"صدري\s+(بيوجعني|واجعني|مقبوض|تقيل|بيتقل)"),
    ("chest", r"\b(chest pain|pain in my chest|chest (is )?tight)"),
    ("breathing", r"(مش\s+(قادر|قادره)|مبقتش\s+(قادر|قادره))\s+(ا)?تنفس"),
    ("breathing", r"(نفسي|النفس)\s+(مقطوع|بيتقطع|محبوس|اتقطع)"),
    ("breathing", r"\b(بتخنق|باتخنق|بختنق)\b"),
    ("breathing", r"\b(can ?not|can t|cant) breathe\b"),
    ("stroke", r"(وشي|بقي|فمي|وشه|بقه)\s+(مايل|اتعوج|معوج|اتلوي)"),
    ("stroke", r"(ايدي|دراعي|رجلي|ايده|دراعه|نص جسمي)\s+(اتشلت|اتشل|مش حاسس بيها|مش حاسه بيها|تقلت فجاه)"),
    ("stroke", r"(مش\s+(قادر|قادره)\s+(اتكلم|انطق))|(كلامي|لساني)\s+(تقيل|اتلخبط|اتقل)"),
    ("unconscious", r"\b(اغمي|اغمى|أغمي)\s+(عليه|عليا|عليها)\b|\bفقد(ت)?\s+الوعي\b|وقع\s+ومش\s+(بيرد|بيفوق)"),
    ("unconscious", r"\b(fainted|passed out|unconscious)\b"),
    ("bleeding", r"(نزيف|بينزف|بنزف)\s+(جامد|شديد|كتير|مش (عايز|راضي) يقف|مش بيقف)"),
    ("bleeding", r"\bbleeding (heavily|a lot|won t stop)\b"),
    ("fall_head", r"وقعت\s+(و\s*)?(اتخبطت|خبطت)\s+(على\s+)?(دماغي|راسي)"),
    ("fall_head", r"وقعت\s+(و\s*)?مش\s+(قادر|قادره)\s+(اقوم|اتحرك)"),
    ("fall_head", r"(دماغ|راس)(ي|ه|ها)?\s+(بتنزف|بينزف|اتفتحت|بتجيب دم)"),
    ("fall_head", r"\bوقع(ت)?\s+(من على|من فوق|ع)\s+(السلم|سلم|السرير)\b.*\b(نزيف|بتنزف|بينزف|مش بيرد|مش قادر)"),
    ("allergy", r"(وشي|شفايفي|لساني|زوري|عينيا)\s+(ورم|وارم|وارمه|اتنفخ|اتنفخت|بيورم)"),
    ("poisoning", r"(خدت|بلعت|شربت)\s+(كل|علبه|شريط|كميه كبيره)\s+(من\s+)?(الدوا|البرشام|الحبوب|دوا)"),
    ("poisoning", r"\b(overdose|poisoned)\b"),
]
_SCREEN_RE = [(kind, re.compile(p)) for kind, p in _SCREEN]


@dataclass(frozen=True)
class ScreenResult:
    kind: str       # "self_harm" | "chest" | "breathing" | ... | "generic"
    matched: str    # the text span that matched

    @property
    def is_self_harm(self) -> bool:
        return self.kind == "self_harm"


def screen(message: str) -> Optional[ScreenResult]:
    """First matching emergency pattern in the user's message, or None."""
    text = " " + normalize_text(message or "") + " "
    for kind, rx in _SCREEN_RE:
        m = rx.search(text)
        if m:
            return ScreenResult(kind, m.group(0).strip())
    return None


def category_for(message: str) -> str:
    """Emergency category for choosing first-aid steps ("generic" if unknown)."""
    hit = screen(message)
    return hit.kind if hit else "generic"


# ---------------------------------------------------------------------------
# 2. Fixed replies
# ---------------------------------------------------------------------------

_FIRST_AID: dict[str, list[str]] = {
    "chest": ["اقعد وارتاح ومتعملش أي مجهود.", "فك أي هدوم ضيقة.", "متسوقش العربية بنفسك."],
    "breathing": ["اقعد معدول ومايل لقدام شوية.", "افتح الشباك وفك أي هدوم ضيقة.", "حاول تاخد نفس بهدوء وببطء."],
    "stroke": ["افتكر الساعة اللي الأعراض بدأت فيها وقولها للإسعاف.", "متاكلش ومتشربش أي حاجة.",
               "اقعد أو نام على جنبك في مكان آمن."],
    "unconscious": ["لو الشخص مش بيرد بس بيتنفس، نيّمه على جنبه.", "متدّيلوش أكل أو شرب.",
                    "خليك جنبه لحد ما الإسعاف توصل."],
    "bleeding": ["اضغط على الجرح جامد بقماشة نضيفة ومتشيلهاش.", "لو تقدر، ارفع المكان المصاب لفوق."],
    "fall_head": ["متتحركش لو فيه وجع في رقبتك أو ضهرك.", "خلي حد يفضل جنبك ومتقومش لوحدك."],
    "allergy": ["لو معاك حقنة حساسية موصوفة لك من الدكتور، استخدمها زي ما هو قال.",
                "اقعد معدول لو التنفس صعب."],
    "poisoning": ["متحاولش ترجّع غير لو الدكتور قال كده.", "خلي علبة الدوا أو المادة معاك عشان تورّيها للإسعاف."],
    "generic": ["حاول تفضل هادي ومتتحركش كتير.", "خلي حد يفضل جنبك لحد ما الإسعاف توصل."],
}


def _greeting(name: Any) -> str:
    n = str(name or "").strip()
    return f"يا {n}، " if n else ""


def _is_female(gender: Any) -> bool:
    return str(gender or "").strip().lower() in ("female", "f", "أنثى", "ست")


def build_emergency_reply(category: str, *, name: Any = None, has_caregivers: bool = False) -> str:
    """Fixed emergency reply: ambulance number first, then first-aid steps."""
    steps = _FIRST_AID.get(category) or _FIRST_AID["generic"]
    lines = [
        f"🚨 {_greeting(name)}اتصل بالإسعاف فوراً على {AMBULANCE}.",
        f"لو الكلام صعب عليك، اطلب من أي حد جنبك يتصل بـ {AMBULANCE}.",
        "",
        "لحد ما الإسعاف توصل:",
        *[f"• {s}" for s in steps],
    ]
    if has_caregivers:
        lines += ["", "📲 بعتنا تنبيه للمسؤولين عن رعايتك المسجلين في التطبيق."]
    return "\n".join(lines)


def build_self_harm_reply(*, name: Any = None, gender: Any = None, has_caregivers: bool = False) -> str:
    """Fixed reply to a self-harm or suicide disclosure."""
    f = _is_female(gender)
    lines = [
        f"{_greeting(name)}أنا سامع{'اكي' if f else 'ك'} ومهتم {'بيكي' if f else 'بيك'}، واللي {'بتحسي' if f else 'بتحس'} بيه ده مهم.",
        f"📞 كلّم{'ي' if f else ''} خط الدعم النفسي {MENTAL_HEALTH_HOTLINE} (مجاني وشغال 24 ساعة، وزارة الصحة).",
        f"🚨 لو {'حاسة' if f else 'حاسس'} إنك ممكن تأذي نفسك دلوقتي، اتصل{'ي' if f else ''} بالإسعاف على {AMBULANCE} أو روح{'ي' if f else ''} أقرب طوارئ.",
        f"خلّي حد {'بتثقي' if f else 'بتثق'} فيه يقعد معا{'كي' if f else 'ك'} دلوقتي، وابعد{'ي' if f else ''} عن أي حاجة ممكن تأذيك.",
        f"وأنا موجود لو {'حابة' if f else 'حابب'} نتكلم.",
    ]
    if has_caregivers:
        lines.append("📲 بعتنا تنبيه للمسؤولين عن رعايتك المسجلين في التطبيق.")
    return "\n".join(lines)


MISSING_IMAGE_REPLY = (
    "📷 مش واصلني أي صورة مع رسالتك. ممكن تبعت صورة {what} تاني؟ "
    "ولما توصلني هقراها معاك. ولو فيه أي حاجة مقلقاك دلوقتي، كلّم الدكتور بتاعك."
)


def build_missing_image_reply(intent: str) -> str:
    what = "التقرير" if intent == "image_report" else "علبة الدوا"
    return MISSING_IMAGE_REPLY.format(what=what)


# ---------------------------------------------------------------------------
# 3. Output sanitiser
# ---------------------------------------------------------------------------

# Emergency numbers that do not work in Egypt. 122 (police), 123 (ambulance)
# and 180 (fire) are Egyptian and are left alone.
_FOREIGN_EMERGENCY = re.compile(r"(?<![\d٠-٩])(911|112|999|997|998|٩١١|١١٢|٩٩٩|٩٩٧)(?![\d٠-٩])")


def strip_foreign_emergency_numbers(text: str) -> str:
    """Replace emergency numbers that do not work in Egypt with 123."""
    return _FOREIGN_EMERGENCY.sub(AMBULANCE, text or "")


def has_foreign_emergency_number(text: str) -> bool:
    return bool(_FOREIGN_EMERGENCY.search(text or ""))
