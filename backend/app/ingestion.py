from __future__ import annotations

import hashlib
import io
import json
import uuid
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ExifTags

from app import config
from app.db import get_db


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _apply_exif_orientation(img: Image.Image) -> Image.Image:
    try:
        exif = img.getexif()
        orientation_key = None
        for k, v in ExifTags.TAGS.items():
            if v == "Orientation":
                orientation_key = k
                break
        if orientation_key and orientation_key in exif:
            orient = exif[orientation_key]
            rotations = {3: 180, 6: 270, 8: 90}
            if orient in rotations:
                img = img.rotate(rotations[orient], expand=True)
    except Exception:
        pass
    return img


def _resize_long_edge(img: Image.Image, max_edge: int) -> Image.Image:
    w, h = img.size
    if max(w, h) <= max_edge:
        return img
    scale = max_edge / max(w, h)
    new_w = int(w * scale)
    new_h = int(h * scale)
    return img.resize((new_w, new_h), Image.LANCZOS)


def _save_model_image(img: Image.Image, path: Path) -> Path:
    resized = _resize_long_edge(img, config.MODEL_LONG_EDGE)
    buf = io.BytesIO()
    resized.save(buf, format="PNG", optimize=True)
    while buf.tell() > config.MODEL_MAX_BYTES and resized.size[0] > 200:
        scale = 0.8
        new_w = int(resized.size[0] * scale)
        new_h = int(resized.size[1] * scale)
        resized = resized.resize((new_w, new_h), Image.LANCZOS)
        buf = io.BytesIO()
        resized.save(buf, format="PNG", optimize=True)
    path.write_bytes(buf.getvalue())
    return path


def validate_upload(filename: str, data: bytes) -> tuple[str, str]:
    """Return (mime_type, error_or_empty)."""
    ext = Path(filename).suffix.lower()
    mime_map = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }
    if ext not in mime_map:
        return "", f"Unsupported file type: {ext}"
    if len(data) > 25 * 1024 * 1024:
        return "", "File exceeds 25 MB limit"
    mime = mime_map[ext]
    if mime == "application/pdf":
        if not data[:5] == b"%PDF-":
            return "", "Invalid PDF file"
    elif mime.startswith("image/"):
        try:
            img = Image.open(io.BytesIO(data))
            img.verify()
        except Exception:
            return "", "Invalid or corrupted image file"
    return mime, ""


def get_pdf_page_count(data: bytes) -> int:
    pdf = pdfium.PdfDocument(data)
    count = len(pdf)
    pdf.close()
    return count


def parse_page_ranges(spec: str, total: int) -> list[int]:
    """Parse '1-4,7,10-12' into sorted unique 1-based page numbers."""
    pages = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start, end = int(start_s), int(end_s)
            for p in range(max(1, start), min(total, end) + 1):
                pages.add(p)
        else:
            p = int(part)
            if 1 <= p <= total:
                pages.add(p)
    return sorted(pages)


def import_pdf_pages(
    doc_id: str, data: bytes, filename: str, selected_pages: list[int]
) -> None:
    file_hash = sha256_of(data)
    original_path = config.ORIGINALS_DIR / f"{doc_id}.pdf"
    original_path.write_bytes(data)

    pdf = pdfium.PdfDocument(data)
    total = len(pdf)

    with get_db() as conn:
        conn.execute(
            "UPDATE documents SET sha256=?, original_path=?, original_page_count=?, "
            "selected_pages_json=? WHERE id=?",
            (file_hash, str(original_path), total, json.dumps(selected_pages), doc_id),
        )

    try:
        for phys_page in selected_pages:
            page_idx = phys_page - 1
            if page_idx < 0 or page_idx >= total:
                continue

            pdf_page = pdf[page_idx]
            scale = min(config.CANONICAL_LONG_EDGE / max(pdf_page.get_width(), pdf_page.get_height()), 1.0)
            if scale < 1.0:
                bitmap = pdf_page.render(scale=scale * 72 / 72)
            else:
                scale_factor = config.CANONICAL_LONG_EDGE / max(pdf_page.get_width(), pdf_page.get_height())
                bitmap = pdf_page.render(scale=scale_factor)

            pil_image = bitmap.to_pil()
            if pil_image.mode != "RGB":
                pil_image = pil_image.convert("RGB")

            page_id = str(uuid.uuid4())
            canonical_path = config.PAGES_DIR / f"{page_id}_canonical.png"
            model_path = config.PAGES_DIR / f"{page_id}_model.png"

            canonical = _resize_long_edge(pil_image, config.CANONICAL_LONG_EDGE)
            canonical.save(str(canonical_path), format="PNG")
            _save_model_image(pil_image, model_path)

            raster_hash = sha256_of(canonical_path.read_bytes())
            w, h = canonical.size

            with get_db() as conn:
                conn.execute(
                    "INSERT INTO pages (id, document_id, physical_page_number, "
                    "canonical_path, model_image_path, width_px, height_px, raster_sha256) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (page_id, doc_id, phys_page, str(canonical_path), str(model_path), w, h, raster_hash),
                )

        with get_db() as conn:
            conn.execute("UPDATE documents SET status='ready' WHERE id=?", (doc_id,))
    except Exception as exc:
        with get_db() as conn:
            conn.execute(
                "UPDATE documents SET status='failed', error_code=? WHERE id=?",
                (str(exc)[:200], doc_id),
            )
        raise
    finally:
        pdf.close()


def import_image(doc_id: str, data: bytes, filename: str) -> None:
    file_hash = sha256_of(data)
    ext = Path(filename).suffix.lower()
    original_path = config.ORIGINALS_DIR / f"{doc_id}{ext}"
    original_path.write_bytes(data)

    try:
        img = Image.open(io.BytesIO(data))
        img = _apply_exif_orientation(img)
        if img.mode != "RGB":
            img = img.convert("RGB")

        w_orig, h_orig = img.size
        if w_orig * h_orig > 20_000_000:
            with get_db() as conn:
                conn.execute(
                    "UPDATE documents SET status='failed', error_code=? WHERE id=?",
                    ("Image exceeds 20 megapixel limit", doc_id),
                )
            return

        page_id = str(uuid.uuid4())
        canonical_path = config.PAGES_DIR / f"{page_id}_canonical.png"
        model_path = config.PAGES_DIR / f"{page_id}_model.png"

        canonical = _resize_long_edge(img, config.CANONICAL_LONG_EDGE)
        canonical.save(str(canonical_path), format="PNG")
        _save_model_image(img, model_path)

        raster_hash = sha256_of(canonical_path.read_bytes())
        w, h = canonical.size

        with get_db() as conn:
            conn.execute(
                "UPDATE documents SET sha256=?, original_path=?, original_page_count=1, "
                "selected_pages_json='[1]' WHERE id=?",
                (file_hash, str(original_path), doc_id),
            )
            conn.execute(
                "INSERT INTO pages (id, document_id, physical_page_number, "
                "canonical_path, model_image_path, width_px, height_px, raster_sha256) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (page_id, doc_id, 1, str(canonical_path), str(model_path), w, h, raster_hash),
            )
            conn.execute("UPDATE documents SET status='ready' WHERE id=?", (doc_id,))
    except Exception as exc:
        with get_db() as conn:
            conn.execute(
                "UPDATE documents SET status='failed', error_code=? WHERE id=?",
                (str(exc)[:200], doc_id),
            )
        raise
