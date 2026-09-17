"""
SenioCare Evaluation Harness
=============================

Loads eval cases, invokes the 3-agent pipeline, records outputs and metrics,
writes results to disk.

ASSERTION LOGIC IS DELIBERATELY STUBBED. Every function in the ASSERTIONS
section raises NotImplementedError. The harness runs end-to-end and produces
a complete results file without them — assertions are additive.

Usage:
    python evals/runner.py                                  # all cases, in-process
    python evals/runner.py --cases evals/cases/04_emergency.jsonl
    python evals/runner.py --filter emergency-              # id prefix filter
    python evals/runner.py --mode http --base-url http://localhost:8080
    python evals/runner.py --dry-run                        # load + validate only

No new dependencies. Uses only stdlib plus packages already in requirements.txt
(google-adk, httpx).

Design notes
------------
Two execution modes:

  adk  (default) — imports seniocare.agent.root_agent and drives it through
                   ADK's Runner in-process. No server needed. Gives direct
                   access to per-stage state and tool-call events, which is
                   what most assertions need.

  http           — POSTs to /run_sse on a running server. Exercises the real
                   transport the Flutter client uses, but stage-level detail
                   must be reconstructed from the SSE event stream.

Prefer `adk` unless you are specifically testing the HTTP layer.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
import traceback
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

EVALS_DIR = Path(__file__).resolve().parent
DEFAULT_CASES_DIR = EVALS_DIR / "cases"
DEFAULT_RESULTS_DIR = EVALS_DIR / "results"
PROFILES_PATH = EVALS_DIR / "profiles.json"

APP_NAME = "seniocare"

# Tools actually registered on the Feature Agent
# (source: seniocare/sub_agents/feature_agent.py:312-323)
KNOWN_TOOLS = {
    "get_meal_options",
    "get_meal_recipe",
    "check_drug_food_interaction",
    "assess_symptoms",
    "get_exercises",
    "search_medical_info",
    "search_web",
    "search_youtube",
    "store_medical_report",
    "save_user_preference",
}

# Stage output_key -> agent name
# (orchestrator_agent.py:318, feature_agent.py:324, formatter_agent.py:234)
STAGES = {
    "orchestrator": ("orchestrator_agent", "orchestrator_result"),
    "feature": ("feature_agent", "feature_result"),
    "formatter": ("formatter_agent", "final_response"),
}


# ===========================================================================
# Case + result models
# ===========================================================================


@dataclass
class Case:
    id: str
    input: str
    locale: str
    category: str
    expect: dict
    assertion: str
    profile: str
    notes: str = ""
    output: Optional[dict] = None

    @staticmethod
    def from_dict(d: dict) -> "Case":
        missing = [k for k in ("id", "input", "category", "assertion", "profile") if k not in d]
        if missing:
            raise ValueError(f"case missing required fields {missing}: {d.get('id', '<no id>')}")
        return Case(
            id=d["id"],
            input=d["input"],
            locale=d.get("locale", "ar-EG"),
            category=d["category"],
            expect=d.get("expect") or {},
            assertion=d["assertion"],
            profile=d["profile"],
            notes=d.get("notes", ""),
            output=d.get("output"),
        )


@dataclass
class StageRecord:
    text: str = ""
    latency_ms: Optional[int] = None


@dataclass
class Result:
    case_id: str
    category: str
    assertion: str
    profile: str
    run_id: str
    final_response: str = ""
    stages: dict = field(default_factory=dict)
    tools_called: list = field(default_factory=list)
    parsed: dict = field(default_factory=dict)
    e2e_latency_ms: Optional[int] = None
    output_chars: int = 0
    error: Optional[str] = None
    assertions: list = field(default_factory=list)


# ===========================================================================
# Loading
# ===========================================================================


def load_profiles() -> dict:
    if not PROFILES_PATH.exists():
        raise FileNotFoundError(f"profiles file not found: {PROFILES_PATH}")
    with open(PROFILES_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    # Strip documentation keys
    return {
        k: {sk: sv for sk, sv in v.items() if not sk.startswith("_")}
        for k, v in raw.items()
        if not k.startswith("_") and isinstance(v, dict)
    }


def load_cases(path: Path) -> list[Case]:
    """Load cases from a .jsonl file or every .jsonl in a directory."""
    files: list[Path]
    if path.is_dir():
        files = sorted(path.glob("*.jsonl"))
    elif path.is_file():
        files = [path]
    else:
        raise FileNotFoundError(f"no such case path: {path}")

    cases: list[Case] = []
    seen: set[str] = set()

    for fp in files:
        with open(fp, encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                line = line.strip()
                if not line or line.startswith("//"):
                    continue
                try:
                    case = Case.from_dict(json.loads(line))
                except (json.JSONDecodeError, ValueError) as e:
                    print(f"  [SKIP] {fp.name}:{lineno} — {e}")
                    continue
                if case.id in seen:
                    print(f"  [SKIP] {fp.name}:{lineno} — duplicate id {case.id!r}")
                    continue
                seen.add(case.id)
                cases.append(case)

    return cases


# ===========================================================================
# Parsing helpers — reuse production regexes where they exist
# ===========================================================================


def extract_intent(orchestrator_output: str) -> str:
    """Mirrors seniocare/callbacks.py:206-212 EXACTLY.

    Deliberately duplicated rather than imported, so the eval measures the
    real parser's behaviour without importing the ADK-dependent callbacks
    module. If callbacks.py changes, this must change with it.
    """
    if not orchestrator_output:
        return "unknown"
    match = re.search(r"INTENT:\s*(\w+)", orchestrator_output)
    if match:
        return match.group(1).lower().strip()
    return "unknown"


def extract_safety_status(orchestrator_output: str) -> str:
    """Extract SAFETY_STATUS from stage-1 output.

    NOTE: no production code reads this field (see docs/AUDIT.md C-03).
    This harness is its first and only consumer.
    """
    if not orchestrator_output:
        return "unknown"
    match = re.search(r"SAFETY_STATUS:\s*(\w+)", orchestrator_output)
    return match.group(1).upper().strip() if match else "unknown"


def extract_response_type(feature_output: str) -> str:
    """Extract RESPONSE_TYPE from stage-2 output (feature_agent.py:233)."""
    if not feature_output:
        return "unknown"
    match = re.search(r"RESPONSE_TYPE:\s*(\w+)", feature_output)
    return match.group(1).lower().strip() if match else "unknown"


# ===========================================================================
# Runner — ADK in-process mode
# ===========================================================================


async def run_case_adk(case: Case, profiles: dict, run_id: str) -> Result:
    """Invoke the real 3-agent pipeline in-process via ADK's Runner."""
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    from seniocare.agent import root_agent

    result = Result(
        case_id=case.id,
        category=case.category,
        assertion=case.assertion,
        profile=case.profile,
        run_id=run_id,
    )

    profile_state = profiles.get(case.profile)
    if profile_state is None:
        result.error = f"unknown profile {case.profile!r}"
        return result

    session_service = InMemorySessionService()
    runner = Runner(
        agent=root_agent,
        app_name=APP_NAME,
        session_service=session_service,
    )

    user_id = f"eval_{case.profile}_{uuid.uuid4().hex[:6]}"
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=f"eval_{uuid.uuid4().hex[:12]}",
        state=dict(profile_state),
    )

    message = types.Content(role="user", parts=[types.Part(text=case.input)])

    stage_texts: dict[str, str] = {}
    stage_first_seen: dict[str, float] = {}
    tools_called: list[str] = []
    started = time.perf_counter()

    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session.id,
            new_message=message,
        ):
            now = time.perf_counter()
            author = getattr(event, "author", None)

            # Accumulate per-agent text output
            content = getattr(event, "content", None)
            if content and getattr(content, "parts", None):
                for part in content.parts:
                    text = getattr(part, "text", None)
                    if text:
                        if author:
                            stage_texts[author] = stage_texts.get(author, "") + text
                            stage_first_seen.setdefault(author, now)

                    # Record tool invocations
                    fc = getattr(part, "function_call", None)
                    if fc is not None and getattr(fc, "name", None):
                        tools_called.append(fc.name)

        result.e2e_latency_ms = int((time.perf_counter() - started) * 1000)

        # Read final stage state
        final_session = await session_service.get_session(
            app_name=APP_NAME, user_id=user_id, session_id=session.id
        )
        state = dict(getattr(final_session, "state", {}) or {})

        for stage_name, (agent_name, output_key) in STAGES.items():
            text = state.get(output_key) or stage_texts.get(agent_name, "")
            result.stages[stage_name] = asdict(StageRecord(text=text or ""))

        result.final_response = result.stages["formatter"]["text"]
        result.output_chars = len(result.final_response)
        result.tools_called = tools_called
        result.parsed = {
            "safety_status": extract_safety_status(result.stages["orchestrator"]["text"]),
            "intent": extract_intent(result.stages["orchestrator"]["text"]),
            "response_type": extract_response_type(result.stages["feature"]["text"]),
        }

    except Exception:
        result.error = traceback.format_exc(limit=6)
        result.e2e_latency_ms = int((time.perf_counter() - started) * 1000)

    return result


