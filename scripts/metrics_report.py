#!/usr/bin/env python
"""
metrics_report.py — aggregate llm_traces into Markdown (and CSV) tables.

Same SQL as GET /metrics/summary (app/metrics_queries.py), so the numbers in
the paper and the numbers in the API cannot disagree.

    python scripts/metrics_report.py                       # last 24 h, Markdown to stdout
    python scripts/metrics_report.py --hours 168 --out docs/metrics_week.md
    python scripts/metrics_report.py --since 2026-09-18T10:00:00+00:00 --until 2026-09-18T12:00:00+00:00
    python scripts/metrics_report.py --csv-dir evals/results/baseline/metrics
    python scripts/metrics_report.py --json                # raw summary dict
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from app import metrics_queries  # noqa: E402


def _fmt(v) -> str:
    if v is None:
        return "–"
    if isinstance(v, float):
        if abs(v) < 0.01:
            return f"{v:.6f}".rstrip("0").rstrip(".") if v else "0"
        return f"{v:,.2f}"
    try:
        from decimal import Decimal

        if isinstance(v, Decimal):
            return _fmt(float(v))
    except ImportError:  # pragma: no cover
        pass
    return str(v)


def table(rows: list[dict], columns: list[tuple[str, str]]) -> str:
    """columns: [(key, header), ...]"""
    if not rows:
        return "_no data in this window_\n"
    head = "| " + " | ".join(h for _, h in columns) + " |"
    sep = "|" + "|".join("---" for _ in columns) + "|"
    body = ["| " + " | ".join(_fmt(r.get(k)) for k, _ in columns) + " |" for r in rows]
    return "\n".join([head, sep, *body]) + "\n"


def to_markdown(data: dict) -> str:
    w = data["window"]
    t = data["turns"]["summary"]
    out = [f"# SenioCare metrics — {w['start'][:19]} → {w['end'][:19]} UTC\n"]

    out.append("## Turns (end-to-end)\n")
    out.append(table([t], [
        ("turns", "turns"), ("e2e_p50_ms", "e2e p50 ms"), ("e2e_p95_ms", "e2e p95 ms"),
        ("llm_share_of_e2e", "LLM share of e2e"), ("llm_calls_avg", "LLM calls/turn"),
        ("prompt_tokens_avg", "prompt tok/turn"), ("completion_tokens_avg", "compl. tok/turn"),
        ("cost_token_priced_avg_usd", "cost/turn (ref $)"), ("cost_compute_avg_usd", "cost/turn (GPU $)"),
    ]))
    out.append(table([t], [
        ("intent_unknown", "intent unparsed"), ("safety_unparsed", "safety unparsed"),
        ("emergencies", "emergencies"), ("empty_final", "empty final"),
        ("already_called_total", "tool guard hits (C-04)"), ("tool_errors_total", "tool errors"),
    ]))

    out.append("## Turns by intent × safety status\n")
    out.append(table(data["turns"]["by_intent"], [
        ("intent", "intent"), ("safety_status", "safety"), ("turns", "turns"),
        ("e2e_p50_ms", "e2e p50 ms"), ("cost_token_priced_avg_usd", "cost/turn (ref $)"),
    ]))

    out.append("## LLM calls by stage\n")
    out.append(table(data["llm_by_stage"], [
        ("stage", "stage"), ("calls", "calls"), ("latency_p50_ms", "p50 ms"), ("latency_p95_ms", "p95 ms"),
        ("prompt_tokens_avg", "prompt tok avg"), ("completion_tokens_avg", "compl. tok avg"),
        ("calls_requesting_tools", "with tool calls"), ("errors", "errors"),
        ("cost_token_priced_usd", "cost (ref $)"), ("cost_compute_usd", "cost (GPU $)"),
    ]))

    out.append("## Stage outputs\n")
    out.append(table(data["stages"], [
        ("stage", "stage"), ("runs", "runs"), ("latency_p50_ms", "p50 ms"), ("latency_p95_ms", "p95 ms"),
        ("parse_ok", "parse ok"), ("empty_output", "empty"), ("output_chars_avg", "chars avg"),
    ]))

    out.append("## Tools\n")
    out.append(table(data["tools"], [
        ("tool", "tool"), ("calls", "calls"), ("latency_p50_ms", "p50 ms"), ("latency_p95_ms", "p95 ms"),
        ("latency_max_ms", "max ms"), ("already_called", "already_called"), ("errors", "errors"),
    ]))

    out.append("## SerpAPI\n")
    out.append(table(data["serpapi"], [("engine", "engine"), ("calls", "calls"), ("cost_usd", "cost $"), ("failures", "failures")]))

    out.append("## Emergency escalation\n")
    em = list(data["emergency"].values())
    out.append(table(em, [("kind", "step"), ("n", "n"), ("ok", "ok"), ("sent", "pushes sent"), ("failed", "pushes failed")]))

    out.append("## HTTP\n")
    out.append(table(data["http"], [
        ("method", "method"), ("path", "path"), ("requests", "requests"),
        ("latency_p50_ms", "p50 ms"), ("latency_p95_ms", "p95 ms"), ("errors_5xx", "5xx"),
    ]))
    return "\n".join(out)


def write_csv(data: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    sections = {
        "llm_by_stage": data["llm_by_stage"],
        "stages": data["stages"],
        "turns_summary": [data["turns"]["summary"]],
        "turns_by_intent": data["turns"]["by_intent"],
        "tools": data["tools"],
        "serpapi": data["serpapi"],
        "emergency": list(data["emergency"].values()),
        "http": data["http"],
    }
    for name, rows in sections.items():
        if not rows:
            continue
        with open(out_dir / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--hours", type=float, default=24)
    parser.add_argument("--since", help="ISO-8601 start")
    parser.add_argument("--until", help="ISO-8601 end")
    parser.add_argument("--out", help="write Markdown here instead of stdout")
    parser.add_argument("--csv-dir", help="also write one CSV per table into this directory")
    parser.add_argument("--json", action="store_true", help="print the raw summary as JSON")
    args = parser.parse_args()

    from seniocare.data.database import get_connection

    conn = get_connection()
    try:
        data = metrics_queries.summary(conn, hours=args.hours, since=args.since, until=args.until)
    finally:
        conn.close()

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        return 0
    md = to_markdown(data)
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(md)
    if args.csv_dir:
        write_csv(data, Path(args.csv_dir))
        print(f"wrote CSVs to {args.csv_dir}")
    return 0


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    sys.exit(main())
