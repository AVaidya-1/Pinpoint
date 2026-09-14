"""Deterministic fixture generation for the P0 import/viewer slice.

Produces fixtures/generated/: 8-page test PDF, portrait/landscape/cropbox
PDFs, EXIF JPEG, standard PNG, and a SHA-256 manifest. Writes
fixtures/development.json (dev pages 1-5 + orientation ground truth) and
fixtures/holdout.json (20 frozen evaluation questions).

Every generated page embeds a unique 4x4 pixel signature at rendered (0,0).
The generator renders each PDF with the same pypdfium2 code path the backend
uses and self-verifies every signature before writing ground truth.
"""

import hashlib
import io
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.ingestion import (  # noqa: E402
    decode_image_canonical,
    pdf_canonical_size,
    render_pdf_canonical,
)

from PIL import Image, ImageDraw  # noqa: E402

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
except ImportError:  # pragma: no cover
    letter = None
    canvas = None

PAGE_W, PAGE_H = letter  # 612 x 792
GENERATED = PROJECT_ROOT / "fixtures" / "generated"

SIGNATURES = {
    "P1": (255, 0, 0),
    "P2": (0, 255, 0),
    "P3": (0, 0, 255),
    "P4": (255, 255, 0),
    "P5": (255, 0, 255),
    "P6": (0, 255, 255),
    "P7": (128, 0, 0),
    "P8": (0, 128, 0),
    "PORTRAIT": (128, 128, 0),
    "LANDSCAPE": (0, 128, 128),
    "CROPBOX": (128, 0, 128),
    "EXIF": (255, 128, 0),
    "STANDARD": (0, 0, 128),
}

CORNER_SQ = 26  # pt, kept clear of all content (content margin 48pt)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def signature_ok(img: Image.Image, rgb: tuple[int, int, int], tol: int = 10) -> bool:
    px = img.convert("RGB")
    for x in range(4):
        for y in range(4):
            r, g, b = px.getpixel((x, y))
            if abs(r - rgb[0]) > tol or abs(g - rgb[1]) > tol or abs(b - rgb[2]) > tol:
                return False
    return True


def draw_corners(c, rgb, page_w=PAGE_W, page_h=PAGE_H):
    c.setFillColorRGB(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
    c.rect(0, 0, CORNER_SQ, CORNER_SQ, fill=1, stroke=0)
    c.rect(page_w - CORNER_SQ, 0, CORNER_SQ, CORNER_SQ, fill=1, stroke=0)
    c.rect(0, page_h - CORNER_SQ, CORNER_SQ, CORNER_SQ, fill=1, stroke=0)
    c.rect(page_w - CORNER_SQ, page_h - CORNER_SQ, CORNER_SQ, CORNER_SQ, fill=1, stroke=0)


def white_page(c, page_w=PAGE_W, page_h=PAGE_H):
    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, page_w, page_h, fill=1, stroke=0)


def norm_box(x_pt, y_top_pt, w_pt, h_pt, page_w=PAGE_W, page_h=PAGE_H):
    """ReportLab coords (origin bottom-left) -> normalized (origin top-left)."""
    x0 = x_pt / page_w
    y0 = 1.0 - (y_top_pt) / page_h
    x1 = (x_pt + w_pt) / page_w
    y1 = 1.0 - (y_top_pt - h_pt) / page_h
    return [round(x0, 5), round(y0, 5), round(x1, 5), round(y1, 5)]


# ---------------------------------------------------------------- page bodies

def draw_spec_table(c, title, rows, target_row_idx, y_top):
    """rows: list of (label, value, unit). Returns target box."""
    x, w = 72, 468
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(x, y_top, title)
    y = y_top - 28
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y, "Parameter")
    c.drawString(x + 260, y, "Value")
    c.drawString(x + 360, y, "Unit")
    y -= 6
    c.line(x, y, x + w, y)
    y -= 16
    target = None
    for i, (label, value, unit) in enumerate(rows):
        c.setFont("Helvetica", 10)
        c.drawString(x, y, label)
        c.drawString(x + 260, y, value)
        c.drawString(x + 360, y, unit)
        if i == target_row_idx:
            target = norm_box(x - 4, y + 14, w + 8, 20)
            c.setStrokeColorRGB(0, 0, 0)
            c.rect(x - 4, y - 5, w + 8, 19, fill=0, stroke=1)
        y -= 20
    return target