# ===========================================================================
# Runner — HTTP mode
# ===========================================================================


async def run_case_http(case: Case, profiles: dict, run_id: str, base_url: str) -> Result:
    """Drive the pipeline through the live /run_sse endpoint."""
    import httpx

    result = Result(
        case_id=case.id,
        category=case.category,
        assertion=case.assertion,
        profile=case.profile,
        run_id=run_id,
    )

    profile_state = profiles.get(case.profile)
    if profile_state is None:
        result.error = f"unknown profile {case.profile!r}"
        return result

    user_id = f"eval_{case.profile}_{uuid.uuid4().hex[:6]}"
    started = time.perf_counter()

    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=300.0) as client:
            # Seed the profile through the real endpoint, unless testing the
            # no-profile path (docs/AUDIT.md C-11).
            if profile_state:
                payload = {
                    k.replace("user:", ""): v
                    for k, v in profile_state.items()
                    if k.startswith("user:") and k != "user:user_id"
                }
                payload.pop("preferences", None)
                await client.post(f"/set-user-profile/{user_id}", json=payload)

            sess = await client.post("/create-session", json={"user_id": user_id})
            sess.raise_for_status()
            session_id = sess.json()["session_id"]

            body = {
                "app_name": APP_NAME,
                "user_id": user_id,
                "session_id": session_id,
                "new_message": {"role": "user", "parts": [{"text": case.input}]},
                "streaming": False,
            }

            stage_texts: dict[str, str] = {}
            tools_called: list[str] = []

            async with client.stream("POST", "/run_sse", json=body) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw or raw == "[DONE]":
                        continue
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    author = event.get("author")
                    for part in (event.get("content") or {}).get("parts") or []:
                        if part.get("text") and author:
                            stage_texts[author] = stage_texts.get(author, "") + part["text"]
                        fc = part.get("functionCall") or part.get("function_call")
                        if fc and fc.get("name"):
                            tools_called.append(fc["name"])

        result.e2e_latency_ms = int((time.perf_counter() - started) * 1000)

        for stage_name, (agent_name, _key) in STAGES.items():
            result.stages[stage_name] = asdict(
                StageRecord(text=stage_texts.get(agent_name, ""))
            )

        result.final_response = result.stages["formatter"]["text"]
        result.output_chars = len(result.final_response)
        result.tools_called = tools_called
        result.parsed = {
            "safety_status": extract_safety_status(result.stages["orchestrator"]["text"]),
            "intent": extract_intent(result.stages["orchestrator"]["text"]),
            "response_type": extract_response_type(result.stages["feature"]["text"]),
        }

    except Exception:
        result.error = traceback.format_exc(limit=6)
        result.e2e_latency_ms = int((time.perf_counter() - started) * 1000)

    return result


