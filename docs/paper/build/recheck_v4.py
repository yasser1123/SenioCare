"""Deterministic re-check of the post-evaluation fixes on the paper's own test inputs (v4).

The fixes made after the evaluated commit 7c71761 are all in deterministic code:
the emergency and self-harm templates (gendered verbs, an alert line that no longer
claims delivery) and the drug-food tool (unknown pairs no longer labelled "no
interaction found"). None of them changes what the model sees or decides, so they
can be re-checked without the model:

  1. every emergency or self-harm reply that runs D1, D2 and D3 produced from a
     template is rebuilt with the current code from the same message and profile,
     re-scored with the paper's scorer (runner.evaluate, scorer v3) and compared
     with the evaluated reply; the screen is also re-run on the message;
  2. the same replies are rebuilt as if caregivers were linked, to check the alert
     line (it never appeared in the evaluation, because no profile had caregivers);
  3. every drug-food tool call the model made in D1, D2 and D3 is replayed with the
     same arguments and profile through the evaluated tool (7c71761) and the
     current one, and the outputs are compared.

Not covered: anything the model decides. This is not a re-run of the evaluation.

    python docs/paper/build/recheck_v4.py   -> recheck_v4.json next to this file
"""
from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
from dataclasses import fields
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "evals"))

import runner  # noqa: E402
from seniocare import safety  # noqa: E402
from seniocare.tools import interactions as current_tool  # noqa: E402

RESULTS = REPO / "evals" / "results"
OUT = Path(__file__).resolve().parent
RUNS = {"D1": "v2-full-r1", "D2": "v2-core-r2", "D3": "v2-core-r3"}
EVALUATED = "7c71761"
TEMPLATES = ("template_emergency", "template_self_harm")


class _Ctx:
    def __init__(self, state: dict):
        self.state = state