def page_spec_table_p1(c):
    rows = [
        ("Operating temperature", "-20 ... +70", "degC"),
        ("Compact housing width", "42.5", "mm"),
        ("Compact housing depth", "38.0", "mm"),
        ("Supply voltage", "24", "V DC"),
        ("Pressure range", "0 ... 10", "bar"),
    ]
    return draw_spec_table(c, "Controller specification (development)", rows, 1, 700)


def page_chart_p2(c):
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, 700, "Efficiency at low load (development)")
    ox, oy, ow, oh = 90, 420, 420, 200
    c.setStrokeColorRGB(0, 0, 0)
    c.rect(ox, oy, ow, oh, fill=0, stroke=1)
    c.setFont("Helvetica", 9)
    c.drawString(ox - 30, oy + oh + 6, "Eff %")
    c.drawString(ox + ow - 10, oy - 16, "Load %")
    # target curve region (the low-load knee)
    c.setStrokeColorRGB(0.8, 0, 0)
    c.setLineWidth(2)
    p = c.beginPath()
    p.moveTo(ox + 20, oy + 30)
    p.curveTo(ox + 120, oy + 40, ox + 160, oy + 150, ox + 380, oy + 170)
    c.drawPath(p, fill=0, stroke=1)
    c.setLineWidth(1)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(ox + ow + 12, oy + 150, "==")
    c.drawString(ox + ow + 30, oy + 150, "unit A")
    c.setStrokeColorRGB(0, 0, 0.8)
    p2 = c.beginPath()
    p2.moveTo(ox + 20, oy + 20)
    p2.lineTo(ox + 380, oy + 90)
    c.drawPath(p2, fill=0, stroke=1)
    c.drawString(ox + ow + 12, oy + 60, "--")
    c.drawString(ox + ow + 30, oy + 60, "unit B")
    target = norm_box(ox + 100, oy + 200, 160, 140)
    return target


def raster_flowchart_image():
    img = Image.new("RGB", (1500, 1900), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([550, 60, 950, 200], outline="black", width=5)
    d.text((640, 115), "Pressure check", fill="black")
    d.polygon([(750, 320), (1050, 520), (750, 720), (450, 520)], outline="black", width=5)
    d.text((700, 505), "Pass?", fill="black")
    d.line([(750, 720), (750, 900)], fill="black", width=5)
    d.text((760, 790), "No", fill="black")
    d.rectangle([(550, 900), (950, 1040)], outline="black", width=5)
    d.text((620, 960), "Vent branch", fill="black")
    d.line([(1050, 520), (1250, 520)], fill="black", width=5)
    d.text((1130, 480), "Yes", fill="black")
    d.rectangle([(1250, 450), (1450, 590)], outline="black", width=5)
    d.text((1280, 510), "Run", fill="black")
    return img


def page_flowchart_p3(c):
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(72, 712, "Troubleshooting flowchart (raster-only)")
    img = raster_flowchart_image()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    from reportlab.lib.utils import ImageReader

    c.drawImage(ImageReader(buf), 106, 180, width=400, height=507,
                preserveAspectRatio=True, mask="auto")
    # target: the "No" branch + vent destination, in image-fraction coords
    # image placed at (106,180) size 400x507; branch region approx:
    fx0, fy0, fx1, fy1 = 540 / 1500, 700 / 1900, 960 / 1500, 1060 / 1900
    x_pt = 106 + fx0 * 400
    w_pt = (fx1 - fx0) * 400
    y_top_pt = 180 + 507 - fy0 * 507
    h_pt = (fy1 - fy0) * 507
    return norm_box(x_pt, y_top_pt, w_pt, h_pt)


def page_schematic_p4(c):
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, 700, "Connector diagram (development)")
    # sub-diagram A
    c.setFont("Helvetica", 10)
    c.drawString(72, 660, "Assembly A")
    c.rect(72, 480, 200, 150, fill=0, stroke=1)
    c.drawString(90, 590, "J1 connector")
    c.rect(110, 520, 40, 30, fill=0, stroke=1)
    c.drawString(90, 490, "mounting hole")
    c.circle(200, 500, 8, fill=0, stroke=1)
    # sub-diagram B (repeated labels)
    c.drawString(320, 660, "Assembly B")
    c.rect(320, 480, 200, 150, fill=0, stroke=1)
    c.drawString(338, 590, "J1 connector")
    c.rect(360, 520, 40, 30, fill=0, stroke=1)
    c.drawString(420, 490, "mounting hole")
    c.circle(450, 500, 8, fill=0, stroke=1)
    # target: J1 connector in assembly A
    return norm_box(106, 555, 48, 38)


