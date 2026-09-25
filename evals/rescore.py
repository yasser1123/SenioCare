"""Re-score a finished eval run with the current assertions, without calling the model.

Scoring is deterministic over the saved replies, tool calls and state, so a
checker fix (e.g. scorer v2, EXERCISE_MATCH_NAMES in runner.py) can be applied to
runs that already finished. The original results are kept next to the new ones.

    python evals/rescore.py evals/results/v2-full-r1 [evals/results/v2-noprofile ...]
"""
from __future__ import annotations

import json
import shutil
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner  # noqa: E402

CASES_DIR = Path(__file__).resolve().parent / "cases"


def rescore(run_dir: Path) -> None:
    src = run_dir / "results.jsonl"
    if not src.exists():
        raise SystemExit(f"{run_dir}: no results.jsonl (run not finished)")
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    if config.get("scorer_version", 1) == runner.SCORER_VERSION:
        print(f"{run_dir.name}: already scorer v{runner.SCORER_VERSION}")
        return
    backup = run_dir / f"results.scorer_v{config.get('scorer_version', 1)}.jsonl"
    if not backup.exists():
        shutil.copy(src, backup)

    cases_by_id: dict = {}                    # scenario turns are scored as their own cases, as in runner.main_async
    for c in runner.load_cases(CASES_DIR):
        if c.is_scenario:
            for i in range(len(c.turns)):
                tc = c.turn_case(i)
                cases_by_id[tc.id] = tc
        else:
            cases_by_id[c.id] = c
    results = [runner.Result(**json.loads(line)) for line in src.read_text(encoding="utf-8").splitlines() if line.strip()]
    changed = 0
    for r in results:
        before = [(a["name"], a["passed"]) for a in r.assertions]
        r.assertions = runner.evaluate(cases_by_id[r.case_id], r)
        changed += before != [(a["name"], a["passed"]) for a in r.assertions]

    with open(src, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
    summary = runner.build_summary(results, cases_by_id, config["run_id"], config["name"])
    (run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "summary.md").write_text(runner.summary_markdown(summary, results), encoding="utf-8")
    config.update(scorer_version=runner.SCORER_VERSION,
                  rescored_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    (run_dir / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{run_dir.name}: rescored {len(results)} turns, {changed} changed; original kept as {backup.name}")


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        rescore(Path(arg))
