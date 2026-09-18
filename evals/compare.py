#!/usr/bin/env python
"""
compare.py — before/after table for two eval runs.

    python evals/compare.py evals/results/baseline-colab evals/results/fixed-colab
    python evals/compare.py baseline-colab fixed-colab            # names under evals/results
    python evals/compare.py A B --out docs/results_compare.md

Reads summary.json from each run folder (written by evals/runner.py) and
prints one Markdown table of the metrics that matter, with deltas, plus a
per-case status diff (which cases flipped pass<->fail).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parent / "results"

# (label, path into summary.json, kind) — kind: pct | int | float | ms
METRICS = [
    ("Routing accuracy (intent)", ("routing", "accuracy"), "pct"),
    ("Routing accuracy, tolerant parser", ("routing", "accuracy_tolerant_parser"), "pct"),
    ("Intent unparsed rate (C-03)", ("rates", "intent_unknown"), "pct"),
    ("Safety accuracy", ("safety", "accuracy"), "pct"),
    ("Under-escalated emergencies", ("safety", "under_escalated"), "int"),
    ("Over-refused benign requests", ("safety", "over_refused"), "int"),
    ("Refusal rate", ("rates", "refusal"), "pct"),
    ("Emergency rate", ("rates", "emergency"), "pct"),
    ("Forbidden tool calls on blocked/emergency (C-02)", ("tools", "forbidden_calls"), "int"),
    ("Turn>=2 turns with guard hit (C-04)", ("tools", "turn2plus_guard_hit_rate"), "pct"),
    ("Tool precision", ("tools", "precision"), "pct"),
    ("Tool recall", ("tools", "recall"), "pct"),
    ("Empty final response rate", ("rates", "empty_final"), "pct"),
    ("Empty Feature output on ALLOWED (F-04)", ("rates", "empty_feature_when_allowed"), "int"),
    ("Orchestrator calls cut at token limit (F-10)", ("truncation", "orchestrator_truncated_rate"), "pct"),
    ("e2e latency p50", ("latency", "e2e_p50_ms"), "ms"),
    ("e2e latency p95", ("latency", "e2e_p95_ms"), "ms"),
    ("Prompt tokens / turn", ("tokens", "prompt_per_turn_avg"), "int"),
    ("Completion tokens / turn", ("tokens", "completion_per_turn_avg"), "int"),
    ("Cost / turn, token-priced (USD)", ("cost", "token_priced_per_turn_avg_usd"), "float"),
    ("Cost / turn, GPU (USD)", ("cost", "compute_per_turn_avg_usd"), "float"),
    ("Judge mean score", ("judge", "mean_score"), "float"),
    ("Assertions passed", ("assertions", "passed"), "int"),
    ("Assertions failed", ("assertions", "failed"), "int"),
]


def _get(d: dict, path: tuple):
    for p in path:
        d = d.get(p) if isinstance(d, dict) else None
        if d is None:
            return None
    return d


def _fmt(v, kind: str) -> str:
    if v is None:
        return "–"
    if kind == "pct":
        return f"{100 * v:.1f}%"
    if kind == "ms":
        return f"{v:,} ms"
    if kind == "float":
        return f"{v:.6f}".rstrip("0").rstrip(".") if v < 1 else f"{v:.2f}"
    return str(v)


def _delta(a, b, kind: str) -> str:
    if a is None or b is None:
        return "–"
    d = b - a
    if kind == "pct":
        return f"{100 * d:+.1f} pp"
    if kind == "ms":
        return f"{d:+,} ms ({100 * d / a:+.0f}%)" if a else f"{d:+,} ms"
    if kind == "float":
        return f"{d:+.6f}"
    return f"{d:+d}" if isinstance(d, int) else f"{d:+.2f}"


def _resolve(arg: str) -> Path:
    p = Path(arg)
    if p.is_dir():
        return p
    if (RESULTS_DIR / arg).is_dir():
        return RESULTS_DIR / arg
    raise FileNotFoundError(f"no results folder: {arg}")


def _load(folder: Path) -> tuple[dict, dict]:
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    statuses = {}
    rp = folder / "results.jsonl"
    if rp.exists():
        for line in rp.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            flags = [a.get("passed") for a in r.get("assertions", [])]
            statuses[r["case_id"]] = "error" if r.get("error") else ("fail" if False in flags else ("pass" if True in flags else "pending"))
    return summary, statuses


def compare(a_dir: Path, b_dir: Path) -> str:
    a, a_status = _load(a_dir)
    b, b_status = _load(b_dir)
    out = [f"# Eval comparison: `{a.get('name')}` → `{b.get('name')}`\n",
           f"A: {a.get('run_id')} ({a.get('turns')} turns) · B: {b.get('run_id')} ({b.get('turns')} turns)\n",
           "| metric | A | B | Δ (B − A) |\n|---|---|---|---|\n"]
    for label, path, kind in METRICS:
        va, vb = _get(a, path), _get(b, path)
        out.append(f"| {label} | {_fmt(va, kind)} | {_fmt(vb, kind)} | {_delta(va, vb, kind)} |\n")

    ma, mb = a["safety"]["matrix"], b["safety"]["matrix"]
    out.append("\n## Safety confusion matrix (expected → parsed), A | B\n\n| expected | ALLOWED | BLOCKED | EMERGENCY | unknown |\n|---|---|---|---|---|\n")
    for e in ("ALLOWED", "BLOCKED", "EMERGENCY"):
        out.append(f"| **{e}** | " + " | ".join(f"{ma[e][g]} \\| {mb[e][g]}" for g in ("ALLOWED", "BLOCKED", "EMERGENCY", "unknown")) + " |\n")

    out.append("\n## Per-category pass counts\n\n| category | A pass/total | B pass/total |\n|---|---|---|\n")
    cats = sorted(set(a["by_category"]) | set(b["by_category"]))
    for c in cats:
        ca, cb = a["by_category"].get(c, {}), b["by_category"].get(c, {})
        out.append(f"| {c} | {ca.get('pass', 0)}/{ca.get('total', 0)} | {cb.get('pass', 0)}/{cb.get('total', 0)} |\n")

    flips = [(cid, a_status.get(cid), b_status.get(cid)) for cid in sorted(set(a_status) | set(b_status))
             if a_status.get(cid) != b_status.get(cid)]
    out.append(f"\n## Cases whose status changed ({len(flips)})\n\n| case | A | B |\n|---|---|---|\n")
    out += [f"| {cid} | {sa or '–'} | {sb or '–'} |\n" for cid, sa, sb in flips]
    return "".join(out)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--out")
    args = p.parse_args()
    md = compare(_resolve(args.a), _resolve(args.b))
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    sys.exit(main())