def page_shapes_p5(c):
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, 700, "Geometry targets")
    # target shape at exact coordinates
    c.setStrokeColorRGB(0.7, 0, 0)
    c.setLineWidth(3)
    c.rect(150, 450, 180, 120, fill=0, stroke=1)
    c.setLineWidth(1)
    c.setFillColorRGB(0, 0, 0)
    c.circle(420, 300, 40, fill=0, stroke=1)
    c.rect(100, 150, 120, 60, fill=0, stroke=1)
    return norm_box(150, 570, 180, 120)


def page_spec_table_p6(c):
    rows = [
        ("Standby current", "12", "mA"),
        ("Extended housing width", "55.0", "mm"),
        ("Extended housing height", "61.5", "mm"),
        ("Trip threshold", "4.2", "A"),
        ("Insulation class", "Class II", "-"),
    ]
    return draw_spec_table(c, "Power module specification (holdout)", rows, 2, 700)


def page_chart_p7(c):
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, 700, "Torque curve (holdout)")
    ox, oy, ow, oh = 90, 400, 420, 220
    c.rect(ox, oy, ow, oh, fill=0, stroke=1)
    c.setFont("Helvetica", 9)
    c.drawString(ox + ow + 12, oy + 170, "==")
    c.drawString(ox + ow + 30, oy + 170, "rated")
    c.setStrokeColorRGB(0, 0.5, 0)
    c.setLineWidth(2)
    p = c.beginPath()
    p.moveTo(ox + 20, oy + 180)
    p.curveTo(ox + 200, oy + 170, ox + 260, oy + 60, ox + 380, oy + 40)
    c.drawPath(p, fill=0, stroke=1)
    c.setLineWidth(1)
    # raster diagram region below
    img = Image.new("RGB", (900, 300), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([50, 50, 400, 250], outline="black", width=6)
    d.text((150, 140), "pump stage", fill="black")
    d.ellipse([550, 80, 800, 220], outline="black", width=6)
    d.text((620, 140), "valve", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    from reportlab.lib.utils import ImageReader

    c.drawImage(ImageReader(buf), 106, 120, width=400, height=133,
                preserveAspectRatio=True, mask="auto")
    return norm_box(ox + 180, oy + 220, 200, 160)


def page_schematic_p8(c):
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, 700, "Valve schematic (holdout)")
    c.setFont("Helvetica", 10)
    c.drawString(72, 660, "Loop 1")
    c.rect(72, 480, 200, 150, fill=0, stroke=1)
    c.drawString(90, 590, "V2 valve")
    c.rect(110, 520, 40, 30, fill=0, stroke=1)
    c.drawString(320, 660, "Loop 2")
    c.rect(320, 480, 200, 150, fill=0, stroke=1)
    c.drawString(338, 590, "V2 valve")
    c.rect(360, 520, 40, 30, fill=0, stroke=1)
    return norm_box(106, 555, 48, 38)


PAGE_BUILDERS = [
    ("P1", page_spec_table_p1, "spec_table"),
    ("P2", page_chart_p2, "chart"),
    ("P3", page_flowchart_p3, "flowchart"),
    ("P4", page_schematic_p4, "schematic"),
    ("P5", page_shapes_p5, "shapes"),
    ("P6", page_spec_table_p6, "spec_table"),
    ("P7", page_chart_p7, "chart"),
    ("P8", page_schematic_p8, "schematic"),
]


def build_test_pages_pdf() -> tuple[bytes, list]:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    targets = []
    for key, builder, content in PAGE_BUILDERS:
        white_page(c)
        draw_corners(c, SIGNATURES[key])
        target = builder(c)
        targets.append((key, target, content))
        c.showPage()
    c.save()
    return buf.getvalue(), targets


def build_portrait_pdf():
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    white_page(c)
    draw_corners(c, SIGNATURES["PORTRAIT"])
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, 700, "Portrait orientation fixture")
    c.rect(150, 400, 200, 140, fill=0, stroke=1)
    c.drawString(170, 470, "target zone")
    target = norm_box(150, 540, 200, 140)
    c.showPage()
    c.save()
    return buf.getvalue(), target


