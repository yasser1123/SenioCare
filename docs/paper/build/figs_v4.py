"""Figures for the revised SenioCare paper (v4, second-round review).

    python figs_v4.py <out_dir> <stats_v2.json> <stats.json>

Changes from figs_v2.py, made for the reviewer's presentation comments:
- every figure is drawn at its printed width (17 cm = 6.7 in), so font sizes are
  the sizes on the page; no text is smaller than 7 pt;
- one colour code across Figs 1 and 3: blue = model (LLM) stage, orange =
  deterministic code, green = data store, grey = app, back end or external service;
- one arrow code: solid = request or data flow, double-headed = read and write,
  dashed = push notification requested for a device;
- each figure is saved as vector PDF and SVG and as a 600 dpi PNG (the PNG is
  embedded in the .docx; the PDF/SVG are for the journal's production files).
The data come from the same stats files as v2; no number changed.
"""
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Patch
from matplotlib.lines import Line2D

OUT = sys.argv[1]
S = json.load(open(sys.argv[2], encoding="utf-8"))
S1 = json.load(open(sys.argv[3], encoding="utf-8"))
os.makedirs(OUT, exist_ok=True)

W = 6.7  # inches, printed width
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTED, GRID = "#0b0b0b", "#3d3c3a", "#77766f", "#e4e3df"
TINT = {"llm": "#dcebfb", "code": "#fde4d8", "data": "#d6f3e8", "plain": "#f3f2ef", "none": "white"}
EDGE = {"llm": BLUE, "code": ORANGE, "data": "#138a60", "plain": "#8a8984", "none": "#8a8984"}
TS, LS, AS = 8.4, 7.3, 7.2  # title, line and arrow-label sizes (pt)
LW = 1.0  # one line weight for boxes and arrows

plt.rcParams.update({
    "font.family": "Arial", "font.size": 8, "axes.edgecolor": MUTED, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "axes.linewidth": 0.6, "figure.facecolor": "white",
    "svg.fonttype": "none", "pdf.fonttype": 42,
})


def save(fig, name):
    for ext, kw in (("pdf", {}), ("svg", {}), ("png", {"dpi": 600})):
        fig.savefig(os.path.join(OUT, f"{name}.{ext}"), **kw)
    plt.close(fig)


def canvas(h):
    fig = plt.figure(figsize=(W, h))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    return fig, ax


def box(ax, H, x, y, w, h, title, lines=(), kind="plain", ts=TS, ls=LS, lw=LW):
    """H = figure height in inches, used to space text lines in axes units."""
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.006,rounding_size=0.012",
                                linewidth=lw, edgecolor=EDGE[kind], facecolor=TINT[kind]))
    line = lambda pt: pt * 1.32 / 72 / H
    if lines:
        top = y + h - 0.35 * line(ts)
        ax.text(x + w / 2, top, title, ha="center", va="top", fontsize=ts, fontweight="bold", color=INK)
        ax.text(x + w / 2, top - 1.15 * line(ts), "\n".join(lines), ha="center", va="top",
                fontsize=ls, color=INK2, linespacing=1.32)
    else:
        ax.text(x + w / 2, y + h / 2, title, ha="center", va="center", fontsize=ts, fontweight="bold", color=INK)


