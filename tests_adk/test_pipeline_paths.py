"""SenioCarePipeline paths under the real ADK runner, with stub stages.

Run separately from tests/ (whose conftest replaces google.adk with stubs):

    pytest tests_adk

No model and no database are involved.
"""

from typing import AsyncGenerator

import pytest
from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.runners import InMemoryRunner
from google.genai import types

from seniocare.pipeline import SenioCarePipeline
from seniocare.safety import AMBULANCE, MENTAL_HEALTH_HOTLINE

# ----------------------------------------------------------------- pipeline


class Stub(BaseAgent):
    """A stage that writes a fixed text to its output key and records that it ran."""

    text: str
    key: str

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        ran = list(ctx.session.state.get("ran", []))
        yield Event(
            invocation_id=ctx.invocation_id, author=self.name, branch=ctx.branch,
            content=types.Content(role="model", parts=[types.Part(text=self.text)]),
            actions=EventActions(state_delta={self.key: self.text, "ran": ran + [self.name]}),
        )


def _pipeline(orchestrator_text: str, formatter_text: str = "تمام يا حاج، اتصل بـ 911 لو تعبت.") -> SenioCarePipeline:
    return SenioCarePipeline(
        name="seniocare",
        orchestrator=Stub(name="orchestrator_agent", text=orchestrator_text, key="orchestrator_result"),
        feature=Stub(name="feature_agent", text="RESPONSE_TYPE: meal_recommendation", key="feature_result"),
        formatter=Stub(name="formatter_agent", text=formatter_text, key="final_response"),
    )


async def _run(agent: SenioCarePipeline, message: str, image: bool = False, state: dict | None = None):
    runner = InMemoryRunner(agent=agent, app_name="t")
    session = await runner.session_service.create_session(app_name="t", user_id="u", state=state or {})
    parts = [types.Part(text=message)]
    if image:
        parts.append(types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=b"\xff\xd8\xff")))
    texts = []
    async for ev in runner.run_async(user_id="u", session_id=session.id,
                                     new_message=types.Content(role="user", parts=parts)):
        if ev.author == "formatter_agent" and ev.content and ev.content.parts:
            texts.append("".join(p.text or "" for p in ev.content.parts))
    session = await runner.session_service.get_session(app_name="t", user_id="u", session_id=session.id)
    return "".join(texts), session.state


ALLOWED_MEAL = "SAFETY_STATUS: ALLOWED\nINTENT: meal\nTASK_PLAN: get_meal_options"


@pytest.mark.asyncio
async def test_screen_hit_skips_every_llm_stage_and_answers_with_the_template():
    text, state = await _run(_pipeline(ALLOWED_MEAL), "صدري بيوجعني جامد ومش قادر أتنفس",
                             state={"user:user_name": "أحمد"})
    assert state.get("ran", []) == []
    assert text.startswith("🚨") and AMBULANCE in text.splitlines()[0]
    assert state["safety_status"] == "EMERGENCY" and state["route"] == "screen_emergency"
    assert state["reply_source"] == "template_emergency" and state["final_response"] == text


@pytest.mark.asyncio
async def test_self_harm_gets_the_crisis_template():
    text, state = await _run(_pipeline(ALLOWED_MEAL), "مش عايز أعيش تاني")
    assert MENTAL_HEALTH_HOTLINE in text and state["reply_source"] == "template_self_harm"


@pytest.mark.asyncio
async def test_llm_detected_emergency_uses_the_template_not_the_formatter():
    orch = "SAFETY_STATUS: EMERGENCY\nINTENT: emergency\nEMERGENCY_MESSAGE: اتصل بـ 911"
    text, state = await _run(_pipeline(orch), "حاسس إني هموت من الوجع")
    assert state["ran"] == ["orchestrator_agent"]
    assert "911" not in text and AMBULANCE in text
    assert state["reply_source"] == "template_emergency"


@pytest.mark.asyncio
async def test_image_intent_without_an_image_asks_for_it():
    orch = "SAFETY_STATUS: ALLOWED\nINTENT: image_report\nTASK_PLAN: read report"
    text, state = await _run(_pipeline(orch), "[IMAGE ATTACHED] ده تقرير التحاليل بتاعي")
    assert state["ran"] == ["orchestrator_agent"]
    assert "مش واصلني" in text and state["route"] == "bypass_missing_image"


@pytest.mark.asyncio
async def test_image_intent_with_an_image_runs_the_full_pipeline():
    orch = "SAFETY_STATUS: ALLOWED\nINTENT: image_medication\nTASK_PLAN: read box"
    _, state = await _run(_pipeline(orch), "ده دوا إيه؟", image=True)
    assert state["ran"] == ["orchestrator_agent", "feature_agent", "formatter_agent"]


@pytest.mark.asyncio
async def test_formatter_reply_is_sanitised_of_foreign_numbers():
    text, state = await _run(_pipeline(ALLOWED_MEAL), "عايز غدا")
    assert "911" not in text and "123" in text
    assert "911" not in state["final_response"]
    assert state["reply_source"] == "formatter"


@pytest.mark.asyncio
async def test_a_medicine_the_user_does_not_take_is_flagged_and_corrected():
    meds = {"user:user_id": "u", "user:medications": [{"name": "Metformin", "dose": "500mg"}]}
    text, state = await _run(_pipeline(ALLOWED_MEAL, "الأكلة دي آمنة مع اللوسارتان."), "عايز غدا", state=meds)
    assert state["unlisted_medications"] == ["losartan"]
    assert "الأدوية المسجلة في ملفك هي: Metformin" in text
    assert "الأدوية المسجلة" in state["final_response"]


@pytest.mark.asyncio
async def test_profile_medicines_pass_without_a_note():
    meds = {"user:user_id": "u", "user:medications": [{"name": "Metformin"}]}
    text, state = await _run(_pipeline(ALLOWED_MEAL, "الأكلة دي آمنة مع الميتفورمين."), "عايز غدا", state=meds)
    assert state["unlisted_medications"] == [] and "ملحوظة" not in text


@pytest.mark.asyncio
async def test_ablation_without_the_safety_layer_behaves_as_before(monkeypatch):
    """SENIOCARE_SAFETY_LAYER=0: no screen, the Formatter answers the emergency, 123 is appended."""
    monkeypatch.setenv("SENIOCARE_SAFETY_LAYER", "0")
    orch = "SAFETY_STATUS: EMERGENCY\nINTENT: emergency\nEMERGENCY_MESSAGE: اهدى"
    text, state = await _run(_pipeline(orch, "حاول تهدى واتصل بـ 911"), "صدري بيوجعني جامد")
    assert state["ran"] == ["orchestrator_agent", "formatter_agent"]
    assert "911" in text and text.rstrip().endswith("123.")
