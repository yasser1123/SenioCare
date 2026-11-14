"""Statistics for the v2 evaluation (docs/EXPERIMENTS_v2.md §7).

Per run: every metric as k/n with an exact Clopper-Pearson 95% CI.
Paired: full run D1 vs each ablation (F no profile, E no safety layer), turn by
turn on the shared cases, with an exact McNemar test.
Repeats: D1, D2, D3 on the 93 core turns - per-metric rate per run, and per-turn
consistency (passed in every run / failed in every run / flipped).

    python docs/paper/build/stats_v2.py        -> stats_v2.json, stats_v2.md next to this file
"""
from __future__ import annotations

import json
import os
import re
import statistics
from pathlib import Path

from scipy.stats import beta, binomtest

REPO = Path(__file__).resolve().parents[3]
RESULTS = REPO / "evals" / "results"
OUT = Path(__file__).resolve().parent
RUNS = {"D1": "v2-full-r1", "F": "v2-noprofile", "E": "v2-nolayer", "D2": "v2-core-r2", "D3": "v2-core-r3"}
CORE_PREFIXES = ("pers-", "safe2-", "img2-", "mem-")   # files 07-10


def cp(k: int, n: int, alpha: float = 0.05):
    if n == 0:
        return (None, None)
    lo = 0.0 if k == 0 else beta.ppf(alpha / 2, k, n - k + 1)
    hi = 1.0 if k == n else beta.ppf(1 - alpha / 2, k + 1, n - k)
    return (round(float(lo), 3), round(float(hi), 3))


def load(name: str) -> dict:
    path = RESULTS / name / "results.jsonl"
    if not path.exists():
        return {}
    return {x["case_id"]: x for x in (json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip())}


def metrics(x: dict) -> dict[str, bool | None]:
    """Turn -> {metric: passed}. Only metrics the case actually tests are present."""
    m: dict[str, bool | None] = {}
    if x.get("error"):
        return {"completed": False}
    m["completed"] = True
    cid, cat = x["case_id"], x.get("category") or ""
    for a in x.get("assertions") or []:
        name, ok = a["name"], a["passed"]
        if ok is None:
            continue
        if name == "safety_status":
            m["safety_correct"] = ok
        elif name == "intent":
            m["routing_correct"] = ok
        elif name == "meal_within_profile":
            m["meal_safe_for_profile"] = ok
        elif name == "exercise_within_profile":
            m["exercise_within_profile"] = ok
        elif name == "no_unlisted_medications":
            m["no_unlisted_medication"] = ok
        elif name == "no_foreign_emergency_number":
            m["no_foreign_number"] = ok
        elif name == "emergency_number_first":
            m["number_123_first"] = ok
        elif name == "contains '16328'":
            m["crisis_line_16328"] = ok
        elif name.startswith("contains '") and cid.startswith("pers-"):
            m["uses_name"] = ok
        elif name.startswith("contains_any") and cid.startswith("pers-"):
            m["condition_aware"] = ok
        elif name.startswith("contains_any") and cat == "memory":
            m["memory_recall"] = ok
        elif name.startswith("state:user:memory_facts"):
            m["memory_saved"] = ok
        elif name == "tools_not_called":
            m["no_forbidden_tool"] = ok
        elif name == "arabic_script":
            m["arabic_script"] = ok
    checks = [a["passed"] for a in x.get("assertions") or [] if a["passed"] is not None]
    if checks:
        m["turn_all_checks_pass"] = all(checks)
    return m


def rate(turns: dict, metric: str, only=None) -> dict:
    vals = [t[metric] for tid, t in turns.items() if metric in t and (only is None or only(tid))]
    k, n = sum(vals), len(vals)
    return {"k": k, "n": n, "rate": round(k / n, 3) if n else None, "ci95": cp(k, n)}


def mcnemar(a: dict, b: dict, metric: str) -> dict:
    both = [t for t in a if t in b and metric in a[t] and metric in b[t]]
    improved = sum(1 for t in both if not a[t][metric] and b[t][metric])   # D1 wrong, ablation right
    worsened = sum(1 for t in both if a[t][metric] and not b[t][metric])   # D1 right, ablation wrong
    n = improved + worsened
    p = binomtest(min(improved, worsened), n, 0.5).pvalue if n else 1.0
    return {"pairs": len(both), "D1_k": sum(bool(a[t][metric]) for t in both),
            "ablation_k": sum(bool(b[t][metric]) for t in both),
            "D1_right_ablation_wrong": worsened, "D1_wrong_ablation_right": improved,
            "p_exact": float(f"{float(p):.3g}")}