# ===========================================================================
# Multi-turn — STUB
# ===========================================================================


async def run_multi_turn(cases: list[Case], profiles: dict, run_id: str) -> list[Result]:
    """Run an ordered list of cases inside ONE session.

    NOT IMPLEMENTED. This is the single most important extension to this
    harness, because two confirmed findings are invisible to single-turn runs:

      - docs/AUDIT.md C-04: the _*_tool_called guards (nutrition.py:29,
        interactions.py:27, symptoms.py:30, image_tools.py:48) are written to
        session state WITHOUT a temp: prefix and are never reset. From turn 2
        onward every guarded tool short-circuits to "already_called". Drug
        interaction screening silently stops running.

      - docs/AUDIT.md C-05: the preference conflict bug only manifests when a
        like and a dislike for the same item are saved in sequence
        (preference-happy-002 followed by preference-conflict-001).

    Implementation sketch: create one session, replay each case's input
    through the same runner and session_id in order, and snapshot
    session.state between turns so the guard flags and user:preferences can
    be inspected per turn.
    """
    raise NotImplementedError(
        "Multi-turn runner not implemented. Required to reproduce AUDIT C-04 and C-05."
    )


# ===========================================================================
# ASSERTIONS — ALL STUBBED. Fill these in.
# ===========================================================================
#
# Each returns a list of dicts:
#   {"name": str, "passed": bool, "detail": str}
#
# Return [] to mean "nothing asserted", which is different from "passed".
# Keep that distinction — a case with no assertions must never be reported
# as green.
# ===========================================================================


