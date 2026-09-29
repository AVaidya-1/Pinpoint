"""Generate a separate synthetic 20-question holdout with explicit chart axes.

Run once before quality tuning. Output stays under ignored out/evaluation-v3/.
The generator and manifest record exact construction geometry; questions and
reference regions must not be used as model prompts or repair hints.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from reportlab.lib.colors import Color
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "evaluation-v3"
PAGE_W, PAGE_H = 612, 792


def region(x0: float, y0: float, x1: float, y1: float) -> list[float]:
    """ReportLab bottom-left points to top-left normalized coordinates."""
    return [round(x0 / PAGE_W, 4), round(1 - y1 / PAGE_H, 4),
            round(x1 / PAGE_W, 4), round(1 - y0 / PAGE_H, 4)]


def signature(c: canvas.Canvas, rgb: tuple[int, int, int]) -> None:
    c.setFillColor(Color(*(v / 255 for v in rgb)))
    c.rect(0, 762, 30, 30, fill=1, stroke=0)
    c.rect(582, 0, 30, 30, fill=1, stroke=0)
    c.setFillColorRGB(0, 0, 0)


def question(qid: str, kind: str, prompt: str, sig: tuple[int, int, int],
             primary: list[float] | None = None,
             required: list[list[float]] | None = None) -> dict:
    item = {"id": qid, "type": kind, "question": prompt,
            "expected_page": list(sig) if kind != "absent" else None,
            "expected_region": primary}
    if required:
        item["expected_regions"] = required
    return item


def build() -> tuple[Path, Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    pdf_path = OUT / "fresh-holdout.pdf"
    suite_path = OUT / "suite.json"
    sig_table = (255, 100, 0)
    sig_chart = (60, 80, 220)
    sig_relay = (170, 30, 180)
    c = canvas.Canvas(str(pdf_path), pagesize=(PAGE_W, PAGE_H), pageCompression=1)
    suite: list[dict] = []

    # Page 1: four separate text lines and a 4-row table with a real Unit column.
    signature(c, sig_table)
    c.setFont("Helvetica-Bold", 17)
    c.drawString(72, 720, "Hydraulic actuator service sheet")
    c.setFont("Helvetica", 11)
    text_lines = [
        ("t01", "Where is the release code listed?", 680, "Release code: RDX-27"),
        ("t02", "Where is the operating mode stated?", 655, "Operating mode: continuous"),
        ("t03", "Where is the service interval specified?", 630, "Service interval: 9 months"),
        ("t04", "Where is the safety note?", 605, "Safety note: isolate pressure before service"),
    ]
    for qid, prompt, y, content in text_lines:
        c.drawString(72, y, content)
        suite.append(question(qid, "text", prompt, sig_table,
                              region(70, y - 3, 74 + stringWidth(content, "Helvetica", 11), y + 12)))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(84, 560, "Parameter")
    c.drawString(330, 560, "Value")
    c.drawString(448, 560, "Unit")
    c.setFont("Helvetica", 11)
    rows = [
        ("b01", "Where is the idle draw row?", 525, "Idle draw", "18", "mA"),
        ("b02", "Where is the seal span row?", 495, "Seal span", "53.4", "mm"),
        ("b03", "Where is the cutoff current row?", 465, "Cutoff current", "5.6", "A"),
        ("b04", "Where is the pressure rating row?", 435, "Pressure rating", "210", "kPa"),
    ]
    for qid, prompt, y, label, value, unit in rows:
        c.rect(72, y - 8, 480, 24, fill=0, stroke=1)
        c.drawString(84, y, label)
        c.drawString(330, y, value)
        c.drawString(448, y, unit)
        row = region(82, y - 3, 480, y + 11)
        unit_box = region(446, y - 3, 450 + stringWidth(unit, "Helvetica", 11), y + 11)
        suite.append(question(qid, "table", prompt, sig_table, row,
                              [row, unit_box]))
    c.showPage()

    # Page 2: axes explicitly define load direction and torque quantity.
    signature(c, sig_chart)
    c.setFont("Helvetica-Bold", 17)
    c.drawString(72, 720, "Motor torque profile")
    chart = region(90, 390, 510, 620)
    legend = region(520, 558, 595, 582)
    x_axis = region(268, 345, 345, 371)
    c.rect(90, 390, 420, 230, fill=0, stroke=1)
    c.setFont("Helvetica", 11)
    c.drawString(90, 637, "Torque (Nm)")
    c.drawString(280, 356, "Load (%)")
    c.drawString(90, 375, "0")
    c.drawString(488, 375, "100")
    c.drawString(525, 570, "nominal")
    c.setStrokeColorRGB(0.0, 0.35, 0.1)
    c.setLineWidth(3)
    path = c.beginPath()
    path.moveTo(110, 580)
    path.curveTo(235, 570, 355, 450, 485, 415)
    c.drawPath(path, fill=0, stroke=1)
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(1)
    suite.extend([
        question("v01", "visual", "Where does nominal torque decline at high load?", sig_chart,
                 region(90, 345, 595, 620), [chart, legend, x_axis]),
        question("v02", "visual", "Where does the nominal curve begin at low load?", sig_chart,
                 region(90, 345, 345, 620), [region(90, 390, 300, 620), x_axis]),
        question("v03", "visual", "Where is the nominal legend relative to the curve?", sig_chart,
                 region(90, 390, 595, 620), [chart, legend]),
    ])
    c.setFont("Helvetica", 11)
    c.drawString(120, 300, "Filter")
    c.rect(115, 165, 145, 120, fill=0, stroke=1)
    c.drawString(345, 300, "Motor")
    c.circle(395, 225, 65, fill=0, stroke=1)
    suite.append(question("v04", "visual", "Where is the motor relative to the filter?", sig_chart,
                          region(110, 160, 465, 315)))
    c.showPage()

    # Page 3: identical relay symbols require a bank heading for disambiguation.
    signature(c, sig_relay)
    c.setFont("Helvetica-Bold", 17)
    c.drawString(72, 720, "Dual relay mounting diagram")
    c.setFont("Helvetica", 12)
    c.drawString(72, 660, "Bank A")
    c.drawString(330, 660, "Bank B")
    c.rect(72, 455, 210, 170, fill=0, stroke=1)
    c.rect(330, 455, 210, 170, fill=0, stroke=1)
    for x in (72, 330):
        c.drawString(x + 34, 570, "Q5 relay")
        c.rect(x + 60, 515, 58, 32, fill=0, stroke=1)
        c.circle(x + 170, 500, 15, fill=0, stroke=1)
        c.drawString(x + 135, 470, "mount lug")
    bank_a = region(72, 455, 282, 625)
    bank_b = region(330, 455, 540, 625)
    heading_a = region(71, 657, 74 + stringWidth("Bank A", "Helvetica", 12), 671)
    heading_b = region(329, 657, 332 + stringWidth("Bank B", "Helvetica", 12), 671)
    suite.extend([
        question("v05", "visual", "Where is the Q5 relay in Bank A?", sig_relay,
                 region(72, 455, 282, 674), [heading_a, bank_a]),
        question("v06", "visual", "Where is the Q5 relay in Bank B?", sig_relay,
                 region(330, 455, 540, 674), [heading_b, bank_b]),
        question("v07", "visual", "Where is the mount lug relative to Q5 in Bank A?", sig_relay,
                 region(72, 455, 282, 674), [heading_a, bank_a]),
        question("v08", "visual", "Where is the Bank B boundary?", sig_relay,
                 region(330, 455, 540, 674), [heading_b, bank_b]),
    ])
    c.showPage()
    c.save()

    absent = [
        ("a01", "Where is the emergency stop lever?"),
        ("a02", "Where is the battery charge indicator?"),
        ("a03", "Where is the Q9 relay in Bank A?"),
        ("a04", "Where is the overload reset switch?"),
    ]
    suite.extend(question(qid, "absent", prompt, sig_table)
                 for qid, prompt in absent)
    assert len(suite) == 20
    assert [sum(item["type"] == kind for item in suite)
            for kind in ("text", "table", "visual", "absent")] == [4, 4, 8, 4]
    suite_path.write_text(json.dumps(suite, indent=2) + "\n", encoding="utf-8")
    manifest = {"pdf_sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
                "suite_sha256": hashlib.sha256(suite_path.read_bytes()).hexdigest(),
                "question_count": 20, "split": [4, 4, 8, 4],
                "purpose": "fresh synthetic quality holdout; freeze before task 09 repair"}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return pdf_path, suite_path


if __name__ == "__main__":
    print(*build(), sep="\n")