def emergency_latency(run: dict) -> dict:
    lat = [x["e2e_latency_ms"] for x in run.values()
           if not x.get("error") and (x.get("parsed") or {}).get("safety_status") == "EMERGENCY" and x.get("e2e_latency_ms") is not None]
    return {"n": len(lat), "p50_ms": statistics.median(lat) if lat else None, "max_ms": max(lat) if lat else None}


def main() -> None:
    raw = {k: load(v) for k, v in RUNS.items()}
    runs = {k: {tid: metrics(x) for tid, x in v.items()} for k, v in raw.items() if v}
    all_metrics = sorted({m for t in runs.get("D1", {}).values() for m in t})
    out: dict = {"runs": {k: RUNS[k] for k in runs}, "per_run": {}, "paired": {}, "repeats": {}, "emergency_latency": {}}

    for k, turns in runs.items():
        out["per_run"][k] = {m: rate(turns, m) for m in all_metrics if any(m in t for t in turns.values())}
        out["emergency_latency"][k] = emergency_latency(raw[k])

    pairs = {"F": ["uses_name", "meal_safe_for_profile", "exercise_within_profile", "condition_aware",
                   "no_unlisted_medication", "memory_recall", "memory_saved", "turn_all_checks_pass"],
             "E": ["number_123_first", "crisis_line_16328", "no_foreign_number", "no_forbidden_tool",
                   "safety_correct", "turn_all_checks_pass"]}
    for abl, ms in pairs.items():
        if abl in runs and "D1" in runs:
            out["paired"][f"D1_vs_{abl}"] = {m: mcnemar(runs["D1"], runs[abl], m) for m in ms}

    reps = [r for r in ("D1", "D2", "D3") if r in runs]
    core = lambda tid: tid.startswith(CORE_PREFIXES)
    if len(reps) > 1:
        for m in all_metrics:
            ids = [t for t in runs["D1"] if core(t) and all(t in runs[r] and m in runs[r][t] for r in reps)]
            if not ids:
                continue
            vals = {t: [runs[r][t][m] for r in reps] for t in ids}
            out["repeats"][m] = {
                "runs": reps, "turns": len(ids),
                "rate_per_run": {r: rate({t: runs[r][t] for t in ids}, m)["rate"] for r in reps},
                "pass_all_runs": sum(all(v) for v in vals.values()),
                "fail_all_runs": sum(not any(v) for v in vals.values()),
                "flipped": sum(any(v) and not all(v) for v in vals.values()),
            }

    (OUT / "stats_v2.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# v2 statistics", "", f"Runs: {', '.join(f'{k}={v}' for k, v in out['runs'].items())}", "",
             "## Per run (k/n, exact 95% CI)", "", "| metric | " + " | ".join(runs) + " |", "|---|" + "---|" * len(runs)]
    for m in all_metrics:
        cells = []
        for k in runs:
            r = out["per_run"][k].get(m)
            cells.append(f"{r['k']}/{r['n']} [{r['ci95'][0]:.2f}–{r['ci95'][1]:.2f}]" if r and r["n"] else "–")
        lines.append(f"| {m} | " + " | ".join(cells) + " |")
    lines += ["", "## Emergency reply latency", ""]
    lines += [f"- {k}: p50 {v['p50_ms']} ms, max {v['max_ms']} ms (n={v['n']})" for k, v in out["emergency_latency"].items()]
    for name, ms in out["paired"].items():
        lines += ["", f"## Paired {name} (exact McNemar)", "", "| metric | pairs | D1 right, ablation wrong | D1 wrong, ablation right | p |", "|---|---|---|---|---|"]
        lines += [f"| {m} | {v['pairs']} | {v['D1_right_ablation_wrong']} | {v['D1_wrong_ablation_right']} | {v['p_exact']} |" for m, v in ms.items()]
    if out["repeats"]:
        lines += ["", "## Repeats on the core turns", "", "| metric | turns | rate per run | pass all | fail all | flipped |", "|---|---|---|---|---|---|"]
        lines += [f"| {m} | {v['turns']} | {v['rate_per_run']} | {v['pass_all_runs']} | {v['fail_all_runs']} | {v['flipped']} |"
                  for m, v in out["repeats"].items()]
    (OUT / "stats_v2.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
