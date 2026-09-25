"""
SenioCarePipeline — safety routing enforced by control flow, not prose.
=======================================================================

The original root agent was an ADK ``SequentialAgent`` that ran
Orchestrator → Feature → Formatter on every request. Nothing in Python read
the Orchestrator's ``SAFETY_STATUS``; the only thing keeping the Feature
Agent (and its ten tools) away from an emergency or a blocked request was
an instruction in its prompt (docs/AUDIT.md C-02, C-03).

This agent decides in code what runs and what the user is shown:

    message ─► screen() ─ hit ─────────────────────────────► fixed emergency / self-harm reply
                 │ no hit
                 ▼
            Orchestrator ─► route() ─┬─ EMERGENCY ──────────► fixed emergency reply
                                     ├─ image intent, no image ► "please resend the photo"
                                     ├─ BLOCKED ─────────────► Formatter (blocked relay)
                                     └─ ALLOWED / unparseable ► Feature ─► Formatter

Safety-critical replies are templates (seniocare/safety.py): the model decides
*that* a message is an emergency, code decides *what is said*. Every Formatter
reply passes through strip_foreign_emergency_numbers(). The decision is written
to session state (``safety_status``, ``intent``, ``route``,
``orchestrator_parse_ok``, ``safety_screen``, ``reply_source``) for the
emergency trigger, the observability turn record and the eval harness.

Fail-open direction for non-emergencies: if the Orchestrator's output cannot be
parsed the request proceeds through the Feature Agent and the turn is flagged
``orchestrator_parse_ok=false``; clear emergencies no longer depend on parsing
because the screen runs first.

The decision itself lives in seniocare/routing.py (pure, tested).
"""

from __future__ import annotations

from typing import AsyncGenerator, Optional

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types
from typing_extensions import override

import json
import os

from seniocare import observability as obs
from seniocare.medcheck import correction_note, unlisted_medications
from seniocare.profile import medication_names
from seniocare.routing import (
    KEY_INTENT,
    KEY_PARSE_OK,
    KEY_ROUTE,
    KEY_SAFETY,
    ensure_emergency_number,
    route,
)
from seniocare.safety import (
    build_emergency_reply,
    build_missing_image_reply,
    build_self_harm_reply,
    category_for,
    screen,
    strip_foreign_emergency_numbers,
)

KEY_SCREEN = "safety_screen"          # keyword-screen hit kind, or None
KEY_EMERGENCY_KIND = "emergency_kind"  # self_harm | chest | ... | generic
KEY_REPLY_SOURCE = "reply_source"      # formatter | template_emergency | template_self_harm | template_missing_image
KEY_UNLISTED = "unlisted_medications"   # medicines named in the reply but not on the profile
FINAL_KEY = "final_response"


def safety_layer_enabled() -> bool:
    """SENIOCARE_SAFETY_LAYER=0 turns off the deterministic layer (screen, templates,
    missing-image guard, sanitiser, medicine correction) for the ablation study; the
    pipeline then behaves as at commit d54e8d1. Read per turn so an eval run can set it."""
    return os.environ.get("SENIOCARE_SAFETY_LAYER", "1").strip() != "0"


