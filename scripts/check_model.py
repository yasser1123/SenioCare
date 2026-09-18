#!/usr/bin/env python
"""
check_model.py — verify the configured model before starting SenioCare.

Runs, with the exact settings the agents use (seniocare/model.py):

  1. reachability   GET on the model server (skipped for provider-hosted APIs)
  2. completion     one short Egyptian-Arabic chat completion; latency + tokens
  3. tool call      the model must emit a well-formed tool call for a schema
                    mirroring seniocare/tools/nutrition.py::get_meal_options
  4. tool round trip the model must answer from a returned tool result
  5. adk (optional) the same tool loop driven by ADK's Runner + LlmAgent, i.e.
                    the code path the Feature Agent actually takes  (--adk)

Exit code 0 when every executed check passes, 1 otherwise. Run it after every
Colab restart (the tunnel URL changes) and before any eval run.

    python scripts/check_model.py            # checks 1-4
    python scripts/check_model.py --adk      # also the ADK tool loop
    python scripts/check_model.py --json     # machine-readable output
"""

from __future__ import annotations

import argparse
import warnings
import asyncio
import json
import os
import sys
import time
from pathlib import Path

warnings.filterwarnings("ignore", message=".*PydanticSerializationUnexpectedValue.*")
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from seniocare.model import describe_model, model_settings, probe_url  # noqa: E402

MEAL_TOOL = {
    "type": "function",
    "function": {
        "name": "get_meal_options",
        "description": "Get meal options for the user filtered by their health conditions and allergies.",
        "parameters": {
            "type": "object",
            "properties": {
                "meal_type": {
                    "type": "string",
                    "enum": ["breakfast", "lunch", "dinner", "snack"],
                    "description": "Which meal of the day",
                }
            },
            "required": ["meal_type"],
        },
    },
}


class Check:
    def __init__(self, name: str):
        self.name = name
        self.ok: bool | None = None
        self.detail = ""
        self.latency_ms: int | None = None

    def finish(self, ok: bool | None, detail: str, started: float | None = None):
        self.ok = ok
        self.detail = detail
        if started is not None:
            self.latency_ms = round((time.perf_counter() - started) * 1000)
        return self

    def as_dict(self):
        return {"name": self.name, "ok": self.ok, "latency_ms": self.latency_ms, "detail": self.detail}


def _usage(response) -> str:
    u = getattr(response, "usage", None)
    if not u:
        return "usage: n/a"
    return f"tokens in/out {getattr(u, 'prompt_tokens', '?')}/{getattr(u, 'completion_tokens', '?')}"


async def check_reachable() -> Check:
    c = Check("reachability")
    url = probe_url()
    if url is None:
        return c.finish(None, "provider-hosted API; skipped")
    import httpx

    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
        return c.finish(r.status_code < 500, f"GET {url} -> HTTP {r.status_code}", t0)
    except Exception as e:  # noqa: BLE001
        return c.finish(False, f"GET {url} -> {type(e).__name__}: {e}", t0)


async def check_completion(settings: dict) -> Check:
    import litellm

    c = Check("completion")
    t0 = time.perf_counter()
    try:
        r = await litellm.acompletion(
            messages=[
                {"role": "system", "content": "أنت مساعد صحي لكبار السن. رد باللهجة المصرية في جملة واحدة."},
                {"role": "user", "content": "عايز أكلة خفيفة على الغدا"},
            ],
            max_tokens=512,
            **settings,
        )
        msg = r.choices[0].message
        text = (msg.content or "").strip()
        reasoning = (getattr(msg, "reasoning_content", None) or "").strip()
        if text:
            note = f" (+{len(reasoning)} chars of hidden reasoning)" if reasoning else ""
            return c.finish(True, f"{_usage(r)} -> {text[:100]!r}{note}", t0)
        if reasoning or r.choices[0].finish_reason == "length":
            return c.finish(
                False,
                f"{_usage(r)} -> empty content; the model spent its budget on reasoning "
                f"(finish_reason={r.choices[0].finish_reason}). Raise MODEL_MAX_TOKENS or disable thinking mode.",
                t0,
            )
        return c.finish(False, f"{_usage(r)} -> empty content (finish_reason={r.choices[0].finish_reason})", t0)
    except Exception as e:  # noqa: BLE001
        return c.finish(False, f"{type(e).__name__}: {str(e)[:300]}", t0)


async def check_tool_call(settings: dict) -> tuple[Check, list]:
    import litellm

    c = Check("tool call")
    t0 = time.perf_counter()
    try:
        r = await litellm.acompletion(
            messages=[
                {"role": "system", "content": "You are a health assistant. You MUST call get_meal_options to answer meal requests. Never answer from memory."},
                {"role": "user", "content": "I want something good for lunch"},
            ],
            tools=[MEAL_TOOL],
            tool_choice="auto",
            max_tokens=256,
            **settings,
        )
    except Exception as e:  # noqa: BLE001
        return c.finish(False, f"{type(e).__name__}: {str(e)[:300]}", t0), []

    msg = r.choices[0].message
    calls = getattr(msg, "tool_calls", None) or []
    if not calls:
        return c.finish(False, f"no tool_calls (finish_reason={r.choices[0].finish_reason}); content={str(msg.content)[:100]!r}", t0), []
    fn = calls[0].function
    try:
        args = json.loads(fn.arguments or "{}")
    except json.JSONDecodeError as e:
        return c.finish(False, f"arguments are not valid JSON: {fn.arguments!r} ({e})", t0), []
    ok = fn.name == "get_meal_options" and args.get("meal_type") == "lunch"
    return c.finish(ok, f"{_usage(r)} -> {fn.name}({args})", t0), [tc.model_dump() if hasattr(tc, "model_dump") else tc for tc in calls]


