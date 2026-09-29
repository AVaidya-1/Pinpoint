"""Render the recorded public-document evidence boxes for human review."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "out" / "public-doc" / "report.json"
OUT = ROOT / "out" / "public-doc" / "review"


def main() -> None:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    for question in report["questions"]:
        for evidence in question.get("evidence", []):
            page_id = evidence["page_id"]
            source = ROOT / "data" / "pages" / page_id / "canonical.png"
            with Image.open(source).convert("RGB") as image:
                draw = ImageDraw.Draw(image)
                width, height = image.size
                for index, box in enumerate(evidence["boxes"], start=1):
                    x0, y0, x1, y1 = box
                    coords = (x0 * width, y0 * height, x1 * width, y1 * height)
                    draw.rectangle(coords, outline=(220, 30, 30), width=7)
                    draw.text(
                        (coords[0] + 8, coords[1] + 8),
                        f"actual {index}",
                        fill=(220, 30, 30),
                        stroke_width=2,
                        stroke_fill="white",
                    )
                image.save(
                    OUT / f"{question['id']}-page-{evidence['physical_page_number']}.png"
                )


if __name__ == "__main__":
    main()
