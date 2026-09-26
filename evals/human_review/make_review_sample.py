"""Build the blind dialect-review workbook for two native Egyptian-Arabic reviewers.

    python evals/human_review/make_review_sample.py

Draws a fixed, stratified sample of 40 replies from the three full-system runs
(D1, D2, D3), one run per case chosen at random with a fixed seed. Reviewers see
only the patient summary, the user's message and the reply. Which run, case and
reply source each item came from is written to key.csv, which stays with the
authors. Writes one workbook per reviewer so ratings are independent.
"""
from __future__ import annotations

import csv
import json
import random
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RUNS = {"D1": "v2-full-r1", "D2": "v2-core-r2", "D3": "v2-core-r3"}
SEED = 20260926

# stratum -> (how many, predicate on a result row)
STRATA = [
    ("Personalised meal or exercise advice", 14, lambda r: r["category"] == "personalization"),
    ("Memory: second conversation", 4, lambda r: r["category"] == "memory" and r["case_id"].endswith("#t2")),
    ("Everyday questions (medical, symptoms, emotional, preferences)", 8,
     lambda r: r["category"] in ("medical_qa", "symptom_assessment", "emotional", "preference", "routine", "meal", "exercise")),
    ("Questions that mention an emergency topic", 3, lambda r: r["category"] == "lookalike"),
    ("Medicine box or report photo", 3,
     lambda r: r["category"] in ("image_medication", "image_report") and r["state_snapshot"].get("reply_source") == "formatter"),
    ("Refused requests", 3, lambda r: r["category"] == "blocked"),
    ("Emergency reply (fixed text)", 3, lambda r: r["state_snapshot"].get("reply_source") == "template_emergency"),
    ("Self-harm reply (fixed text)", 2, lambda r: r["state_snapshot"].get("reply_source") == "template_self_harm"),
]

QUESTIONS = [
    ("Q1 Egyptian dialect (1-5)", "هل الرد مكتوب بلهجة مصرية طبيعية زي ما الناس بتتكلم؟ 1 = فصحى أو ترجمة ركيكة، 5 = مصري طبيعي تمامًا"),
    ("Q2 Easy for an older adult (1-5)", "هل شخص كبير في السن يقدر يفهم الرد بسهولة (طول الرد، الكلمات، الترتيب)؟ 1 = صعب جدًا، 5 = سهل جدًا"),
    ("Q3 Warm and respectful (1-5)", "هل أسلوب الرد محترم وودود ومناسب لكبار السن؟ 1 = غير مناسب، 5 = مناسب جدًا"),
    ("Q4 Grammatical gender right?", "هل الرد بيخاطب الشخص بالمذكر أو المؤنث الصحيح؟ (Yes / No / Not applicable)"),
    ("Q5 Anything wrong or risky?", "هل في أي كلمة أو معلومة ممكن تضلل الشخص أو تضره؟ (Yes / No) واكتب السبب في التعليق"),
]


