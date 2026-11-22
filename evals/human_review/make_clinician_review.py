"""Builds the clinician review sheet for SenioCare's fixed emergency and self-harm texts.

    python evals/human_review/make_clinician_review.py  -> SenioCare_clinician_review.xlsx

The texts are read from seniocare/safety.py (masculine forms; the feminine forms are
the same steps). English glosses are the authors' translations.
"""
from __future__ import annotations

import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from seniocare import safety  # noqa: E402  (run with the project's .venv)

CONTEXT = {
    "chest": "Chest pain / suspected heart attack",
    "breathing": "Severe shortness of breath",
    "stroke": "Suspected stroke (face, arm, speech)",
    "unconscious": "Someone unconscious / not responding",
    "bleeding": "Heavy bleeding",
    "fall_head": "Fall or head injury",
    "allergy": "Severe allergic reaction",
    "poisoning": "Poisoning or medicine overdose",
    "generic": "Emergency of unknown type (model-detected)",
}
GLOSS = {
    "chest": ["Sit and rest; do not exert yourself.", "Loosen any tight clothing.", "Do not drive yourself."],
    "breathing": ["Sit upright, leaning slightly forward.", "Open the window and loosen any tight clothing.",
                  "Try to breathe calmly and slowly."],
    "stroke": ["Remember the time the symptoms started and tell the ambulance.", "Do not eat or drink anything.",
               "Sit, or lie on your side, in a safe place."],
    "unconscious": ["If the person does not respond but is breathing, lay them on their side.",
                    "Do not give them food or drink.", "Stay with them until the ambulance arrives."],
    "bleeding": ["Press hard on the wound with a clean cloth and do not remove it.",
                 "If you can, raise the injured part."],
    "fall_head": ["Do not move if you have neck or back pain.", "Have someone stay with you; do not get up alone."],
    "allergy": ["If you have an allergy injection prescribed by your doctor, use it as instructed.",
                "Sit upright if breathing is hard."],
    "poisoning": ["Do not try to vomit unless a doctor says so.",
                  "Keep the medicine or substance package with you to show the ambulance."],
    "generic": ["Try to stay calm and avoid moving much.", "Have someone stay with you until the ambulance arrives."],
}
OPENING_AR = safety.build_emergency_reply("generic").split("\n\n")[0]
OPENING_EN = ("Call the ambulance now on 123. If speaking is hard, ask anyone near you to call 123. "
              "Until the ambulance arrives: [steps below]")
SELF_HARM_AR = safety.build_self_harm_reply()
SELF_HARM_EN = ("I hear you and I care about you, and what you are feeling matters. Call the psychological support line "
                "16328 (free, 24 hours, Ministry of Health). If you feel you might hurt yourself now, call the ambulance "
                "on 123 or go to the nearest emergency department. Have someone you trust sit with you now, and stay away "
                "from anything that could hurt you. I am here if you would like to talk.")

QUESTIONS = ["Q1 Medically appropriate as lay first aid? (Yes/Partly/No)",
             "Q2 Could any step cause harm? (Yes/No)",
             "Q3 Important step missing? (Yes/No)",
             "Comments / suggested wording"]
YELLOW = PatternFill("solid", fgColor="FFF2CC")


def main() -> None:
    wb = Workbook()
    ins = wb.active
    ins.title = "Instructions"
    for line in [
        "SenioCare: clinician review of fixed emergency texts",
        "SenioCare is a research prototype of an Arabic chat companion for older adults in Egypt. When it detects an "
        "emergency it does not let the AI write the reply; it shows one of the fixed texts below: the ambulance number "
        "first, then two or three lay first-aid steps for the detected type of emergency. Self-harm messages get a "
        "fixed supportive reply with the national psychological-support line 16328 and the ambulance number.",
        "Please judge each text as advice shown on a phone to an older adult (or someone with them) while waiting for "
        "an ambulance. Fill in the yellow cells only. About 20 to 30 minutes.",
        "Q1: Is it appropriate lay first aid for this situation? Q2: Could following any step harm the person? "
        "Q3: Is an important step missing? Please suggest wording in Comments for any No/Partly/Yes-harm answer.",
        "The texts are in Egyptian Arabic in the app; the English column is a translation. Female users see the same "
        "steps with feminine verb forms.",
        "Reviewer name, specialty and date (for the authors' records; not published without your consent):",
    ]:
        ins.append([line])
    ins.column_dimensions["A"].width = 120
    for row in ins.iter_rows():
        row[0].alignment = Alignment(wrap_text=True, vertical="top")
    ins["A1"].font = Font(bold=True, size=13)
    ins["A7"].fill = YELLOW

    ws = wb.create_sheet("Texts")
    ws.append(["Item", "Situation", "Arabic text (as shown)", "English translation", *QUESTIONS])
    rows = [("Opening (all emergencies)", OPENING_AR, OPENING_EN)]
    for k, steps in safety._FIRST_AID.items():
        rows.append((CONTEXT[k], "\n".join(f"• {s}" for s in steps), "\n".join(f"• {s}" for s in GLOSS[k])))
    rows.append(("Self-harm or suicidal message", SELF_HARM_AR, SELF_HARM_EN))
    for i, (ctx, ar, en) in enumerate(rows, 1):
        ws.append([i, ctx, ar, en, None, None, None, None])
    widths = [6, 28, 55, 55, 18, 16, 16, 45]
    for col, w in zip("ABCDEFGH", widths):
        ws.column_dimensions[col].width = w
    for c in ws[1]:
        c.font = Font(bold=True)
        c.alignment = Alignment(wrap_text=True, vertical="top")
    dv1 = DataValidation(type="list", formula1='"Yes,Partly,No"', allow_blank=True)
    dv2 = DataValidation(type="list", formula1='"Yes,No"', allow_blank=True)
    ws.add_data_validation(dv1)
    ws.add_data_validation(dv2)
    for r in range(2, ws.max_row + 1):
        for col in "ABCDEFGH":
            ws[f"{col}{r}"].alignment = Alignment(wrap_text=True, vertical="top",
                                                  horizontal="right" if col == "C" else "left")
        for col in "EFGH":
            ws[f"{col}{r}"].fill = YELLOW
        dv1.add(f"E{r}")
        dv2.add(f"F{r}")
        dv2.add(f"G{r}")
    out = HERE / "SenioCare_clinician_review.xlsx"
    wb.save(out)
    print("wrote", out, "rows", ws.max_row - 1)


if __name__ == "__main__":
    main()