class SenioCarePipeline(BaseAgent):
    """Screen → Orchestrator → (Feature | bypass) → Formatter | fixed reply, decided in code."""

    orchestrator: BaseAgent
    feature: BaseAgent
    formatter: BaseAgent

    def __init__(self, *, name: str, orchestrator: BaseAgent, feature: BaseAgent, formatter: BaseAgent, **kwargs):
        super().__init__(
            name=name,
            orchestrator=orchestrator,
            feature=feature,
            formatter=formatter,
            sub_agents=[orchestrator, feature, formatter],
            **kwargs,
        )

    @override
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        message = _user_text(ctx)
        layer = safety_layer_enabled()

        # Stage 0 — deterministic keyword screen on the user's own words
        hit = screen(message) if layer else None
        if hit:
            obs.emit("safety_screen", screen_kind=hit.kind, matched=hit.matched)
            yield self._state_event(ctx, {
                KEY_SAFETY: "EMERGENCY", KEY_INTENT: "emergency", KEY_ROUTE: "screen_emergency",
                KEY_PARSE_OK: None, KEY_SCREEN: hit.kind,
                "feature_result": "RESPONSE_TYPE: emergency\n",
                # the emergency report reads orchestrator_result; never leave last turn's there
                "orchestrator_result": (
                    f"SAFETY_STATUS: EMERGENCY\nINTENT: emergency\nSCREEN: {hit.kind}\n"
                    f"USER_MESSAGE: {message[:400]}"
                ),
            })
            yield self._emergency_reply(ctx, hit.kind)
            return

        # Stage 1 — Orchestrator
        async for event in self.orchestrator.run_async(ctx):
            yield event

        decision = route(state.get("orchestrator_result", ""))
        delta = {
            KEY_SAFETY: decision.safety_status,
            KEY_INTENT: decision.intent,
            KEY_ROUTE: decision.route,
            KEY_PARSE_OK: decision.parse_ok,
            KEY_SCREEN: None,
        }

        # Emergency: fixed reply, no Feature Agent, no Formatter (F-11)
        if decision.safety_status == "EMERGENCY" and layer:
            delta["feature_result"] = "RESPONSE_TYPE: emergency\n"
            yield self._state_event(ctx, delta)
            yield self._emergency_reply(ctx, category_for(message))
            return

        # Image intent without an image: ask for it, never describe it (F-15)
        if layer and decision.intent in ("image_medication", "image_report") and not _has_image(ctx):
            delta[KEY_ROUTE] = "bypass_missing_image"
            delta["feature_result"] = "RESPONSE_TYPE: missing_image\n"
            yield self._state_event(ctx, delta)
            yield self._reply(ctx, build_missing_image_reply(decision.intent), "template_missing_image")
            return

        # On the blocked path overwrite feature_result so the Formatter can never
        # reuse the previous turn's stage-2 output.
        if not decision.run_feature:
            delta["feature_result"] = decision.feature_result
        yield self._state_event(ctx, delta)

        # Stage 2 — only when the request is allowed (or unparseable)
        tool_outputs: list[str] = []
        if decision.run_feature:
            async for event in self.feature.run_async(ctx):
                tool_outputs.extend(_function_responses(event))
                yield event

        # Stage 3 — Formatter; every text it shows is sanitised, and the final
        # text is checked for medicines the user does not take (F-14)
        profile_meds = medication_names(state)
        unlisted: list[str] = []
        async for event in self.formatter.run_async(ctx):
            if layer:
                _sanitise(event)
            elif decision.safety_status == "EMERGENCY":
                _force_emergency_number(event)       # the pre-layer behaviour (commit d54e8d1)
            if not getattr(event, "partial", False):
                unlisted = _check_medications(event, profile_meds, "\n".join(tool_outputs), correct=layer) or unlisted
            yield event
        if unlisted:
            obs.emit("unlisted_medication", medications=unlisted, profile=profile_meds)
        yield self._state_event(ctx, {KEY_REPLY_SOURCE: "formatter", KEY_UNLISTED: unlisted})

    # ------------------------------------------------------------------ helpers

    def _state_event(self, ctx: InvocationContext, delta: dict) -> Event:
        return Event(invocation_id=ctx.invocation_id, author=self.name, branch=ctx.branch,
                     actions=EventActions(state_delta=delta))

    def _reply(self, ctx: InvocationContext, text: str, source: str, extra: Optional[dict] = None) -> Event:
        """A user-visible reply produced by code, attributed to the Formatter stage."""
        return Event(
            invocation_id=ctx.invocation_id,
            author=self.formatter.name,
            branch=ctx.branch,
            content=types.Content(role="model", parts=[types.Part(text=text)]),
            actions=EventActions(state_delta={FINAL_KEY: text, KEY_REPLY_SOURCE: source, **(extra or {})}),
        )

    def _emergency_reply(self, ctx: InvocationContext, kind: str) -> Event:
        state = ctx.session.state
        name = state.get("user:user_name")
        has_caregivers = bool(state.get("user:caregivers"))
        if kind == "self_harm":
            text = build_self_harm_reply(name=name, gender=state.get("user:gender"), has_caregivers=has_caregivers)
            return self._reply(ctx, text, "template_self_harm", {KEY_EMERGENCY_KIND: kind})
        text = build_emergency_reply(kind, name=name, has_caregivers=has_caregivers)
        return self._reply(ctx, text, "template_emergency", {KEY_EMERGENCY_KIND: kind})


