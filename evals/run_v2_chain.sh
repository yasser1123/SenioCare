#!/usr/bin/env bash
# Runs the v2 protocol (docs/EXPERIMENTS_v2.md §5) on two GPU hosts at once,
# one run at a time per host:
#   colab   D1 (started separately) -> D2          model URL from .env
#   kaggle  F -> E -> D3                           model URL from evals/results/kaggle_api_base.txt
# Every run uses --resume, so re-running a lane after a tunnel drop continues
# where it stopped; finished runs (summary.json present) are skipped.
#   usage: bash evals/run_v2_chain.sh colab|kaggle
set -u
cd "$(dirname "$0")/.."
export PYTHONIOENCODING=utf-8 EVAL_TURN_TIMEOUT_S=600 PYTHONUNBUFFERED=1
PY=.venv/Scripts/python.exe
C=evals/cases
CORE="$C/07_personalization.jsonl,$C/08_safety_v2.jsonl,$C/09_images.jsonl,$C/10_memory.jsonl"
LANE=${1:?colab or kaggle}

run() {  # name, cases, extra env
  local name=$1 cases=$2; shift 2
  if [ -f "evals/results/$name/summary.json" ]; then echo "skip $name (done)"; return; fi
  local hostenv=(EVAL_GPU_HOST=colab-t4)
  if [ "$LANE" = kaggle ]; then
    hostenv=(EVAL_GPU_HOST=kaggle-t4 "MODEL_API_BASE=$(tr -d ' \r\n' < evals/results/kaggle_api_base.txt)")
  fi
  echo "=== $name start $(date -u +%FT%TZ)"
  env "${hostenv[@]}" "$@" $PY evals/runner.py --name "$name" --resume --cases "$cases" > "evals/results/$name.log" 2>&1; local rc=$?
  echo "=== $name end $(date -u +%FT%TZ) exit=$rc"
}

if [ "$LANE" = colab ]; then
  until [ -f evals/results/v2-full-r1/summary.json ]; do sleep 60; done
  run v2-core-r2 "$CORE"
else
  run v2-noprofile "$C/07_personalization.jsonl,$C/10_memory.jsonl" SENIOCARE_PROFILE_IN_PROMPT=0
  run v2-nolayer   "$C/04_emergency.jsonl,$C/08_safety_v2.jsonl,$C/09_images.jsonl" SENIOCARE_SAFETY_LAYER=0
  run v2-core-r3   "$CORE"
fi
echo "=== $LANE lane done $(date -u +%FT%TZ)"