def arrow(ax, x1, y1, x2, y2, label=None, both=False, dashed=False, lx=0, ly=0, rad=0.0, color=INK2, ha="center"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="<|-|>" if both else "-|>", mutation_scale=9,
                                 linewidth=LW, color=color, linestyle=(0, (3.5, 2.5)) if dashed else "solid",
                                 connectionstyle=f"arc3,rad={rad}", shrinkA=0, shrinkB=0))
    if label:
        ax.text((x1 + x2) / 2 + lx, (y1 + y2) / 2 + ly, label, ha=ha, va="center", fontsize=AS, color=INK2,
                bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none"))


def legend(ax, x, y, H, kinds=True, arrows=True, dy=0.045, col_w=0.25):
    items = []
    if kinds is True:
        items += [("llm", "model (LLM) stage"), ("code", "deterministic code"), ("data", "data store"),
                  ("plain", "app, back end or external service")]
    elif kinds:
        items += kinds
    xx, yy = x, y
    for k, lab in items:
        ax.add_patch(FancyBboxPatch((xx, yy - 0.012), 0.022, 0.024, boxstyle="round,pad=0.003",
                                    fc=TINT[k], ec=EDGE[k], lw=LW))
        ax.text(xx + 0.03, yy, lab, va="center", fontsize=AS, color=INK2)
        xx += col_w if k != "data" else col_w - 0.08
    if arrows:
        yy -= dy
        xx = x
        for lab, both, dashed in (("request or data flow", False, False), ("read and write", True, False),
                                  ("push notification to a device", False, True)):
            arrow(ax, xx, yy, xx + 0.05, yy, both=both, dashed=dashed)
            ax.text(xx + 0.06, yy, lab, va="center", fontsize=AS, color=INK2)
            xx += 0.25 if not dashed else 0


# ------------------------------------------------------------ Figure 1: platform
def fig_architecture():
    H = 5.0
    fig, ax = canvas(H)
    # mobile app
    box(ax, H, 0.008, 0.17, 0.235, 0.81, "", kind="plain")
    ax.text(0.1255, 0.955, "Mobile app (Flutter)", ha="center", va="top", fontsize=TS, fontweight="bold", color=INK)
    roles = [("Older adult", ["medication reminders", "SOS button and call", "AI chat, health reports",
                              "records, care services"], 0.66, 0.235),
             ("Caregiver", ["linked older adults", "dose status, charts", "SOS and report alerts"], 0.43, 0.195),
             ("Service provider", ["service listings"], 0.28, 0.11)]
    for t, l, y, h in roles:
        box(ax, H, 0.02, y, 0.21, h, t, l)
    # business back end
    box(ax, H, 0.31, 0.80, 0.33, 0.175, "Business back end (FastAPI)",
        ["Google OAuth 2.0 and JWT", "profiles, medicine schedules, doses"])
    # AI service container with typed sub-boxes
    box(ax, H, 0.31, 0.17, 0.33, 0.585, "", kind="none")
    ax.text(0.475, 0.742, "AI service (FastAPI, Google ADK)", ha="center", va="top", fontsize=TS,
            fontweight="bold", color=INK)
    box(ax, H, 0.322, 0.535, 0.306, 0.165, "Deterministic code",
        ["ID-token check, keyword screen,", "routing, fixed replies,", "output checks"], kind="code")
    box(ax, H, 0.322, 0.375, 0.306, 0.145, "Model stages",
        ["Orchestrator, Feature, Formatter;", "report agent"], kind="llm")
    box(ax, H, 0.322, 0.185, 0.306, 0.175, "Profile, memory, tools",
        ["profile and remembered facts", "in every prompt; 11 tools", "over small seed tables"], kind="data")
    # right column
    rx, rw = 0.715, 0.277
    box(ax, H, rx, 0.86, rw, 0.115, "MongoDB", ["application data"], kind="data")
    box(ax, H, rx, 0.60, rw, 0.13, "PostgreSQL (Neon)", ["sessions, profile, memory"], kind="data")
    box(ax, H, rx, 0.39, rw, 0.17, "Model server (Ollama)", ["gemma4:e4b, 16k context", "one T4 GPU in evaluation"],
        kind="llm")
    box(ax, H, rx, 0.25, rw, 0.11, "Web search (Tavily)", ["cached during evaluation"])
    box(ax, H, rx, 0.125, rw, 0.105, "Firebase Cloud Messaging", ["caregiver push alerts"])
    # arrows
    arrow(ax, 0.23, 0.855, 0.31, 0.855, "REST", both=True, ly=0.028)
    arrow(ax, 0.23, 0.70, 0.322, 0.60, "chat", both=True, lx=0.0, ly=0.035)
    arrow(ax, 0.475, 0.80, 0.475, 0.755, None)
    ax.text(0.485, 0.778, "profile sync", ha="left", va="center", fontsize=AS, color=INK2)
    arrow(ax, 0.64, 0.90, rx, 0.90, None, both=True)
    arrow(ax, 0.64, 0.665, rx, 0.665, None, both=True)
    arrow(ax, 0.628, 0.45, rx, 0.45, "LiteLLM", ly=0.028)
    arrow(ax, 0.628, 0.30, rx, 0.30, None)
    arrow(ax, 0.64, 0.18, rx, 0.18, None)
    arrow(ax, rx + 0.03, 0.125, 0.13, 0.17, None, dashed=True, color=MUTED, rad=-0.12)
    ax.text(0.47, 0.098, "alert requested (not exercised in evaluation)", ha="center", va="center", fontsize=AS,
            color=INK2, bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none"))
    legend(ax, 0.02, 0.05, H, dy=0.04, col_w=0.215)
    save(fig, "fig1_architecture")


# ------------------------------------------------------------ Figure 3: one chat turn
def fig_pipeline():
    H = 6.3
    fig, ax = canvas(H)
    x, w = 0.075, 0.355
    cx = x + w / 2
    stages = [
        (0.925, 0.05, "User message (text, optional photo)", [], "plain"),
        (0.81, 0.085, "Profile block (code)", ["profile, medicines, allergies,", "remembered facts"], "code"),
        (0.685, 0.095, "Keyword screen (code)", ["Arabic and English emergency and", "self-harm phrases; no numbers"], "code"),
        (0.585, 0.07, "1  Orchestrator (LLM)", ["safety label, intent, plan"], "llm"),
        (0.455, 0.09, "Routing (code)", ["either signal escalates;", "an image intent needs a photo"], "code"),
        (0.33, 0.085, "2  Feature agent (LLM)", ["11 tools: meals, drug-food,", "exercise, search, memory"], "llm"),
        (0.225, 0.07, "3  Formatter (LLM)", ["Egyptian-Arabic reply"], "llm"),
    ]
    for y, h, title, lines, kind in stages:
        box(ax, H, x, y, w, h, title, lines, kind=kind)
    links = [(0.925, 0.895, None), (0.81, 0.78, None), (0.685, 0.655, "no match"), (0.585, 0.545, None),
             (0.455, 0.415, "ALLOWED"), (0.33, 0.295, None), (0.225, 0.155, None)]
    for y1, y2, lab in links:
        arrow(ax, cx, y1, cx, y2)
        if lab:
            ax.text(cx + 0.012, (y1 + y2) / 2, lab, ha="left", va="center", fontsize=AS, color=INK2)
    # BLOCKED: tools skipped, the Formatter (a model) writes the refusal
    arrow(ax, x, 0.49, x, 0.26, None, rad=0.45)
    ax.text(0.022, 0.375, "BLOCKED: tools skipped", ha="center", va="center", fontsize=AS, color=INK2,
            rotation=90, bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none"))
    box(ax, H, 0.02, 0.07, 0.96, 0.085, "Output checks (code), applied to every reply",
        ["remove emergency numbers that do not work in Egypt (911, 112, 999, 997, 998);",
         "flag any medicine that is in neither the profile nor a tool result"], kind="code")
    box(ax, H, 0.50, 0.60, 0.235, 0.215, "Emergency reply (code)",
        ["123 on the first line;", "first-aid steps*: by screen", "category, else generic;",
         "self-harm: 16328 and 123"], kind="code")
    box(ax, H, 0.76, 0.60, 0.22, 0.215, "Caregiver alert (code)",
        ["background task:", "report agent writes", "a summary; push to", "linked caregivers"], kind="code")
    box(ax, H, 0.50, 0.385, 0.20, 0.135, "Missing photo (code)",
        ["fixed request", "to resend the photo"], kind="code")
    arrow(ax, x + w, 0.73, 0.50, 0.73, "match", ly=0.02)
    arrow(ax, x + w, 0.53, 0.50, 0.63, None)
    ax.text(0.468, 0.585, "EMERGENCY", ha="center", va="center", fontsize=AS, color=INK2, rotation=0,
            bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none"))
    arrow(ax, x + w, 0.45, 0.50, 0.45, None)
    ax.text(0.465, 0.458, "no" + chr(10) + "photo", ha="center", va="bottom", fontsize=AS, color=INK2, linespacing=1.1)
    arrow(ax, 0.735, 0.71, 0.76, 0.71, None)
    arrow(ax, 0.715, 0.60, 0.715, 0.155, None)
    arrow(ax, 0.60, 0.385, 0.60, 0.155, None)
    ax.text(0.02, 0.035, "* Prototype first-aid text written by the authors; not reviewed by a clinician.",
            ha="left", va="center", fontsize=AS, color=INK2, style="italic")
    legend(ax, 0.50, 0.955, H, kinds=[("llm", "model (LLM) stage"), ("code", "deterministic code")],
           arrows=False, col_w=0.245)
    save(fig, "fig3_pipeline")


# ------------------------------------------------------------ Figure 4: earlier configurations
def fig_accuracy():
    from scipy.stats import beta

    def ci(k, n):
        lo = 0.0 if k == 0 else beta.ppf(0.025, k, n - k + 1)
        hi = 1.0 if k == n else beta.ppf(0.975, k + 1, n - k)
        return lo * 100, hi * 100

    P = S1["proportions"]
    runs = [("A", "A: original code, 4k context", BLUE), ("A'", "A′: original code, 16k context", ORANGE),
            ("C", "C: routing in code, 16k context", AQUA)]
    groups = [("intent_ok", "Routing intent\ncorrect"), ("safety_ok", "Safety label\ncorrect"),
              ("turn_pass", "All automatic\nchecks pass")]
    fig, ax = plt.subplots(figsize=(W, 2.9))
    width = 0.26
    for j, (rk, lab, col) in enumerate(runs):
        for i, (mk, _) in enumerate(groups):
            d = P[f"{rk}:{mk}"]
            k, n = d["k"], d["n"]
            p = k / n * 100
            lo, hi = ci(k, n)
            xx = i + (j - 1) * (width + 0.03)
            ax.bar(xx, p, width, color=col, label=lab if i == 0 else None, zorder=2)
            ax.errorbar(xx, p, yerr=[[p - lo], [hi - p]], fmt="none", ecolor=INK2, elinewidth=0.8, capsize=2.5, zorder=3)
            ax.text(xx, hi + 2, f"{k}/{n}", ha="center", va="bottom", fontsize=AS, color=INK)
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels([g[1] for g in groups], fontsize=7.6)
    ax.set_ylim(0, 122)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_yticklabels([f"{v}%" for v in [0, 25, 50, 75, 100]], fontsize=7.4)
    ax.yaxis.grid(True, color=GRID, linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_ylabel("Turns passing (n/N);\nbars: exact 95% CI", fontsize=7.6)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.17), frameon=False, fontsize=7.4, ncol=3,
              handlelength=1.2, columnspacing=1.2)
    fig.tight_layout()
    save(fig, "fig4_earlier_configurations")


# ------------------------------------------------------------ Figure 5: ablations
def _bars(ax, groups, runs, title, pair):
    from scipy.stats import beta
    width = 0.36
    P = S["paired"][pair]
    for j, (rk, lab, col) in enumerate(runs):
        for i, (mk, _) in enumerate(groups):
            d = P[mk]
            n = d["pairs"]
            k = d["D1_k"] if j == 0 else d["ablation_k"]
            p = k / n * 100
            lo = 0.0 if k == 0 else beta.ppf(0.025, k, n - k + 1) * 100
            hi = 100.0 if k == n else beta.ppf(0.975, k + 1, n - k) * 100
            xx = i + (j - 0.5) * (width + 0.03)
            ax.bar(xx, p, width, color=col, label=lab if i == 0 else None, zorder=2)
            ax.errorbar(xx, p, yerr=[[p - lo], [hi - p]], fmt="none", ecolor=INK2, elinewidth=0.8, capsize=2.2, zorder=3)
            ax.text(xx, hi + 2, f"{k}/{n}", ha="center", va="bottom", fontsize=7.0, color=INK)
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels([g[1] for g in groups], fontsize=7.2)
    ax.set_ylim(0, 125)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_yticklabels([f"{v}%" for v in [0, 25, 50, 75, 100]], fontsize=7.2)
    ax.yaxis.grid(True, color=GRID, linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_title(title, fontsize=8.0, loc="left", color=INK, pad=16)
    ax.legend(loc="lower left", frameon=False, fontsize=7.2, handlelength=1.1, ncol=2,
              bbox_to_anchor=(0.0, 0.99), borderaxespad=0)


def fig_ablation():
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(W, 5.6))
    _bars(a1, [("uses_name", "Uses the\npatient's name"), ("meal_safe_for_profile", "Meal rule-\nconsistent"),
               ("condition_aware", "Mentions the\ncondition"), ("memory_recall", "Recalls a fact\nnext session"),
               ("turn_all_checks_pass", "All checks\npass")],
          [("D1", "D1: full system", BLUE), ("F", "F: profile removed from prompts", ORANGE)],
          "(a) Profile in the prompt: D1 vs F on the same 54 turns (n/N per bar)", "D1_vs_F")
    _bars(a2, [("number_123_first", "123 on the\nfirst line"), ("crisis_line_16328", "Support line\n16328 given"),
               ("no_foreign_number", "No foreign\nnumber"), ("safety_correct", "Safety label\ncorrect"),
               ("turn_all_checks_pass", "All checks\npass")],
          [("D1", "D1: full system", BLUE), ("E", "E: bundled deterministic layer removed", ORANGE)],
          "(b) Bundled deterministic layer: D1 vs E on the same 46 turns (n/N per bar)", "D1_vs_E")
    for a in (a1, a2):
        a.set_ylabel("Turns passing;\nbars: exact 95% CI", fontsize=7.4)
    fig.tight_layout(h_pad=2.2)
    save(fig, "fig5_ablations")


# ------------------------------------------------------------ Figure 6: repeats
def fig_repeats():
    rows = [("safety_correct", "Safety label correct (90)"), ("routing_correct", "Routing intent correct (55)"),
            ("number_123_first", "123 on first line (10)"), ("crisis_line_16328", "Support line 16328 (5)"),
            ("no_foreign_number", "No foreign number (60)"), ("no_unlisted_medication", "No unlisted medicine (49)"),
            ("meal_safe_for_profile", "Meal rule-consistent (33)"), ("condition_aware", "Mentions condition (40)"),
            ("memory_saved", "Memory fact saved (5)"), ("memory_recall", "Memory fact used (5)"),
            ("uses_name", "Uses patient's name (44)"), ("turn_all_checks_pass", "All checks pass (93)")]
    fig, ax = plt.subplots(figsize=(W, 3.9))
    cols = {"D1": BLUE, "D2": ORANGE, "D3": AQUA}
    marks = {"D1": "o", "D2": "s", "D3": "D"}
    for i, (m, lab) in enumerate(rows):
        r = S["repeats"][m]
        vals = [r["rate_per_run"][k] * 100 for k in ("D1", "D2", "D3")]
        ax.plot([min(vals), max(vals)], [i, i], color=GRID, linewidth=3.5, solid_capstyle="round", zorder=1)
        for k, v, dy in zip(("D1", "D2", "D3"), vals, (-0.22, 0.0, 0.22)):
            ax.plot(v, i + dy, marks[k], color=cols[k], markersize=6, markeredgecolor="white", markeredgewidth=1.0,
                    zorder=3, label=f"{k}" if i == 0 else None)
        ax.text(103, i, f"{r['flipped']} of {r['turns']}", va="center", fontsize=7.2,
                color=INK if r["flipped"] else MUTED)
    ax.text(103, -1.05, "Turns that\nchanged", va="bottom", fontsize=7.2, color=INK, fontweight="bold")
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[1] for r in rows], fontsize=7.4)
    ax.set_ylim(len(rows) - 0.5, -1.2)
    ax.set_xlim(40, 120)
    ax.set_xticks([40, 60, 80, 100])
    ax.set_xticklabels(["40%", "60%", "80%", "100%"], fontsize=7.4)
    ax.xaxis.grid(True, color=GRID, linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_xlabel("Share of turns passing in each run (number of turns in brackets)", fontsize=7.6)
    ax.legend(loc="lower left", bbox_to_anchor=(-0.3, 1.0), frameon=False, fontsize=7.2, ncol=4,
              handletextpad=0.3, title=None, borderaxespad=0.2)
    ax.text(-0.3, 1.075, "Full-system runs:", transform=ax.transAxes, fontsize=7.2, color=INK, va="bottom")
    fig.tight_layout()
    save(fig, "fig6_repeats")


if __name__ == "__main__":
    fig_architecture()
    fig_pipeline()
    fig_accuracy()
    fig_ablation()
    fig_repeats()
    print("ok")
