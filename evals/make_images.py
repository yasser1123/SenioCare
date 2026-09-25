"""Render the synthetic test images in evals/images/ (medicine boxes and lab reports).

Synthetic on purpose: the ground truth is known exactly, and no real patient
data or photo is involved. Run once: python evals/make_images.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent / "images"


def _font(size: int, bold: bool = False):
    for name in (("arialbd.ttf" if bold else "arial.ttf"), ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def medicine_box(fname: str, brand: str, strength: str, ingredient: str, count: str, maker: str, color: str):
    img = Image.new("RGB", (900, 560), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 900, 110], fill=color)
    d.text((40, 25), brand, font=_font(64, True), fill="white")
    d.text((40, 150), strength, font=_font(54, True), fill="black")
    d.text((40, 235), ingredient, font=_font(36), fill="black")
    d.text((40, 300), count, font=_font(32), fill="#333333")
    d.text((40, 360), "For oral use. Read the leaflet before use.", font=_font(26), fill="#333333")
    d.text((40, 480), maker, font=_font(28, True), fill=color)
    d.rectangle([640, 300, 860, 520], outline=color, width=6)
    img.save(OUT / fname)


def lab_report(fname: str, title: str, rows: list[tuple[str, str, str, str]]):
    img = Image.new("RGB", (1000, 140 + 60 * len(rows) + 120), "white")
    d = ImageDraw.Draw(img)
    d.text((40, 30), "SYNTHETIC LAB  -  TEST REPORT (not a real patient)", font=_font(26, True), fill="#1f4e79")
    d.text((40, 75), f"Patient: Test Patient   Age: 72   Date: 2026-09-20   Test: {title}", font=_font(22), fill="black")
    y = 130
    for i, head in enumerate(("Test", "Result", "Unit", "Reference range")):
        d.text((40 + i * 240, y), head, font=_font(24, True), fill="black")
    d.line([40, y + 36, 960, y + 36], fill="black", width=2)
    y += 50
    for row in rows:
        for i, cell in enumerate(row):
            d.text((40 + i * 240, y), cell, font=_font(24), fill="black")
        y += 60
    d.text((40, y + 20), "H = high, L = low. Interpret with your doctor.", font=_font(20), fill="#555555")
    img.save(OUT / fname)


def main():
    OUT.mkdir(exist_ok=True)
    medicine_box("med_glucophage_500.png", "Glucophage", "500 mg", "Metformin hydrochloride",
                 "50 film-coated tablets", "Synthetic Pharma Co.", "#1b6fb3")
    medicine_box("med_concor_5.png", "Concor", "5 mg", "Bisoprolol fumarate",
                 "30 film-coated tablets", "Synthetic Pharma Co.", "#b31b3b")
    medicine_box("med_marevan_5.png", "Marevan", "5 mg", "Warfarin sodium",
                 "100 tablets", "Synthetic Pharma Co.", "#6a3fb3")
    medicine_box("med_augmentin_1g.png", "Augmentin", "1 g", "Amoxicillin / Clavulanic acid",
                 "14 film-coated tablets", "Synthetic Pharma Co.", "#2e8b57")
    lab_report("report_cbc.png", "Complete blood count", [
        ("Hemoglobin", "11.2 L", "g/dL", "13.0 - 17.0"),
        ("WBC", "7.1", "x10^3/uL", "4.0 - 11.0"),
        ("Platelets", "210", "x10^3/uL", "150 - 400"),
    ])
    lab_report("report_glucose_lipids.png", "Glucose and lipids", [
        ("Fasting glucose", "142 H", "mg/dL", "70 - 100"),
        ("HbA1c", "7.4 H", "%", "4.0 - 5.6"),
        ("LDL cholesterol", "160 H", "mg/dL", "< 100"),
        ("HDL cholesterol", "45", "mg/dL", "> 40"),
    ])
    print("wrote", sorted(p.name for p in OUT.glob("*.png")))


if __name__ == "__main__":
    main()
