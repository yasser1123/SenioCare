"""Exact CIs and paired McNemar tests for the SenioCare 2x2 (three cells) evaluation.

Reads evals/results/<run>/results.jsonl and the case files; writes stats.json + prints a summary.
Denominators follow the harness: routing = turns whose case declares expect.intent and that completed;
safety = turns whose case declares expect.safety_status and that completed.
"""
import json
import glob
import os
import sys
from scipy.stats import beta, binomtest

REPO = r"D:/PROJECTS/Graduation Project/SenioCare"
RUNS = {"A": "baseline-colab", "A'": "baseline-colab-16k", "C": "fixed-colab-16k"}


def cp(k, n, alpha=0.05):
    """Clopper-Pearson exact interval."""
    if n == 0:
        return (None, None)
    lo = 0.0 if k == 0 else beta.ppf(alpha / 2, k, n - k + 1)
    hi = 1.0 if k == n else beta.ppf(1 - alpha / 2, k + 1, n - k)
    return (lo, hi)


def load_cases():
    exp = {}
    for f in sorted(glob.glob(os.path.join(REPO, "evals/cases/*.jsonl"))):
        for line in open(f, encoding="utf-8"):
            c = json.loads(line)
            if c.get("turns"):
                for i, t in enumerate(c["turns"], 1):
                    exp[f"{c['id']}#t{i}"] = t.get("expect", {}) or {}
            else:
                exp[c["id"]] = c.get("expect", {}) or {}
    return exp


def load_run(name):
    out = {}
    for line in open(os.path.join(REPO, f"evals/results/{name}/results.jsonl"), encoding="utf-8"):
        x = json.loads(line)
        out[x["case_id"]] = x
    return out


def per_turn(run, exp):
    """Return dict turn_id -> outcome flags."""
    res = {}
    for tid, x in run.items():
        e = exp.get(tid, {})
        parsed = x.get("parsed") or {}
        errored = bool(x.get("error"))
        failed = [a for a in (x.get("assertions") or []) if a.get("passed") is False]
        struct_asserts = [a for a in (x.get("assertions") or []) if a.get("passed") is not None]
        res[tid] = {
            "errored": errored,
            "intent_expected": e.get("intent"),
            "intent_ok": (None if errored or not e.get("intent") else parsed.get("intent") == e.get("intent")),
            "safety_expected": e.get("safety_status"),
            "safety_ok": (None if errored or not e.get("safety_status") else parsed.get("safety_status") == e.get("safety_status")),
            "turn_pass": (None if not struct_asserts else (not failed)),
            "category": x.get("category"),
        }
    return res


def mcnemar(a, b, key):
    """Exact McNemar on turns where both runs have a defined outcome for `key`."""
    both = [t for t in a if t in b and a[t][key] is not None and b[t][key] is not None]
    b_only = sum(1 for t in both if (not a[t][key]) and b[t][key])   # first wrong, second right
    a_only = sum(1 for t in both if a[t][key] and not b[t][key])     # first right, second wrong
    n = b_only + a_only
    p = binomtest(min(b_only, a_only), n, 0.5).pvalue if n else 1.0
    return {"pairs": len(both), "improved": b_only, "worsened": a_only, "p_exact": p}


def main():
    exp = load_cases()
    runs = {k: per_turn(load_run(v), exp) for k, v in RUNS.items()}
    out = {"proportions": {}, "mcnemar": {}}
    for k, r in runs.items():
        for key in ("intent_ok", "safety_ok", "turn_pass"):
            vals = [v[key] for v in r.values() if v[key] is not None]
            kk, n = sum(vals), len(vals)
            lo, hi = cp(kk, n)
            out["proportions"][f"{k}:{key}"] = {"k": kk, "n": n, "p": kk / n if n else None, "ci95": [lo, hi]}
    # emergency sub-metrics
    for k, r in runs.items():
        em = [v for v in r.values() if v["safety_expected"] == "EMERGENCY" and v["safety_ok"] is not None]
        caught = sum(1 for v in em if v["safety_ok"])
        lo, hi = cp(caught, len(em))
        out["proportions"][f"{k}:emergency_recall"] = {"k": caught, "n": len(em), "ci95": [lo, hi]}
        allowed = [v for v in r.values() if v["safety_expected"] == "ALLOWED" and v["safety_ok"] is not None]
        ok = sum(1 for v in allowed if v["safety_ok"])
        lo, hi = cp(ok, len(allowed))
        out["proportions"][f"{k}:allowed_specificity"] = {"k": ok, "n": len(allowed), "ci95": [lo, hi]}
    # emergency number: 1 of 7 in C, 4 of 8 in A'
    for k, (kk, n) in {"C": (1, 7), "A'": (4, 8)}.items():
        out["proportions"][f"{k}:emergency_number_present"] = {"k": kk, "n": n, "ci95": list(cp(kk, n))}
    for a, b in (("A", "A'"), ("A'", "C"), ("A", "C")):
        for key in ("intent_ok", "safety_ok", "turn_pass"):
            out["mcnemar"][f"{a}->{b}:{key}"] = mcnemar(runs[a], runs[b], key)
    # A'->C turn_pass excluding the harness artefact F-13 (mt-pref-conflict-001#t1)
    ra = {t: v for t, v in runs["A'"].items() if t != "mt-pref-conflict-001#t1"}
    rc = {t: v for t, v in runs["C"].items() if t != "mt-pref-conflict-001#t1"}
    out["mcnemar"]["A'->C:turn_pass_excl_F13"] = mcnemar(ra, rc, "turn_pass")
    json.dump(out, open(sys.argv[1], "w"), indent=1)
    for k, v in out["proportions"].items():
        lo, hi = v["ci95"]
        print(f"{k:32s} {v['k']:>3}/{v['n']:<3} CI95 [{lo*100:5.1f}, {hi*100:5.1f}]")
    for k, v in out["mcnemar"].items():
        print(f"{k:32s} pairs={v['pairs']:>2} improved={v['improved']:>2} worsened={v['worsened']:>2} p={v['p_exact']:.2g}")


if __name__ == "__main__":
    main()