# ------------------------------------------------------- raw PDFs (rotate/crop)

def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_raw_pdf(page_entries: str, media_box=(0, 0, 612, 792),
                  rotate=None, crop_box=None) -> bytes:
    """Minimal one-page PDF with Helvetica text/shapes. Content stream uses
    PDF user space (origin bottom-left, y up)."""
    content = page_entries.encode("latin-1")
    objects = []
    objects.append("<< /Type /Catalog /Pages 2 0 R >>")
    page_dict = "<< /Type /Page /Parent 2 0 R /MediaBox [%d %d %d %d]" % media_box
    if rotate is not None:
        page_dict += f" /Rotate {rotate}"
    if crop_box is not None:
        page_dict += " /CropBox [%d %d %d %d]" % crop_box
    page_dict += " /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
    objects.append("<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objects.append(page_dict)
    objects.append(f"<< /Length {len(content)} >>\nstream\n".encode("latin-1") + content + b"\nendstream")
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode("latin-1"))
        out.write(obj if isinstance(obj, bytes) else obj.encode("latin-1"))
        out.write(b"\nendobj\n")
    xref_pos = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    out.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.write(f"{off:010d} 00000 n \n".encode("latin-1"))
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF".encode("latin-1")
    )
    return out.getvalue()


def _rgb_pdf(r, g, b):
    return f"{r/255:.4f} {g/255:.4f} {b/255:.4f} rg"


def corner_squares_pdf(rgb, corners):
    ops = []
    ops.append(_rgb_pdf(*rgb))
    for (x, y) in corners:
        ops.append(f"{x} {y} {CORNER_SQ} {CORNER_SQ} re f")
    return "\n".join(ops)


MEDIA_CORNERS = [(0, 0), (PAGE_W - CORNER_SQ, 0), (0, PAGE_H - CORNER_SQ),
                 (PAGE_W - CORNER_SQ, PAGE_H - CORNER_SQ)]


def build_landscape_pdf():
    rgb = SIGNATURES["LANDSCAPE"]
    ops = []
    ops.append("1 1 1 rg 0 0 612 792 re f")
    ops.append(corner_squares_pdf(rgb, MEDIA_CORNERS))
    ops.append("0 0 0 RG 2 w")
    # target feature: stroked rect with unique green outline for detection
    ops.append("0 1 0 RG 6 w 150 300 220 140 re S")
    ops.append("0 0 0 rg BT /F1 16 Tf 150 640 Td (Landscape fixture Rotate 90) Tj ET")
    ops.append("BT /F1 12 Tf 150 250 Td (target outline in green) Tj ET")
    return build_raw_pdf("\n".join(ops), rotate=90)


def build_cropbox_pdf():
    rgb = SIGNATURES["CROPBOX"]
    crop = (100, 100, 512, 692)
    cx0, cy0, cx1, cy1 = crop
    corners = [(cx0, cy0), (cx1 - CORNER_SQ, cy0), (cx0, cy1 - CORNER_SQ),
               (cx1 - CORNER_SQ, cy1 - CORNER_SQ)]
    ops = []
    ops.append(f"1 1 1 rg {cx0} {cy0} {cx1-cx0} {cy1-cy0} re f")
    ops.append(corner_squares_pdf(rgb, corners))
    ops.append("0 1 0 RG 6 w 200 400 150 100 re S")
    ops.append("0 0 0 rg BT /F1 16 Tf 140 640 Td (CropBox fixture) Tj ET")
    return build_raw_pdf("\n".join(ops), crop_box=crop)