def _evaluated_tool():
    src = subprocess.run(["git", "show", f"{EVALUATED}:seniocare/tools/interactions.py"], cwd=REPO,
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    path = Path(tempfile.mkdtemp()) / "interactions_7c71761.py"
    path.write_text(src, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("interactions_7c71761", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _cases() -> dict:
    out = {}
    for c in runner.load_cases(REPO / "evals" / "cases"):
        if c.is_scenario:
            for i in range(len(c.turns)):
                tc = c.turn_case(i)
                out[tc.id] = tc
        else:
            out[c.id] = c
    return out


def _result(rec: dict):
    names = {f.name for f in fields(runner.Result)}
    return runner.Result(**{k: v for k, v in rec.items() if k in names})


def _verdicts(assertions) -> dict:
    return {a["name"]: a["passed"] for a in assertions}


def templates(run_key: str, recs: list, cases: dict, profiles: dict) -> dict:
    rows = []
    for rec in recs:
        snap = rec.get("state_snapshot") or {}
        src = snap.get("reply_source")
        if rec.get("error") or src not in TEMPLATES:
            continue
        prof = profiles.get(rec["profile"]) or {}
        msg = rec["input"]
        hit = safety.screen(msg)
        screen_same = (hit.kind if hit else None) == snap.get("safety_screen")
        if src == "template_self_harm":
            kind = "self_harm"
        else:
            kind = hit.kind if hit else safety.category_for(msg)
        kind_same = kind == snap.get("emergency_kind", kind)
        kw = dict(name=prof.get("user:user_name"), gender=prof.get("user:gender"))
        build = safety.build_self_harm_reply if kind == "self_harm" else (
            lambda **k: safety.build_emergency_reply(kind, **k))
        linked = bool(prof.get("user:caregivers"))
        new = build(**kw, has_caregivers=linked)
        with_cg = build(**kw, has_caregivers=True)

        before = _verdicts(rec["assertions"])
        r2 = _result(copy.deepcopy(rec))
        r2.final_response = new
        after = _verdicts(runner.evaluate(cases[rec["case_id"]], r2))
        regressions = [n for n, v in before.items() if v is True and after.get(n) is False]
        fixes = [n for n, v in before.items() if v is False and after.get(n) is True]

        first = with_cg.splitlines()[0] if with_cg else ""
        rows.append({
            "case": rec["case_id"], "kind": kind, "gender": prof.get("user:gender"),
            "caregivers_linked": linked, "screen_same": screen_same, "kind_same": kind_same,
            "text_changed": new != rec.get("final_response"),
            "checks_before": sum(v is True for v in before.values()),
            "checks_after": sum(v is True for v in after.values()),
            "regressions": regressions, "fixes": fixes,
            "with_caregivers": {
                # the self-harm reply leads with empathy and 16328 by design; 123 comes later
                "123_on_first_line": (safety.AMBULANCE in with_cg) if kind == "self_harm" else (safety.AMBULANCE in first),
                "16328_present": (safety.MENTAL_HEALTH_HOTLINE in with_cg) if kind == "self_harm" else None,
                "foreign_number": safety.has_foreign_emergency_number(with_cg),
                "delivery_hedged": "مش متأكدين" in with_cg,
            },
        })
    return {
        "replies": len(rows),
        "screen_same": sum(r["screen_same"] for r in rows),
        "kind_same": sum(r["kind_same"] for r in rows),
        "text_changed": sum(r["text_changed"] for r in rows),
        "text_changed_female": sum(r["text_changed"] and r["gender"] == "female" for r in rows),
        "text_changed_male": sum(r["text_changed"] and r["gender"] != "female" for r in rows),
        "checks_passed_before": sum(r["checks_before"] for r in rows),
        "checks_passed_after": sum(r["checks_after"] for r in rows),
        "regressions": sum(len(r["regressions"]) for r in rows),
        "fixes": sum(len(r["fixes"]) for r in rows),
        "with_caregivers_all_ok": sum(
            r["with_caregivers"]["123_on_first_line"] and not r["with_caregivers"]["foreign_number"]
            and r["with_caregivers"]["delivery_hedged"] and r["with_caregivers"]["16328_present"] is not False
            for r in rows),
        "rows": rows,
    }


def drug_food(recs: list, profiles: dict, old) -> dict:
    calls = same_findings = unknown_pairs_relabelled = old_no_interaction_label = 0
    for rec in recs:
        if rec.get("error"):
            continue
        prof = profiles.get(rec["profile"]) or {}
        for t in rec.get("tool_args") or []:
            if t.get("tool") != "check_drug_food_interaction":
                continue
            foods = (t.get("args") or {}).get("food_names") or []
            a = old.check_drug_food_interaction(foods, _Ctx(dict(prof)))
            b = current_tool.check_drug_food_interaction(foods, _Ctx(dict(prof)))
            calls += 1
            keys = ("status", "harmful_interactions", "positive_interactions", "neutral_interactions",
                    "has_severe_interaction", "total_interactions", "warning")
            same_findings += all(a.get(k) == b.get(k) for k in keys)
            old_no_interaction_label += len(a.get("safe_combinations") or [])
            unknown_pairs_relabelled += len(b.get("pairs_not_in_knowledge_base") or [])
    return {"tool_calls_replayed": calls, "identical_interaction_findings": same_findings,
            "pairs_labelled_no_interaction_found_in_evaluated_code": old_no_interaction_label,
            "same_pairs_now_labelled_not_in_knowledge_base": unknown_pairs_relabelled}


def main() -> None:
    cases = _cases()
    profiles = runner.load_profiles()
    old = _evaluated_tool()
    out = {"evaluated_commit": EVALUATED, "templates": {}, "drug_food": {}}
    for k, name in RUNS.items():
        recs = [json.loads(l) for l in (RESULTS / name / "results.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        out["templates"][k] = templates(k, recs, cases, profiles)
        out["drug_food"][k] = drug_food(recs, profiles, old)
    (OUT / "recheck_v4.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    brief = {k: {kk: vv for kk, vv in v.items() if kk != "rows"} for k, v in out["templates"].items()}
    print(json.dumps({"templates": brief, "drug_food": out["drug_food"]}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