async def check_tool_round_trip(settings: dict, calls: list) -> Check:
    import litellm

    c = Check("tool round trip")
    if not calls:
        return c.finish(None, "skipped: no tool call to continue from")
    t0 = time.perf_counter()
    try:
        r = await litellm.acompletion(
            messages=[
                {"role": "system", "content": "You are a health assistant. Use tool results to answer."},
                {"role": "user", "content": "I want something good for lunch"},
                {"role": "assistant", "content": None, "tool_calls": calls},
                {
                    "role": "tool",
                    "tool_call_id": calls[0]["id"],
                    "name": "get_meal_options",
                    "content": json.dumps({"status": "success", "options": [{"name_ar": "شوربة عدس", "name_en": "Lentil soup"}]}),
                },
            ],
            tools=[MEAL_TOOL],
            max_tokens=512,
            **settings,
        )
        msg = r.choices[0].message
        again = bool(getattr(msg, "tool_calls", None))
        text = (msg.content or "").strip()
        if again:
            return c.finish(False, f"{_usage(r)} -> model re-called the tool instead of answering from its result", t0)
        if not text:
            return c.finish(False, f"{_usage(r)} -> empty content (finish_reason={r.choices[0].finish_reason}); raise MODEL_MAX_TOKENS or disable thinking mode", t0)
        return c.finish(True, f"{_usage(r)} -> {text[:100]!r}", t0)
    except Exception as e:  # noqa: BLE001
        return c.finish(False, f"{type(e).__name__}: {str(e)[:300]}", t0)


async def check_adk_tool_loop() -> Check:
    """Drive the same tool through ADK's Runner — the Feature Agent's real path."""
    c = Check("adk tool loop")
    t0 = time.perf_counter()
    try:
        from google.adk.agents import LlmAgent
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai import types

        from seniocare.model import get_model

        calls: list[str] = []

        def get_meal_options(meal_type: str) -> dict:
            """Get meal options for the user filtered by their health conditions and allergies.

            Args:
                meal_type: one of breakfast, lunch, dinner, snack
            """
            calls.append(meal_type)
            return {"status": "success", "options": [{"name_ar": "شوربة عدس", "name_en": "Lentil soup"}]}

        agent = LlmAgent(
            name="check_model_agent",
            model=get_model(),
            instruction="You are a health assistant. You MUST call get_meal_options to answer meal requests, then answer in one sentence using the result.",
            tools=[get_meal_options],
        )
        session_service = InMemorySessionService()
        runner = Runner(agent=agent, app_name="check_model", session_service=session_service)
        session = await session_service.create_session(app_name="check_model", user_id="u", session_id="s")
        final = ""
        async for event in runner.run_async(
            user_id="u", session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part(text="I want something good for lunch")]),
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text and event.is_final_response():
                        final += part.text
        ok = calls == ["lunch"] and bool(final.strip())
        return c.finish(ok, f"tool called with {calls}; final={final.strip()[:100]!r}", t0)
    except Exception as e:  # noqa: BLE001
        return c.finish(False, f"{type(e).__name__}: {str(e)[:300]}", t0)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--adk", action="store_true", help="also run the ADK Runner tool loop")
    parser.add_argument("--json", action="store_true", help="print a JSON report instead of text")
    parser.add_argument("--skip-reachability", action="store_true")
    args = parser.parse_args()

    os.environ.setdefault("LITELLM_LOG", "ERROR")
    settings = model_settings()
    info = describe_model()

    checks: list[Check] = []

    def progress(c: Check) -> Check:
        if not args.json:
            tag = {True: "PASS", False: "FAIL", None: "SKIP"}[c.ok]
            lat = f"{c.latency_ms:>6} ms" if c.latency_ms is not None else "        -"
            print(f"[{tag}] {c.name:<16} {lat}  {c.detail}", flush=True)
        checks.append(c)
        return c

    if not args.json:
        print(f"model      : {info['model']}  ({info['location']})")
        print(f"endpoint   : {info['api_base'] or 'provider default'}   key: {info['api_key']}   timeout: {info['timeout_s']}s", flush=True)
    if not args.skip_reachability:
        if progress(await check_reachable()).ok is False:
            return _report(info, checks, args.json, header=False)

    progress(await check_completion(settings))
    tool_check, calls = await check_tool_call(settings)
    progress(tool_check)
    progress(await check_tool_round_trip(settings, calls))
    if args.adk:
        progress(await check_adk_tool_loop())
    return _report(info, checks, args.json, header=False)


def _report(info: dict, checks: list[Check], as_json: bool, header: bool = True) -> int:
    failed = [c for c in checks if c.ok is False]
    if as_json:
        print(json.dumps({"model": info, "checks": [c.as_dict() for c in checks], "ok": not failed}, ensure_ascii=False, indent=2))
    else:
        if header:
            print(f"model      : {info['model']}  ({info['location']})")
            print(f"endpoint   : {info['api_base'] or 'provider default'}   key: {info['api_key']}   timeout: {info['timeout_s']}s")
            print()
            for c in checks:
                tag = {True: "PASS", False: "FAIL", None: "SKIP"}[c.ok]
                lat = f"{c.latency_ms:>6} ms" if c.latency_ms is not None else "        -"
                print(f"[{tag}] {c.name:<16} {lat}  {c.detail}")
        print()
        if failed:
            print(f"RESULT: FAIL ({', '.join(c.name for c in failed)}) — do not start the app against this model.")
        else:
            print("RESULT: PASS — the model answers and calls tools; safe to start the app.")
    return 1 if failed else 0


if __name__ == "__main__":
    if sys.platform == "win32":
        # Arabic output on a legacy console
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    sys.exit(asyncio.run(main()))
