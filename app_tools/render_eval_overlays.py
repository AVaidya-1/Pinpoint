"""Render evaluation boxes over canonical pages for human review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--question", action="append", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    report = json.loads((args.run_dir / "report.json").read_text(encoding="utf-8"))
    by_id = {entry["id"]: entry for entry in report["questions"]}
    args.out_dir.mkdir(parents=True, exist_ok=True)

    for question_id in args.question:
        entry = by_id[question_id]
        page_id = entry["expected_page_id"]
        source = args.run_dir / "data" / "pages" / page_id / "canonical.png"
        with Image.open(source).convert("RGB") as image:
            draw = ImageDraw.Draw(image)
            width, height = image.size
            for index, box in enumerate(entry.get("actual_boxes", []), start=1):
                x0, y0, x1, y1 = box
                coords = (x0 * width, y0 * height, x1 * width, y1 * height)
                draw.rectangle(coords, outline=(220, 30, 30), width=6)
                draw.text((coords[0] + 8, coords[1] + 8), f"actual {index}", fill=(220, 30, 30), stroke_width=2, stroke_fill="white")
            image.save(args.out_dir / f"{question_id}.png")


if __name__ == "__main__":
    main()
