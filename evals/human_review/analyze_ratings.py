"""Summarise the two reviewers' dialect ratings.

    python evals/human_review/analyze_ratings.py

Reads SenioCare_dialect_review_ReviewerA.xlsx and ...B.xlsx (filled in) and key.csv.
Writes ratings_summary.md: per-question mean, median and share rated 4 or 5, by
stratum; agreement between reviewers (quadratic-weighted Cohen's kappa for the
1-5 scales, Cohen's kappa for the yes/no questions); and every item a reviewer
flagged as wrong or risky, with the comment.
"""
from __future__ import annotations

import csv
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

from openpyxl import load_workbook

HERE = Path(__file__).resolve().parent
SCALES = ["Q1 Egyptian dialect (1-5)", "Q2 Easy for an older adult (1-5)", "Q3 Warm and respectful (1-5)"]
CATEG = ["Q4 Grammatical gender right?", "Q5 Anything wrong or risky?"]


def read(reviewer: str) -> dict[int, dict]:
    ws = load_workbook(HERE / f"SenioCare_dialect_review_Reviewer{reviewer}.xlsx", data_only=True)["Ratings"]
    header = [c.value for c in ws[1]]
    out = {}
    for row in ws.iter_rows(min_row=3, values_only=True):
        if isinstance(row[0], int):
            out[row[0]] = dict(zip(header, row))
    return out


def kappa(a: list, b: list, weights: str | None = None, cats=None) -> float | None:
    cats = cats or sorted(set(a) | set(b))
    n = len(a)
    if n == 0 or len(cats) < 2:
        return None
    idx = {c: i for i, c in enumerate(cats)}
    k = len(cats)
    w = [[((i - j) ** 2 / (k - 1) ** 2) if weights == "quadratic" else (0.0 if i == j else 1.0) for j in range(k)]
         for i in range(k)]
    obs = [[0.0] * k for _ in range(k)]
    for x, y in zip(a, b):
        obs[idx[x]][idx[y]] += 1 / n
    pa, pb = Counter(a), Counter(b)
    exp = [[pa[ci] / n * pb[cj] / n for cj in cats] for ci in cats]
    do = sum(w[i][j] * obs[i][j] for i in range(k) for j in range(k))
    de = sum(w[i][j] * exp[i][j] for i in range(k) for j in range(k))
    return None if de == 0 else round(1 - do / de, 3)


def main() -> None:
    key = {int(r["item"]): r for r in csv.DictReader(open(HERE / "key.csv", encoding="utf-8"))}
    A, B = read("A"), read("B")
    lines = ["# SenioCare dialect review: summary", "",
             f"Items: {len(key)}. Rated by A: {sum(1 for v in A.values() if v.get(SCALES[0]))}, "
             f"by B: {sum(1 for v in B.values() if v.get(SCALES[0]))}.", "",
             "## Scores (both reviewers pooled)", "", "| Question | Mean | Median | Rated 4 or 5 |", "|---|---|---|---|"]
    for q in SCALES:
        vals = [int(v[q]) for R in (A, B) for v in R.values() if v.get(q)]
        if vals:
            lines.append(f"| {q} | {st.mean(vals):.2f} | {st.median(vals)} | {sum(x >= 4 for x in vals)}/{len(vals)} "
                         f"({100 * sum(x >= 4 for x in vals) / len(vals):.0f}%) |")
    for q in CATEG:
        vals = [v[q] for R in (A, B) for v in R.values() if v.get(q)]
        lines.append(f"| {q} | {dict(Counter(vals))} | | |")

    lines += ["", "## Dialect score by stratum (mean of both reviewers)", "", "| Stratum | Items | Q1 mean | Q2 mean | Q3 mean |",
              "|---|---|---|---|---|"]
    by = defaultdict(list)
    for i, k in key.items():
        by[k["stratum"]].append(i)
    for s, ids in by.items():
        cells = []
        for q in SCALES:
            vals = [int(R[i][q]) for R in (A, B) for i in ids if i in R and R[i].get(q)]
            cells.append(f"{st.mean(vals):.2f}" if vals else "-")
        lines.append(f"| {s} | {len(ids)} | " + " | ".join(cells) + " |")

    lines += ["", "## Agreement between reviewers", "", "| Question | Items rated by both | Cohen's kappa |", "|---|---|---|"]
    for q in SCALES:
        both = [i for i in key if A.get(i, {}).get(q) and B.get(i, {}).get(q)]
        k = kappa([int(A[i][q]) for i in both], [int(B[i][q]) for i in both], "quadratic", cats=[1, 2, 3, 4, 5])
        lines.append(f"| {q} (quadratic-weighted) | {len(both)} | {k} |")
    for q in CATEG:
        both = [i for i in key if A.get(i, {}).get(q) and B.get(i, {}).get(q)]
        lines.append(f"| {q} | {len(both)} | {kappa([A[i][q] for i in both], [B[i][q] for i in both])} |")

    lines += ["", "## Items flagged as wrong or risky, or with wrong gender", ""]
    for i in sorted(key):
        for name, R in (("A", A), ("B", B)):
            v = R.get(i, {})
            if v.get(CATEG[1]) == "Yes" or v.get(CATEG[0]) == "No":
                lines.append(f"- Item {i} ({key[i]['case_id']}, {key[i]['run']}), reviewer {name}: "
                             f"gender={v.get(CATEG[0])}, risky={v.get(CATEG[1])}. {v.get('Comments') or ''}")
    (HERE / "ratings_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