def assert_structural(case: Case, result: Result) -> list[dict]:
    """Assert on parsed stage fields and the tool-call log.

    Should cover, when present in case.expect:
      - expect["safety_status"]  vs result.parsed["safety_status"]
      - expect["intent"]         vs result.parsed["intent"]
      - expect["response_type"]  vs result.parsed["response_type"]
      - expect["tools_called"]     ⊆ result.tools_called
      - expect["tools_not_called"] ∩ result.tools_called == ∅

    Design decisions left to you:
      - Is tool ORDER significant? feature_agent.py:161-172 specifies an
        order for the meal chain, but ADK does not guarantee it.
      - Are DUPLICATE tool calls a failure? feature_agent.py:292-293 says
        "call each tool only once", and the guards at nutrition.py:24 exist
        to enforce it — but see C-04 for why that enforcement is broken.
      - Should intent "unknown" be a hard failure or a tracked metric?
        Recommend tracking it separately; it is the direct measurement of
        C-03 (see docs/INSTRUMENTATION.md §2).
    """
    raise NotImplementedError("assert_structural")


def assert_keyword(case: Case, result: Result) -> list[dict]:
    """Assert substring presence/absence in the final response.

      - every s in expect["must_contain"]     appears in result.final_response
      - no     s in expect["must_not_contain"] appears in result.final_response

    Consider before implementing:
      - Arabic normalisation. أ/إ/آ/ا and ة/ه and ي/ى are routinely
        interchanged. Naive substring matching will produce false negatives.
        A normalise() helper applied to BOTH sides is probably required.
      - Diacritics (tashkeel) should be stripped before comparison.
    """
    raise NotImplementedError("assert_keyword")


def assert_language(case: Case, result: Result) -> list[dict]:
    """Assert the response is in the expected script/dialect.

    Tractable: is the response predominantly Arabic script? Compute the ratio
    of characters in U+0600–U+06FF to total non-whitespace characters.

    NOT tractable: distinguishing Egyptian dialect from MSA, which is what
    formatter_agent.py:217 actually requires. No library does this reliably.
    Presence of honorifics like "حضرتك" (formatter_agent.py:190) or "يا فندم"
    is a weak proxy, NOT proof. See evals/schema.md §4.2 — this needs a
    native speaker.
    """
    raise NotImplementedError("assert_language")


def assert_judge(case: Case, result: Result) -> list[dict]:
    """LLM-as-judge scoring against a rubric.

    Before implementing, read evals/schema.md §4.4. The core problem: the
    obvious judge is the same gemma4:e4b that generated the output
    (orchestrator_agent.py:315), so it shares the generator's blind spots.

    If you build this:
      - use a different and stronger model than the generator
      - emit a score plus a written justification, never a bare pass/fail
      - treat the result as triage for human review, not as a gate
    """
    raise NotImplementedError("assert_judge")


def assert_human(case: Case, result: Result) -> list[dict]:
    """Cases requiring human review — intentionally never auto-passes.

    Should return a single pending marker, e.g.:
        [{"name": "human_review", "passed": None, "detail": "pending"}]

    Applies to every emergency case, clinical-appropriateness cases, and
    dialect authenticity. See evals/schema.md §4. Do NOT let these count as
    passing in any summary — a green run that silently includes unreviewed
    emergency cases is worse than no run at all.
    """
    raise NotImplementedError("assert_human")


ASSERTION_DISPATCH = {
    "structural": assert_structural,
    "keyword": assert_keyword,
    "judge": assert_judge,
    "human": assert_human,
}


def evaluate(case: Case, result: Result) -> list[dict]:
    """Dispatch to the right assertion function. Never raises."""
    fn = ASSERTION_DISPATCH.get(case.assertion)
    if fn is None:
        return [{"name": "dispatch", "passed": False,
                 "detail": f"unknown assertion type {case.assertion!r}"}]
    try:
        return fn(case, result)
    except NotImplementedError as e:
        return [{"name": str(e), "passed": None, "detail": "assertion not implemented"}]


# ===========================================================================
# Output
# ===========================================================================


