#!/usr/bin/env bash
# Runs the v2 protocol after D1, one run at a time (docs/EXPERIMENTS_v2.md §5).
# Each run uses --resume, so re-running this script after a tunnel drop
# continues where it stopped; finished runs (summary.json present) are skipped.
set -u
cd "$(dirname "$0")/.."
export PYTHONIOENCODING=utf-8 EVAL_TURN_TIMEOUT_S=600 PYTHONUNBUFFERED=1
PY=.venv/Scripts/python.exe
C=evals/cases
CORE="$C/07_personalization.jsonl,$C/08_safety_v2.jsonl,$C/09_images.jsonl,$C/10_memory.jsonl"

run() {  # name, cases ("" = all), extra env
  local name=$1 cases=$2; shift 2
  if [ -f "evals/results/$name/summary.json" ]; then echo "skip $name (done)"; return; fi
  echo "=== $name start $(date -u +%FT%TZ)"
  env "$@" $PY evals/runner.py --name "$name" --resume ${cases:+--cases "$cases"} > "evals/results/$name.log" 2>&1; local rc=$?
  echo "=== $name end $(date -u +%FT%TZ) exit=$rc"
}

# wait for D1 (already running separately)
until [ -f evals/results/v2-full-r1/summary.json ]; do sleep 60; done

run v2-noprofile "$C/07_personalization.jsonl,$C/10_memory.jsonl" SENIOCARE_PROFILE_IN_PROMPT=0
run v2-nolayer   "$C/04_emergency.jsonl,$C/08_safety_v2.jsonl,$C/09_images.jsonl" SENIOCARE_SAFETY_LAYER=0
run v2-core-r2   "$CORE"
run v2-core-r3   "$CORE"
echo "=== chain done $(date -u +%FT%TZ)"
