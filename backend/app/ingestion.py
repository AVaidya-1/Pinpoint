"""Ingestion: file validation, content identity, pypdfium2 rendering with
CropBox/Rotate respected, EXIF normalization, canonical + model rasters,
byte-for-byte original persistence.

PDFium is not thread-safe: all rendering goes through one module-level lock.
"""

import hashlib
import io
import threading
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageOps

RENDER_LOCK = threading.Lock()

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_IMAGE_MEGAPIXELS = 20.0
CANONICAL_LONG_EDGE = 3000
MODEL_LONG_EDGE = 2048
MODEL_MAX_BYTES = 4 * 1024 * 1024

PDF_MAGIC = b"%PDF-"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"

EXTENSION_MIME = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sniff_kind(data: bytes) -> str | None:
    if data.startswith(PDF_MAGIC):
        return "pdf"
    if data.startswith(PNG_MAGIC):
        return "png"
    if data.startswith(JPEG_MAGIC):
        return "jpeg"
    return None


def validate_upload(filename: str, data: bytes) -> tuple[str, str]:
    """Returns (kind, mime_type). Raises UploadRejected with a stable code."""
    ext = Path(filename).suffix.lower()
    if ext not in EXTENSION_MIME:
        raise UploadRejected("unsupported_type", f"Unsupported file extension: {ext!r}")
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadRejected("too_large", "Upload exceeds the 25 MB limit")
    kind = sniff_kind(data)
    if kind is None:
        raise UploadRejected("unsupported_type", "Unrecognized file signature")
    expected = {"pdf": "application/pdf", "png": "image/png", "jpeg": "image/jpeg"}[kind]
    if EXTENSION_MIME[ext] != expected:
        raise UploadRejected(
            "unsupported_type",
            f"Extension {ext!r} does not match file signature ({kind})",
        )
    return kind, expected


class UploadRejected(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def pdf_page_count(data: bytes) -> int:
    with RENDER_LOCK:
        doc = pdfium.PdfDocument(io.BytesIO(data))
        try:
            return len(doc)
        finally:
            doc.close()


def pdf_display_size_pt(data: bytes, index: int) -> tuple[float, float]:
    """Displayed page size in points (CropBox + rotation applied)."""
    with RENDER_LOCK:
        doc = pdfium.PdfDocument(io.BytesIO(data))
        try:
            page = doc[index]
            try:
                # get_size() returns the displayed size in points,
                # accounting for CropBox and /Rotate.
                w, h = page.get_size()
                return float(w), float(h)
            finally:
                page.close()
        finally:
            doc.close()


def pdf_canonical_scale(display_w_pt: float, display_h_pt: float) -> float:
    long_edge = max(display_w_pt, display_h_pt)
    if long_edge <= 0:
        raise ValueError("Invalid PDF page size")
    return CANONICAL_LONG_EDGE / long_edge


def pdf_canonical_size(data: bytes, index: int) -> tuple[int, int]:
    """Exact canonical raster dimensions the renderer will produce."""
    w_pt, h_pt = pdf_display_size_pt(data, index)
    scale = pdf_canonical_scale(w_pt, h_pt)
    with RENDER_LOCK:
        doc = pdfium.PdfDocument(io.BytesIO(data))
        try:
            page = doc[index]
            try:
                bitmap = page.render(scale=scale)
                try:
                    return int(bitmap.width), int(bitmap.height)
                finally:
                    bitmap.close()
            finally:
                page.close()
        finally:
            doc.close()


def render_pdf_canonical(data: bytes, index: int) -> Image.Image:
    """Render one PDF page to its canonical RGB raster."""
    w_pt, h_pt = pdf_display_size_pt(data, index)
    scale = pdf_canonical_scale(w_pt, h_pt)
    with RENDER_LOCK:
        doc = pdfium.PdfDocument(io.BytesIO(data))
        try:
            page = doc[index]
            try:
                bitmap = page.render(scale=scale)
                try:
                    pil = bitmap.to_pil().convert("RGB")
                finally:
                    bitmap.close()
            finally:
                page.close()
        finally:
            doc.close()
    return pil


def decode_image_canonical(data: bytes) -> Image.Image:
    """Decode PNG/JPEG, apply EXIF orientation once, convert to RGB."""
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("RGB")
    w, h = img.size
    megapixels = (w * h) / 1_000_000.0
    if megapixels > MAX_IMAGE_MEGAPIXELS:
        raise UploadRejected(
            "too_large",
            f"Image exceeds {MAX_IMAGE_MEGAPIXELS:.0f} megapixels after decoding",
        )
    long_edge = max(w, h)
    if long_edge > CANONICAL_LONG_EDGE:
        scale = CANONICAL_LONG_EDGE / long_edge
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    return img


def render_canonical(kind: str, data: bytes, index: int = 0) -> Image.Image:
    if kind == "pdf":
        return render_pdf_canonical(data, index)
    return decode_image_canonical(data)


def make_model_image(canonical: Image.Image) -> tuple[Image.Image, bool]:
    """Model-input derivative: long edge <= 2048 and encoded <= 4 MB.
    Returns (image, was_reduced)."""
    w, h = canonical.size
    img = canonical
    reduced = False
    if max(w, h) > MODEL_LONG_EDGE:
        scale = MODEL_LONG_EDGE / max(w, h)
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
        reduced = True
    # Enforce encoded-size cap by shrinking until it fits.
    while True:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        if len(buf.getvalue()) <= MODEL_MAX_BYTES:
            break
        w2, h2 = img.size
        if w2 <= 16 or h2 <= 16:
            break
        img = img.resize((int(w2 * 0.8), int(h2 * 0.8)), Image.LANCZOS)
        reduced = True
    return img, reduced


def save_canonical_and_model(
    img: Image.Image, page_dir: Path
) -> tuple[Path, Path, str]:
    page_dir.mkdir(parents=True, exist_ok=True)
    canonical_path = page_dir / "canonical.png"
    model_path = page_dir / "model.png"
    img.save(canonical_path, format="PNG")
    model_img, _ = make_model_image(img)
    model_img.save(model_path, format="PNG")
    return canonical_path, model_path, sha256_file(canonical_path)