def detect_green_bbox(img: Image.Image):
    """Bounding box of pure-green outline pixels, normalized 0-1 (y down)."""
    px = img.convert("RGB")
    w, h = px.size
    data = px.load()
    xs, ys = [], []
    for y in range(h):
        for x in range(w):
            r, g, b = data[x, y]
            if g > 200 and r < 80 and b < 80:
                xs.append(x)
                ys.append(y)
    if not xs:
        raise RuntimeError("target outline not detected in render")
    return [min(xs) / w, min(ys) / h, (max(xs) + 1) / w, (max(ys) + 1) / h]


# ------------------------------------------------------------------- images

def build_exif_jpg():
    rgb = SIGNATURES["EXIF"]
    displayed = Image.new("RGB", (1200, 900), "white")
    d = ImageDraw.Draw(displayed)
    d.rectangle([0, 0, 7, 7], fill=rgb)
    d.rectangle([300, 250, 700, 550], outline="black", width=4)
    d.text((350, 380), "EXIF orientation target", fill="black")
    d.ellipse([800, 550, 1050, 750], outline="black", width=4)
    # Store rotated 90 CCW with EXIF orientation 6 (rotate 90 CW to display).
    from PIL.ExifTags import IFD

    stored = displayed.transpose(Image.ROTATE_90)
    exif = Image.Exif()
    exif[0x0112] = 6
    buf = io.BytesIO()
    stored.save(buf, format="JPEG", quality=95, exif=exif)
    target = [300 / 1200, 250 / 900, 700 / 1200, 550 / 900]
    return buf.getvalue(), target


