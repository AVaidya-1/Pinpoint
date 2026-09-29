"""Generate the versioned holdout frozen before Task 10 quality repair."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from reportlab.lib.colors import Color
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "evaluation-v4"
W, H = 612, 792


def box(x0, y0, x1, y1):
    return [round(x0 / W, 4), round(1 - y1 / H, 4),
            round(x1 / W, 4), round(1 - y0 / H, 4)]


def sig(c, rgb):
    c.setFillColor(Color(*(v / 255 for v in rgb)))
    c.rect(0, 762, 30, 30, fill=1, stroke=0)
    c.rect(582, 0, 30, 30, fill=1, stroke=0)
    c.setFillColorRGB(0, 0, 0)


def item(qid, kind, prompt, signature, primary=None, required=None):
    out = {"id": qid, "type": kind, "question": prompt,
           "expected_page": list(signature) if kind != "absent" else None,
           "expected_region": primary}
    if required:
        out["expected_regions"] = required
    return out


def text_box(text, x, y, font="Helvetica", size=11):
    # Tight construction truth around visible glyphs, with two points allowance.
    return box(x - 2, y - 3, x + stringWidth(text, font, size) + 2, y + 10)


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    pdf_path = OUT / "holdout.pdf"
    suite_path = OUT / "suite.json"
    orange, blue, purple = (230, 120, 10), (25, 110, 200), (120, 40, 150)
    c = canvas.Canvas(str(pdf_path), pagesize=(W, H), pageCompression=1)
    suite = []

    sig(c, orange)
    c.setFont("Helvetica-Bold", 17)
    c.drawString(72, 720, "Compressor maintenance card")
    c.setFont("Helvetica", 11)
    lines = [
        ("t01", "Where is the firmware tag listed?", 680, "Firmware tag: FWC-82"),
        ("t02", "Where is the duty cycle stated?", 655, "Duty cycle: intermittent"),
        ("t03", "Where is the maintenance period specified?", 630, "Maintenance period: 12 months"),
        ("t04", "Where is the warning statement?", 605, "Warning: vent pressure before inspection"),
    ]
    for qid, prompt, y, text in lines:
        c.drawString(72, y, text)
        suite.append(item(qid, "text", prompt, orange, text_box(text, 72, y)))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(84, 560, "Parameter")
    c.drawString(330, 560, "Value")
    c.drawString(448, 560, "Unit")
    c.setFont("Helvetica", 11)
    rows = [
        ("b01", "Where is the standby voltage row?", 525, "Standby voltage", "24", "V"),
        ("b02", "Where is the hose length row?", 495, "Hose length", "3.2", "m"),
        ("b03", "Where is the fuse current row?", 465, "Fuse current", "8", "A"),
        ("b04", "Where is the maximum flow row?", 435, "Maximum flow", "125", "L/min"),
    ]
    for qid, prompt, y, label, value, unit in rows:
        c.rect(72, y - 8, 480, 24, fill=0, stroke=1)
        c.drawString(84, y, label)
        c.drawString(330, y, value)
        c.drawString(448, y, unit)
        row = box(80, y - 5, 480, y + 12)
        unit_region = text_box(unit, 448, y)
        suite.append(item(qid, "table", prompt, orange, row, [row, unit_region]))
    c.showPage()

    sig(c, blue)
    c.setFont("Helvetica-Bold", 17)
    c.drawString(72, 720, "Pump efficiency profile")
    c.rect(90, 390, 420, 230, fill=0, stroke=1)
    c.setFont("Helvetica", 11)
    c.drawString(90, 637, "Efficiency (%)")
    c.drawString(277, 356, "Pressure (%)")
    c.drawString(90, 375, "0")
    c.drawString(488, 375, "100")
    c.drawString(525, 570, "baseline")
    c.setStrokeColorRGB(0.1, 0.3, 0.7)
    c.setLineWidth(3)
    path = c.beginPath()
    path.moveTo(110, 560)
    path.curveTo(235, 575, 365, 505, 485, 420)
    c.drawPath(path, fill=0, stroke=1)
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(1)
    chart = box(90, 390, 510, 620)
    legend = text_box("baseline", 525, 570)
    x_axis = text_box("Pressure (%)", 277, 356)
    suite.extend([
        item("v01", "visual", "Where does baseline efficiency fall at high pressure?", blue,
             box(90, 345, 595, 620), [chart, legend, x_axis]),
        item("v02", "visual", "Where does the baseline curve begin at low pressure?", blue,
             box(90, 345, 345, 620), [box(90, 390, 300, 620), x_axis]),
        item("v03", "visual", "Where is the baseline legend relative to the curve?", blue,
             box(90, 390, 595, 620), [chart, legend]),
    ])
    c.setFont("Helvetica", 11)
    c.drawString(120, 300, "Reservoir")
    c.rect(115, 165, 145, 120, fill=0, stroke=1)
    c.drawString(350, 300, "Pump")
    c.circle(395, 225, 65, fill=0, stroke=1)
    suite.append(item("v04", "visual", "Where is the pump relative to the reservoir?", blue,
                      box(110, 160, 465, 315)))
    c.showPage()

    sig(c, purple)
    c.setFont("Helvetica-Bold", 17)
    c.drawString(72, 720, "Twin controller mounting diagram")
    c.setFont("Helvetica", 12)
    c.drawString(72, 660, "Zone North")
    c.drawString(330, 660, "Zone South")
    c.rect(72, 455, 210, 170, fill=0, stroke=1)
    c.rect(330, 455, 210, 170, fill=0, stroke=1)
    for x in (72, 330):
        c.drawString(x + 34, 570, "R7 relay")
        c.rect(x + 60, 515, 58, 32, fill=0, stroke=1)
        c.circle(x + 170, 500, 15, fill=0, stroke=1)
        c.drawString(x + 130, 470, "mount bracket")
    north = box(72, 455, 282, 625)
    south = box(330, 455, 540, 625)
    north_heading = text_box("Zone North", 72, 660, size=12)
    south_heading = text_box("Zone South", 330, 660, size=12)
    suite.extend([
        item("v05", "visual", "Where is the R7 relay in Zone North?", purple,
             box(72, 455, 282, 674), [north_heading, north]),
        item("v06", "visual", "Where is the R7 relay in Zone South?", purple,
             box(330, 455, 540, 674), [south_heading, south]),
        item("v07", "visual", "Where is the mount bracket relative to R7 in Zone North?", purple,
             box(72, 455, 282, 674), [north_heading, north]),
        item("v08", "visual", "Where is the Zone South boundary?", purple,
             box(330, 455, 540, 674), [south_heading, south]),
    ])
    c.showPage()
    c.save()

    for qid, prompt in [
        ("a01", "Where is the emergency drain handle?"),
        ("a02", "Where is the battery temperature display?"),
        ("a03", "Where is the R9 relay in Zone North?"),
        ("a04", "Where is the automatic bypass switch?"),
    ]:
        suite.append(item(qid, "absent", prompt, orange))
    assert len(suite) == 20
    assert [sum(q["type"] == kind for q in suite)
            for kind in ("text", "table", "visual", "absent")] == [4, 4, 8, 4]
    suite_path.write_text(json.dumps(suite, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "pdf_sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
        "suite_sha256": hashlib.sha256(suite_path.read_bytes()).hexdigest(),
        "question_count": 20,
        "split": [4, 4, 8, 4],
        "purpose": "fresh synthetic quality holdout; frozen before Task 10 repair",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return pdf_path, suite_path


if __name__ == "__main__":
    print(*build(), sep="\n")
