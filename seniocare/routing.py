"""
Routing decision from the Orchestrator's output — pure, no ADK imports.

Used by seniocare/pipeline.py (control flow), seniocare/callbacks.py (the
emergency trigger) and the tests. See pipeline.py for the design notes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from seniocare.observability import parse_intent, parse_safety_status

# State keys written by the router (persisted; read by callbacks, observability and evals)
KEY_SAFETY = "safety_status"
KEY_INTENT = "intent"
KEY_ROUTE = "route"
KEY_PARSE_OK = "orchestrator_parse_ok"

_FIELD_RE = {
    name: re.compile(rf"{name}\s*[:：]\s*(.+?)(?=\n[A-Z_]+\s*[:：]|\n---|\Z)", re.DOTALL)
    for name in ("BLOCKED_REASON", "BLOCKED_MESSAGE", "EMERGENCY_MESSAGE")
}

# The ambulance number is safety-critical and must never depend on the model
# reproducing it (FINDINGS F-11: the Formatter dropped it on 6 of 7 emergency
# turns in run C). It is asserted in code by ensure_emergency_number().
EMERGENCY_NUMBER = "123"
EMERGENCY_NUMBER_LINE = f"🚨 اتصل بالإسعاف فوراً على {EMERGENCY_NUMBER}."

DEFAULT_EMERGENCY_MESSAGE = (
    f"اتصل بالإسعاف فوراً على {EMERGENCY_NUMBER}. "
    "حاول تفضل هادي ومتتحركش كتير، واطلب من حد جنبك يساعدك."
)
DEFAULT_BLOCKED_REASON = "الطلب خارج نطاق المساعد الصحي"
DEFAULT_BLOCKED_MESSAGE = (
    "الموضوع ده محتاج دكتور متخصص يشوفه. من فضلك استشير الدكتور بتاعك في أقرب وقت، "
    "وأنا موجود لو محتاج وجبات صحية أو تمارين."
)


@dataclass(frozen=True)
class RouteDecision:
    safety_status: str             # ALLOWED | BLOCKED | EMERGENCY
    intent: str                    # parsed intent or "unknown"
    parse_ok: bool                 # both SAFETY_STATUS and INTENT parsed
    run_feature: bool              # whether the Feature Agent runs
    feature_result: Optional[str]  # synthesised stage-2 output on the bypass path

    @property
    def route(self) -> str:
        return "full" if self.run_feature else f"bypass_{self.safety_status.lower()}"


def extract_field(text: str, name: str) -> Optional[str]:
    """Value of a `NAME: …` line (multi-line until the next field). None if absent."""
    m = _FIELD_RE[name].search(text or "")
    if not m:
        return None
    value = m.group(1).strip().strip("*").strip()
    return value or None


def route(orchestrator_output: str) -> RouteDecision:
    """Pure routing decision from the Orchestrator's text. Never raises.

    - EMERGENCY (by status *or* intent) → bypass, synthesised emergency relay
    - BLOCKED   (by status *or* intent) → bypass, synthesised blocked relay
    - anything else, including unparseable → Feature Agent runs; parse_ok flags it
    """
    text = orchestrator_output or ""
    status = parse_safety_status(text)
    intent = parse_intent(text) or "unknown"
    parse_ok = status is not None and intent != "unknown"

    if status == "EMERGENCY" or intent == "emergency":
        msg = extract_field(text, "EMERGENCY_MESSAGE") or DEFAULT_EMERGENCY_MESSAGE
        return RouteDecision("EMERGENCY", "emergency", parse_ok, False,
                             f"RESPONSE_TYPE: emergency\nEMERGENCY_MESSAGE: {msg}\n")
    if status == "BLOCKED" or intent == "blocked":
        reason = extract_field(text, "BLOCKED_REASON") or DEFAULT_BLOCKED_REASON
        msg = extract_field(text, "BLOCKED_MESSAGE") or DEFAULT_BLOCKED_MESSAGE
        return RouteDecision("BLOCKED", "blocked", parse_ok, False,
                             f"RESPONSE_TYPE: blocked\nBLOCKED_REASON: {reason}\nBLOCKED_MESSAGE: {msg}\n")
    return RouteDecision(status or "ALLOWED", intent, parse_ok, True, None)


def ensure_emergency_number(text: str) -> str:
    """Return `text` with the ambulance number guaranteed to appear.

    The Formatter is generative: in run C it produced a correct, urgent,
    well-structured emergency answer that told the elder to call an ambulance
    without ever printing the number, on 6 of 7 emergency turns (FINDINGS
    F-11). A safety-critical literal cannot be left to the model, so the
    pipeline appends it after the fact when it is missing. Idempotent.
    """
    body = text or ""
    if EMERGENCY_NUMBER in body:
        return body
    return (body.rstrip() + "\n\n" + EMERGENCY_NUMBER_LINE).lstrip()