def build_standard_png():
    rgb = SIGNATURES["STANDARD"]
    img = Image.new("RGB", (1400, 1000), "white")
    d = ImageDraw.Draw(img)
    for x in range(4):
        for y in range(4):
            d.point((x, y), fill=rgb)
    d.rectangle([350, 300, 900, 650], outline="black", width=4)
    d.text((400, 460), "standard PNG target", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    target = [350 / 1400, 300 / 1000, 900 / 1400, 650 / 1000]
    return buf.getvalue(), target


# ------------------------------------------------------------------- holdout

def build_holdout():
    p6 = SIGNATURES["P6"]
    p7 = SIGNATURES["P7"]
    p8 = SIGNATURES["P8"]
    q = []
    q.append({"id": "h01", "type": "text", "question": "Where is the standby current specified?",
              "expected_page": list(p6), "expected_region": [0.1, 0.1, 0.8, 0.3],
              "notes": "Holdout spec table page; distractor rows nearby."})
    q.append({"id": "h02", "type": "text", "question": "Where is the insulation class listed?",
              "expected_page": list(p6), "expected_region": [0.1, 0.1, 0.8, 0.3],
              "notes": "Last row of the holdout spec table."})
    q.append({"id": "h03", "type": "text", "question": "What are the loop labels in the valve schematic?",
              "expected_page": list(p8), "expected_region": [0.1, 0.6, 0.9, 0.9],
              "notes": "Loop 1 / Loop 2 headings."})
    q.append({"id": "h04", "type": "text", "question": "Where is the pump stage shown?",
              "expected_page": list(p7), "expected_region": [0.1, 0.05, 0.6, 0.3],
              "notes": "Raster diagram region on the chart page."})
    q.append({"id": "h05", "type": "table", "question": "Where is the extended housing width row?",
              "expected_page": list(p6), "expected_region": [0.1, 0.15, 0.85, 0.25],
              "notes": "Target row; standby-current and height rows are distractors."})
    q.append({"id": "h06", "type": "table", "question": "Where is the extended housing height row?",
              "expected_page": list(p6), "expected_region": [0.1, 0.15, 0.85, 0.25],
              "notes": "Target row; width row is the near distractor (same units)."})
    q.append({"id": "h07", "type": "table", "question": "Where is the trip threshold row?",
              "expected_page": list(p6), "expected_region": [0.1, 0.15, 0.85, 0.25],
              "notes": "Amperes row among millimetre distractors."})
    q.append({"id": "h08", "type": "table", "question": "Where is the V2 valve in Loop 2?",
              "expected_page": list(p8), "expected_region": [0.5, 0.3, 0.85, 0.6],
              "notes": "Loop 1 V2 valve is the repeated-label distractor."})
    visuals = [
        ("h09", "Which way does the rated torque curve fall at high load?",
         list(p7), [0.35, 0.35, 0.8, 0.7], "Curve region with axes and legend."),
        ("h10", "Where is the rated legend entry relative to the curve?",
         list(p7), [0.7, 0.5, 0.95, 0.8], "Legend plus curve context."),
        ("h11", "Where is the pump stage relative to the valve?",
         list(p7), [0.1, 0.05, 0.9, 0.3], "Raster region; spatial relation."),
        ("h12", "Where is the V2 valve symbol in Loop 1?",
         list(p8), [0.1, 0.3, 0.45, 0.6], "Loop 2 symbol is the distractor."),
        ("h13", "Where is the mounting context around the Loop 2 valve?",
         list(p8), [0.5, 0.3, 0.85, 0.6], "Symbol plus surrounding sub-diagram."),
        ("h14", "Where is the extended housing dimension pair located?",
         list(p6), [0.1, 0.15, 0.85, 0.3], "Two adjacent rows form the region."),
        ("h15", "Where does the torque curve start at low load?",
         list(p7), [0.15, 0.55, 0.45, 0.85], "Left end of the rated curve."),
        ("h16", "Where is the Loop 1 sub-diagram boundary?",
         list(p8), [0.1, 0.3, 0.45, 0.65], "Whole Loop 1 rectangle."),
    ]
    for qid, text, page, region, notes in visuals:
        q.append({"id": qid, "type": "visual", "question": text,
                  "expected_page": page, "expected_region": region, "notes": notes})
    absent = [
        ("h17", "Where is the emergency stop button shown?",
         "No stop button exists on holdout pages; plausible control labels present."),
        ("h18", "Where is the battery compartment latch?",
         "No battery content on holdout pages; housing rows are distractors."),
        ("h19", "Where is the network address setting?",
         "No network content; schematic labels are distractors."),
        ("h20", "Where is the calibration due-date sticker?",
         "No sticker shown; table metadata rows are distractors."),
    ]
    for qid, text, notes in absent:
        q.append({"id": qid, "type": "absent", "question": text,
                  "expected_page": None, "expected_region": None, "notes": notes})
    assert len(q) == 20
    return q


# ------------------------------------------------------------------- main

def main() -> None:
    if canvas is None:
        raise RuntimeError("reportlab is required to generate fixtures")
    GENERATED.mkdir(parents=True, exist_ok=True)

    dev_entries = []
    evidence_targets = {}  # key -> target box (for debugging only)

    # 8-page test PDF
    pdf_bytes, targets = build_test_pages_pdf()
    (GENERATED / "test_pages.pdf").write_bytes(pdf_bytes)
    for i, (key, target, content) in enumerate(targets):
        w, h = pdf_canonical_size(pdf_bytes, i)
        render = render_pdf_canonical(pdf_bytes, i)
        assert signature_ok(render, SIGNATURES[key]), f"signature missing on {key}"
        assert (w, h) == render.size
        if i < 5:
            dev_entries.append({
                "fixture_id": f"dev_p{i + 1}",
                "fixture_file": "fixtures/generated/test_pages.pdf",
                "page_index": i,
                "signature_rgb": list(SIGNATURES[key]),
                "target": [round(float(v), 5) for v in target],
                "raster_width_px": w,
                "raster_height_px": h,
                "content": content,
            })
        evidence_targets[key] = target

    # portrait
    portrait_bytes, portrait_target = build_portrait_pdf()
    (GENERATED / "portrait.pdf").write_bytes(portrait_bytes)
    w, h = pdf_canonical_size(portrait_bytes, 0)
    render = render_pdf_canonical(portrait_bytes, 0)
    assert signature_ok(render, SIGNATURES["PORTRAIT"]), "portrait signature missing"
    dev_entries.append({
        "fixture_id": "orientation_portrait",
        "fixture_file": "fixtures/generated/portrait.pdf",
        "page_index": 0,
        "signature_rgb": list(SIGNATURES["PORTRAIT"]),
        "target": [round(float(v), 5) for v in portrait_target],
        "raster_width_px": w,
        "raster_height_px": h,
        "content": "orientation_portrait",
    })

    # landscape (Rotate=90) with empirically detected target
    landscape_bytes = build_landscape_pdf()
    (GENERATED / "landscape.pdf").write_bytes(landscape_bytes)
    w, h = pdf_canonical_size(landscape_bytes, 0)
    render = render_pdf_canonical(landscape_bytes, 0)
    assert signature_ok(render, SIGNATURES["LANDSCAPE"]), "landscape signature missing"
    land_target = detect_green_bbox(render)
    dev_entries.append({
        "fixture_id": "orientation_landscape",
        "fixture_file": "fixtures/generated/landscape.pdf",
        "page_index": 0,
        "signature_rgb": list(SIGNATURES["LANDSCAPE"]),
        "target": [round(float(v), 5) for v in land_target],
        "raster_width_px": w,
        "raster_height_px": h,
        "content": "orientation_landscape",
    })

    # cropbox with empirically detected target
    cropbox_bytes = build_cropbox_pdf()
    (GENERATED / "cropbox.pdf").write_bytes(cropbox_bytes)
    w, h = pdf_canonical_size(cropbox_bytes, 0)
    render = render_pdf_canonical(cropbox_bytes, 0)
    assert signature_ok(render, SIGNATURES["CROPBOX"]), "cropbox signature missing"
    crop_target = detect_green_bbox(render)
    dev_entries.append({
        "fixture_id": "orientation_cropbox",
        "fixture_file": "fixtures/generated/cropbox.pdf",
        "page_index": 0,
        "signature_rgb": list(SIGNATURES["CROPBOX"]),
        "target": [round(float(v), 5) for v in crop_target],
        "raster_width_px": w,
        "raster_height_px": h,
        "content": "orientation_cropbox",
    })

    # EXIF JPEG
    exif_bytes, exif_target = build_exif_jpg()
    (GENERATED / "exif_oriented.jpg").write_bytes(exif_bytes)
    exif_img = decode_image_canonical(exif_bytes)
    assert signature_ok(exif_img, SIGNATURES["EXIF"]), "exif signature missing"
    dev_entries.append({
        "fixture_id": "orientation_exif_jpeg",
        "fixture_file": "fixtures/generated/exif_oriented.jpg",
        "page_index": 0,
        "signature_rgb": list(SIGNATURES["EXIF"]),
        "target": [round(float(v), 5) for v in exif_target],
        "raster_width_px": exif_img.size[0],
        "raster_height_px": exif_img.size[1],
        "content": "orientation_exif_jpeg",
    })

    # standard PNG
    png_bytes, png_target = build_standard_png()
    (GENERATED / "standard.png").write_bytes(png_bytes)
    png_img = decode_image_canonical(png_bytes)
    assert signature_ok(png_img, SIGNATURES["STANDARD"]), "png signature missing"
    dev_entries.append({
        "fixture_id": "orientation_standard_png",
        "fixture_file": "fixtures/generated/standard.png",
        "page_index": 0,
        "signature_rgb": list(SIGNATURES["STANDARD"]),
        "target": [round(float(v), 5) for v in png_target],
        "raster_width_px": png_img.size[0],
        "raster_height_px": png_img.size[1],
        "content": "orientation_standard_png",
    })

    with open(PROJECT_ROOT / "fixtures" / "development.json", "w", encoding="utf-8") as f:
        json.dump(dev_entries, f, indent=2)
        f.write("\n")

    with open(PROJECT_ROOT / "fixtures" / "holdout.json", "w", encoding="utf-8") as f:
        json.dump(build_holdout(), f, indent=2)
        f.write("\n")

    manifest = {}
    for name in ["test_pages.pdf", "portrait.pdf", "landscape.pdf", "cropbox.pdf",
                 "exif_oriented.jpg", "standard.png"]:
        manifest[name] = sha256_file(GENERATED / name)
    manifest["development.json"] = sha256_file(PROJECT_ROOT / "fixtures" / "development.json")
    manifest["holdout.json"] = sha256_file(PROJECT_ROOT / "fixtures" / "holdout.json")
    with open(GENERATED / "manifest.json", "w", encoding="utf-8") as f:
        json.dump({"files": manifest}, f, indent=2)
        f.write("\n")

    print(f"generated {len(dev_entries)} development entries; holdout=20 questions")


if __name__ == "__main__":
    main()