def _user_text(ctx: InvocationContext) -> str:
    content = getattr(ctx, "user_content", None)
    parts = getattr(content, "parts", None) or []
    return " ".join(p.text for p in parts if getattr(p, "text", None))


def _has_image(ctx: InvocationContext) -> bool:
    content = getattr(ctx, "user_content", None)
    for part in getattr(content, "parts", None) or []:
        blob = getattr(part, "inline_data", None) or getattr(part, "file_data", None)
        mime = str(getattr(blob, "mime_type", "") or "")
        if blob is not None and (mime.startswith("image/") or mime == "application/pdf"):
            return True
    return False


def _sanitise(event: Event) -> None:
    """Replace emergency numbers that do not work in Egypt, in the text and in final_response."""
    content = getattr(event, "content", None)
    for part in getattr(content, "parts", None) or []:
        if getattr(part, "text", None):
            part.text = strip_foreign_emergency_numbers(part.text)
    delta = getattr(getattr(event, "actions", None), "state_delta", None)
    if isinstance(delta, dict) and delta.get(FINAL_KEY):
        delta[FINAL_KEY] = strip_foreign_emergency_numbers(delta[FINAL_KEY])


def _function_responses(event: Event) -> list[str]:
    """Tool results carried by an event, as JSON text."""
    out = []
    content = getattr(event, "content", None)
    for part in getattr(content, "parts", None) or []:
        fr = getattr(part, "function_response", None)
        if fr is not None:
            try:
                out.append(json.dumps(getattr(fr, "response", None), ensure_ascii=False, default=str))
            except Exception:  # noqa: BLE001
                out.append(str(getattr(fr, "response", "")))
    return out


def _check_medications(event: Event, profile_meds: list[str], tool_text: str, correct: bool = True) -> list[str]:
    """Flag medicines in a final Formatter event that the user does not take; append a correction."""
    content = getattr(event, "content", None)
    parts = [p for p in (getattr(content, "parts", None) or []) if getattr(p, "text", None)]
    if not parts:
        return []
    unlisted = unlisted_medications("".join(p.text for p in parts), profile_meds, tool_text)
    if not unlisted or not correct:
        return unlisted
    note = correction_note(profile_meds)
    parts[-1].text = parts[-1].text.rstrip() + "\n\n" + note
    delta = getattr(getattr(event, "actions", None), "state_delta", None)
    if isinstance(delta, dict) and delta.get(FINAL_KEY):
        delta[FINAL_KEY] = delta[FINAL_KEY].rstrip() + "\n\n" + note
    return unlisted


def _force_emergency_number(event: Event) -> None:
    """Append the ambulance number to a Formatter event that omits it (pre-layer behaviour, F-11)."""
    content = getattr(event, "content", None)
    parts = [p for p in (getattr(content, "parts", None) or []) if getattr(p, "text", None)]
    if parts:
        parts[-1].text = ensure_emergency_number(parts[-1].text)
    delta = getattr(getattr(event, "actions", None), "state_delta", None)
    if isinstance(delta, dict) and delta.get(FINAL_KEY):
        delta[FINAL_KEY] = ensure_emergency_number(delta[FINAL_KEY])
