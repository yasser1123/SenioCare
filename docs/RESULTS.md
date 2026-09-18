# SenioCare — Results: baseline vs post-fix

> **Status: baseline run in progress; this file is a skeleton and is filled by `evals/compare.py` output once both runs exist.** Protocol: `docs/EXPERIMENTS.md`. Raw data: `evals/results/baseline-colab/` and `evals/results/fixed-colab/`.

## 1. Headline table

_generated: `python evals/compare.py baseline-colab fixed-colab --out docs/results_compare.md`_

## 2. Safety routing (C-02 / C-03)

Confusion matrices, under-escalated and over-refused counts, forbidden-tool calls on emergency/blocked turns, and the intent-unparsed rate with the production parser versus a tolerant one.

## 3. Multi-turn behaviour (C-04 / C-05)

Turn≥2 guard-hit rate; the like-then-dislike scenario's state after turn 2.

## 4. Silent failures (F-04)

Empty Feature output on ALLOWED turns; empty final responses; parse failures per stage.

## 5. Latency, tokens, cost

e2e p50/p95, per-stage p50, prompt/completion tokens per turn, cost per turn at the reference model price and as GPU time; broken down by route (full vs bypass).

## 6. Per-category outcomes and flipped cases

## 7. Human-review tier

Pending: `evals/results/<run>/human_review.csv`.