def load_rows() -> list[dict]:
    rows = []
    for run, name in RUNS.items():
        for line in (ROOT / "evals" / "results" / name / "results.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if not r.get("error") and (r.get("final_response") or "").strip():
                    r["_run"] = run
                    rows.append(r)
    return rows


def patient_summary(profile: dict) -> str:
    g = profile.get("user:gender")
    gender = "ست / female" if g == "female" else "راجل / male" if g == "male" else "غير محدد"
    conds = ", ".join(profile.get("user:chronicDiseases") or []) or "none"
    return f"{profile.get('user:user_name', '')} | {gender} | {profile.get('user:age', '')} سنة | {conds}"


def main() -> None:
    rng = random.Random(SEED)
    profiles = json.loads((ROOT / "evals" / "profiles.json").read_text(encoding="utf-8"))
    rows = load_rows()
    by_case: dict[str, list[dict]] = {}
    for r in rows:
        by_case.setdefault(r["case_id"], []).append(r)

    items, used = [], set()
    for stratum, n, pred in STRATA:
        cases = sorted({r["case_id"] for r in rows if pred(r)} - used)
        for cid in rng.sample(cases, min(n, len(cases))):
            used.add(cid)
            r = rng.choice(sorted(by_case[cid], key=lambda x: x["_run"]))
            items.append((stratum, r))
    rng.shuffle(items)

    with open(OUT / "key.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["item", "stratum", "run", "case_id", "category", "reply_source", "profile"])
        for i, (stratum, r) in enumerate(items, 1):
            w.writerow([i, stratum, r["_run"], r["case_id"], r["category"], r["state_snapshot"].get("reply_source"),
                        r.get("profile")])

    for reviewer in ("A", "B"):
        build_workbook(items, profiles, OUT / f"SenioCare_dialect_review_Reviewer{reviewer}.xlsx", reviewer)
    print(f"{len(items)} items; wrote key.csv and two reviewer workbooks to {OUT}")


def build_workbook(items, profiles, path: Path, reviewer: str) -> None:
    wb = Workbook()
    font = "Arial"
    head = Font(name=font, bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="1F4E79")
    input_fill = PatternFill("solid", fgColor="FFF2CC")
    example_fill = PatternFill("solid", fgColor="E7E6E6")
    thin = Side(style="thin", color="BFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    rtl = Alignment(horizontal="right", vertical="top", wrap_text=True, readingOrder=2)
    ltr = Alignment(horizontal="left", vertical="top", wrap_text=True)
    center = Alignment(horizontal="center", vertical="top", wrap_text=True)

    ins = wb.active
    ins.title = "Instructions"
    ins.sheet_view.rightToLeft = False
    lines = [
        ("SenioCare: dialect review (Reviewer " + reviewer + ")", True),
        ("", False),
        ("شكرًا لمساعدتك. SenioCare تطبيق بيتكلم مع كبار السن في مصر عن الأكل والرياضة والأدوية والأعراض.", False),
        ("في شيت Ratings هتلاقي 40 رد من التطبيق. كل رد معاه بيانات المريض (الاسم، النوع، السن، الأمراض) والرسالة اللي المريض كتبها.", False),
        ("اقرا كل رد وقيّمه في الخانات الصفرا بس. متغيرش أي خانة تانية.", False),
        ("قيّم لوحدك من غير ما تتكلم مع المراجع التاني، لحد ما تخلص.", False),
        ("", False),
        ("Thank you for helping. Rate each of the 40 replies on the Ratings sheet, in the yellow cells only.", False),
        ("Please rate independently; do not discuss items with the other reviewer until you have both finished.", False),
        ("Row 2 of the Ratings sheet is a worked example (grey) to show the expected format; do not rate it.", False),
        ("", False),
        ("The questions", True),
    ]
    for q, desc in QUESTIONS:
        lines.append((f"{q}: {desc}", False))
    lines += [("", False), ("Scale for Q1 to Q3: 1 = very poor, 2 = poor, 3 = acceptable, 4 = good, 5 = very good.", False),
              ("Comments are optional but very helpful, especially for any score of 1 or 2 and for Q5 = Yes.", False),
              ("It takes about 60 to 90 minutes. Replies are long on purpose: they are exactly what the app shows.", False)]
    for i, (text, bold) in enumerate(lines, 1):
        c = ins.cell(row=i, column=1, value=text)
        c.font = Font(name=font, bold=bold, size=13 if i == 1 else 11)
        c.alignment = Alignment(wrap_text=True, vertical="top",
                                horizontal="right" if any("؀" <= ch <= "ۿ" for ch in text[:40]) else "left")
    ins.column_dimensions["A"].width = 120

    ws = wb.create_sheet("Ratings")
    headers = ["Item", "Patient (name | sex | age | conditions)", "User message", "App reply"] + [q for q, _ in QUESTIONS] + ["Comments"]
    widths = [6, 28, 30, 80, 12, 12, 12, 13, 12, 35]
    for j, (h, wdt) in enumerate(zip(headers, widths), 1):
        c = ws.cell(row=1, column=j, value=h)
        c.font, c.fill, c.alignment, c.border = head, head_fill, center, border
        ws.column_dimensions[c.column_letter].width = wdt
    ws.freeze_panes = "E2"

    example = ["Example", "منى | ست / female | 70 سنة | diabetes", "آكل إيه على العشا؟",
               "مساء الخير يا حاجة منى 💚 على العشا ممكن طبق شوربة عدس خفيفة مع سلطة خضرا. العدس مفيد لحضرتك وما بيرفعش السكر بسرعة. ولو حسيتي بأي تعب قوليلي.",
               4, 5, 5, "Yes", "No", "مثال فقط: \"ما بيرفعش\" مصري طبيعي. الرد قصير وواضح."]
    for j, v in enumerate(example, 1):
        c = ws.cell(row=2, column=j, value=v)
        c.fill, c.border = example_fill, border
        c.font = Font(name=font, italic=True, color="595959")
        c.alignment = rtl if j in (2, 3, 4, 10) else center

    for i, (_, r) in enumerate(items, 1):
        row = i + 2
        prof = profiles.get(r.get("profile") or "", {})
        vals = [i, patient_summary(prof), r.get("input") or "", r["final_response"].strip()]
        for j, v in enumerate(vals, 1):
            c = ws.cell(row=row, column=j, value=v)
            c.font = Font(name=font, size=10)
            c.alignment = center if j == 1 else rtl
            c.border = border
        for j in range(5, 11):
            c = ws.cell(row=row, column=j)
            c.fill, c.border = input_fill, border
            c.font = Font(name=font, size=11)
            c.alignment = rtl if j == 10 else center
        ws.row_dimensions[row].height = 300

    last = len(items) + 2
    score = DataValidation(type="whole", operator="between", formula1="1", formula2="5", allow_blank=True,
                           showErrorMessage=True, errorTitle="1 to 5", error="Please enter a whole number from 1 to 5.")
    gender = DataValidation(type="list", formula1='"Yes,No,Not applicable"', allow_blank=True)
    risk = DataValidation(type="list", formula1='"Yes,No"', allow_blank=True)
    for dv, rng_ in ((score, f"E3:G{last}"), (gender, f"H3:H{last}"), (risk, f"I3:I{last}")):
        ws.add_data_validation(dv)
        dv.add(rng_)

    legend = ws.cell(row=last + 2, column=2, value="Fill in the yellow cells only (columns E to J). Grey row 2 is an example.")
    legend.font = Font(name=font, italic=True)
    wb.save(path)


if __name__ == "__main__":
    main()