def write_results(results: list[Result], out_dir: Path, run_id: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = run_id.replace(":", "").replace("-", "")
    out_path = out_dir / f"run_{stamp}.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
    return out_path


def print_summary(results: list[Result]) -> None:
    total = len(results)
    errored = sum(1 for r in results if r.error)
    lat = sorted(r.e2e_latency_ms for r in results if r.e2e_latency_ms is not None)

    print("\n" + "=" * 68)
    print(f"  {total} cases  |  {errored} errored  |  {total - errored} completed")
    print("=" * 68)

    if lat:
        def pct(p: float) -> int:
            return lat[min(int(len(lat) * p), len(lat) - 1)]
        print(f"  e2e latency   p50 {pct(0.50)}ms   p95 {pct(0.95)}ms   max {lat[-1]}ms")

    # Intent extraction health — direct measurement of docs/AUDIT.md C-03
    parsed = [r for r in results if not r.error]
    if parsed:
        unknown = sum(1 for r in parsed if r.parsed.get("intent") == "unknown")
        unk_safety = sum(1 for r in parsed if r.parsed.get("safety_status") == "unknown")
        print(f"  intent=unknown         {unknown}/{len(parsed)}"
              f"   ({100 * unknown / len(parsed):.0f}%)   <- AUDIT C-03")
        print(f"  safety_status=unknown  {unk_safety}/{len(parsed)}"
              f"   ({100 * unk_safety / len(parsed):.0f}%)")

    by_cat: dict[str, int] = {}
    for r in results:
        by_cat[r.category] = by_cat.get(r.category, 0) + 1
    print("\n  by category: " + ", ".join(f"{k}={v}" for k, v in sorted(by_cat.items())))

    pending = sum(
        1 for r in results
        for a in r.assertions
        if a.get("passed") is None
    )
    if pending:
        print(f"\n  {pending} assertions unevaluated (stubbed or pending human review)")
        print("  NOTE: this run asserts nothing. Do not read it as a pass.")
    print()


# ===========================================================================
# Main
# ===========================================================================


async def main_async(args: argparse.Namespace) -> int:
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"SenioCare eval harness — run {run_id}")
    print(f"  mode:  {args.mode}")
    print(f"  cases: {args.cases}")

    profiles = load_profiles()
    cases = load_cases(Path(args.cases))

    if args.filter:
        cases = [c for c in cases if c.id.startswith(args.filter)]
    if args.category:
        cases = [c for c in cases if c.category == args.category]
    if args.limit:
        cases = cases[: args.limit]

    print(f"  loaded {len(cases)} cases, {len(profiles)} profiles\n")

    if not cases:
        print("No cases matched. Nothing to do.")
        return 1

    if args.dry_run:
        for c in cases:
            print(f"  {c.id:34} {c.category:20} {c.assertion:11} {c.profile}")
        print(f"\nDry run — {len(cases)} cases validated, nothing executed.")
        return 0

    results: list[Result] = []
    for i, case in enumerate(cases, start=1):
        print(f"[{i}/{len(cases)}] {case.id} ... ", end="", flush=True)

        if args.mode == "http":
            result = await run_case_http(case, profiles, run_id, args.base_url)
        else:
            result = await run_case_adk(case, profiles, run_id)

        result.assertions = evaluate(case, result)
        results.append(result)

        if result.error:
            print(f"ERROR ({result.e2e_latency_ms}ms)")
        else:
            print(
                f"{result.e2e_latency_ms}ms  "
                f"intent={result.parsed.get('intent')}  "
                f"tools={len(result.tools_called)}"
            )

    out_path = write_results(results, Path(args.out), run_id)
    print_summary(results)
    print(f"  results written to {out_path}\n")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="SenioCare evaluation harness (assertions stubbed)."
    )
    p.add_argument("--cases", default=str(DEFAULT_CASES_DIR),
                   help="case file or directory of .jsonl files")
    p.add_argument("--out", default=str(DEFAULT_RESULTS_DIR),
                   help="results output directory")
    p.add_argument("--mode", choices=["adk", "http"], default="adk",
                   help="adk = in-process (default); http = against a running server")
    p.add_argument("--base-url", default="http://localhost:8080",
                   help="server base URL for --mode http")
    p.add_argument("--filter", default=None, help="only cases whose id starts with this")
    p.add_argument("--category", default=None, help="only cases in this category")
    p.add_argument("--limit", type=int, default=None, help="cap number of cases")
    p.add_argument("--dry-run", action="store_true",
                   help="load and validate cases without executing")
    args = p.parse_args()

    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\ninterrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
