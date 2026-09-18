"""
SenioCarePipeline — safety routing enforced by control flow, not prose.
=======================================================================

The original root agent was an ADK ``SequentialAgent`` that ran
Orchestrator → Feature → Formatter on every request. Nothing in Python read
the Orchestrator's ``SAFETY_STATUS``; the only thing keeping the Feature
Agent (and its ten tools) away from an emergency or a blocked request was
an instruction in its prompt (docs/AUDIT.md C-02, C-03).

This agent runs the same three stages but decides in code, after the
Orchestrator, whether the Feature Agent runs at all:

    Orchestrator ──► route() ──┬── ALLOWED / unparseable ──► Feature ──► Formatter
                               └── BLOCKED / EMERGENCY ─────────────────► Formatter

On the bypass path the Feature Agent's output is synthesised
deterministically from the Orchestrator's own BLOCKED_MESSAGE /
EMERGENCY_MESSAGE in the exact format the Formatter already expects, so the
Formatter prompt did not change. The decision and the parsed fields are
written to session state (``safety_status``, ``intent``, ``route``,
``orchestrator_parse_ok``) for the emergency trigger, the observability
turn record and the eval harness.

Fail-safe direction: if the Orchestrator's output cannot be parsed at all,
the request proceeds through the Feature Agent (the user still gets an
answer) and the turn is flagged ``orchestrator_parse_ok=false``. If either
signal says emergency (status *or* intent) the bypass is taken.

The decision itself lives in seniocare/routing.py (pure, tested).
"""

from __future__ import annotations

from typing import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from typing_extensions import override

from seniocare.routing import KEY_INTENT, KEY_PARSE_OK, KEY_ROUTE, KEY_SAFETY, route


class SenioCarePipeline(BaseAgent):
    """Orchestrator → (Feature | bypass) → Formatter, decided in code."""

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
        # Stage 1 — always
        async for event in self.orchestrator.run_async(ctx):
            yield event

        decision = route(ctx.session.state.get("orchestrator_result", ""))

        # Publish the decision. On the bypass path also overwrite feature_result
        # so the Formatter can never reuse the previous turn's stage-2 output.
        delta = {
            KEY_SAFETY: decision.safety_status,
            KEY_INTENT: decision.intent,
            KEY_ROUTE: decision.route,
            KEY_PARSE_OK: decision.parse_ok,
        }
        if not decision.run_feature:
            delta["feature_result"] = decision.feature_result
        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            branch=ctx.branch,
            actions=EventActions(state_delta=delta),
        )

        # Stage 2 — only when the request is allowed (or unparseable)
        if decision.run_feature:
            async for event in self.feature.run_async(ctx):
                yield event

        # Stage 3 — always
        async for event in self.formatter.run_async(ctx):
            yield event
