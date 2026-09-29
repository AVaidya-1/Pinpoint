"""PDF indexing.

Pass 1 (local, seconds even for 500 pages): PyMuPDF extracts every text line
with its box and detects figure regions (embedded images and clusters of
vector drawings, joined with their captions). The document is askable as
soon as this pass finishes.

Pass 2 (background, network): page embeddings for semantic retrieval, then
Nemotron Parse OCR for pages that have no text layer (scans, raster
diagrams), after which those pages are re-indexed and re-embedded.

All boxes are normalized [x0, y0, x1, y1] in 0-1 of the displayed
(rotation-applied) page, so the viewer can draw them at any zoom.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pymupdf

from . import embeddings, store
from .config import get_settings

log = logging.getLogger(__name__)

MIN_TEXT_CHARS = 25          # below this a page is treated as having no text layer
MIN_FIGURE_AREA = 0.012      # fraction of the page
MAX_FIGURES_PER_PAGE = 12
_CAPTION_RE = re.compile(r"^\s*(fig(ure)?|table|chart|diagram|schematic|plate)\.?\s*[\w.\-]+", re.I)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _norm(rect, page) -> list[float]:
    r = pymupdf.Rect(rect) * page.rotation_matrix
    w, h = page.rect.width, page.rect.height
    return [
        round(max(0.0, min(1.0, r.x0 / w)), 5),
        round(max(0.0, min(1.0, r.y0 / h)), 5),
        round(max(0.0, min(1.0, r.x1 / w)), 5),
        round(max(0.0, min(1.0, r.y1 / h)), 5),
    ]


def _area(b) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _union(a, b) -> list[float]:
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]


def _overlaps(a, b, pad: float = 0.0) -> bool:
    return not (a[2] + pad < b[0] or b[2] + pad < a[0] or a[3] + pad < b[1] or b[3] + pad < a[1])


def _contains(outer, inner, tol: float = 0.004) -> bool:
    return (inner[0] >= outer[0] - tol and inner[1] >= outer[1] - tol
            and inner[2] <= outer[2] + tol and inner[3] <= outer[3] + tol)


# ---------------------------------------------------------------------------
# Pass 1: text lines and figures
# ---------------------------------------------------------------------------

def _extract_lines(page) -> list[dict]:
    lines: list[dict] = []
    data = page.get_text("dict", sort=True, flags=pymupdf.TEXTFLAGS_TEXT)
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            text = "".join(span.get("text", "") for span in line.get("spans", []))
            text = re.sub(r"\s+", " ", text).strip()
            if not text:
                continue
            box = _norm(line["bbox"], page)
            if _area(box) <= 0:
                continue
            lines.append({"text": text, "box": box})
    return lines


GRID = 200  # occupancy-grid cells per page side (~3-4 pt per cell)


def _cluster_vector_drawings(page) -> list[list[float]]:
    """Group vector paths that touch (within ~1 cell) into figure regions.

    Equivalent in spirit to PyMuPDF's cluster_drawings(), but it reads paths
    with the C-level get_cdrawings() and merges them on a coarse occupancy
    grid, which stays fast on pages with tens of thousands of paths.
    """
    # Drawing coordinates are unrotated; _norm() applies the page rotation.
    w, h = page.cropbox.width or 1, page.cropbox.height or 1
    grid = bytearray(GRID * GRID)
    any_path = False
    for path in page.get_cdrawings():
        x0, y0, x1, y1 = path["rect"]
        if (x1 - x0) * (y1 - y0) > 0.9 * w * h:
            continue  # page background / frame
        # Paths within ~one cell (3-4 pt) of each other join the same figure.
        cx0 = max(0, int(x0 / w * GRID))
        cy0 = max(0, int(y0 / h * GRID))
        cx1 = min(GRID - 1, int(x1 / w * GRID))
        cy1 = min(GRID - 1, int(y1 / h * GRID))
        for cy in range(cy0, cy1 + 1):
            row = cy * GRID
            grid[row + cx0:row + cx1 + 1] = b"\x01" * (cx1 - cx0 + 1)
        any_path = True
    if not any_path:
        return []
    boxes: list[list[float]] = []
    for start in range(GRID * GRID):
        if grid[start] != 1:
            continue
        grid[start] = 2
        stack = [start]
        gx0 = gx1 = start % GRID
        gy0 = gy1 = start // GRID
        while stack:
            cell = stack.pop()
            cx, cy = cell % GRID, cell // GRID
            gx0, gx1, gy0, gy1 = min(gx0, cx), max(gx1, cx), min(gy0, cy), max(gy1, cy)
            for nb in (cell - 1 if cx else -1, cell + 1 if cx < GRID - 1 else -1,
                       cell - GRID, cell + GRID):
                if 0 <= nb < GRID * GRID and grid[nb] == 1:
                    grid[nb] = 2
                    stack.append(nb)
        rect = pymupdf.Rect(gx0 / GRID * w, gy0 / GRID * h,
                            (gx1 + 1) / GRID * w, (gy1 + 1) / GRID * h)
        if rect.is_valid and not rect.is_empty:
            boxes.append(_norm(rect, page))
    return boxes


def _figure_candidates(page) -> list[list[float]]:
    boxes: list[list[float]] = []
    try:
        for info in page.get_image_info():
            boxes.append(_norm(info["bbox"], page))
    except Exception:  # noqa: BLE001 - malformed image streams
        pass
    try:
        boxes.extend(_cluster_vector_drawings(page))
    except Exception:  # noqa: BLE001
        pass
    boxes = [b for b in boxes if MIN_FIGURE_AREA <= _area(b) <= 0.92]
    # Merge overlapping or touching regions until stable.
    merged = True
    while merged:
        merged = False
        out: list[list[float]] = []
        for b in boxes:
            for i, o in enumerate(out):
                if _overlaps(b, o, pad=0.006):
                    out[i] = _union(b, o)
                    merged = True
                    break
            else:
                out.append(b)
        boxes = out
    return boxes


def _extract_figures(lines: list[dict], candidates: list[list[float]]) -> list[dict]:
    figures: list[dict] = []
    for box in candidates:
        labels = [ln["text"] for ln in lines if _contains(box, ln["box"])]
        # A "figure" that is just a paragraph with a background shade is text.
        label_chars = sum(len(t) for t in labels)
        if label_chars > 1500:
            continue
        caption = None
        best = 0.08
        for ln in lines:
            if not _CAPTION_RE.match(ln["text"]):
                continue
            lb = ln["box"]
            horizontal = min(box[2], lb[2]) - max(box[0], lb[0]) > 0
            if not horizontal:
                continue
            gap = lb[1] - box[3] if lb[1] >= box[3] else box[1] - lb[3]
            if -0.01 <= gap < best:
                best = gap
                caption = ln["text"]
        figures.append({
            "box": [round(v, 5) for v in box],
            "caption": caption,
            "labels": labels[:40],
        })
    figures.sort(key=lambda f: -_area(f["box"]))
    figures = figures[:MAX_FIGURES_PER_PAGE]
    figures.sort(key=lambda f: (f["box"][1], f["box"][0]))
    for i, f in enumerate(figures, 1):
        f["id"] = f"F{i}"
    return figures


def extract_page(page) -> dict:
    lines = _extract_lines(page)
    figures = _extract_figures(lines, _figure_candidates(page))
    text = "\n".join(ln["text"] for ln in lines)
    has_text = len(re.sub(r"\s", "", text)) >= MIN_TEXT_CHARS
    return {
        "page_no": page.number + 1,
        "width": page.rect.width,
        "height": page.rect.height,
        "text": text,
        "lines": lines,
        "figures": figures,
        "source": "text" if has_text else "none",
    }


def render_page_png(pdf_file: Path, page_no: int, max_side: int = 1400,
                    clip: list[float] | None = None) -> bytes:
    """Render one page (optionally a normalized clip of it) to PNG bytes."""
    with pymupdf.open(pdf_file) as doc:
        page = doc[page_no - 1]
        rect = page.rect
        if clip is not None:
            # Clip is in displayed-page space; map back to unrotated space.
            display = pymupdf.Rect(clip[0] * rect.width, clip[1] * rect.height,
                                   clip[2] * rect.width, clip[3] * rect.height)
            area = display * page.derotation_matrix
        else:
            area = page.cropbox
        longest = max(pymupdf.Rect(area).width, pymupdf.Rect(area).height) or 1
        zoom = min(4.0, max_side / longest)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=area, alpha=False)
        return pix.tobytes("png")


# ---------------------------------------------------------------------------
# Pass 2: OCR for pages without a text layer
# ---------------------------------------------------------------------------

def _ocr_page(pdf_file: Path, page_no: int) -> dict | None:
    from .providers import nemotron

    import tempfile

    png = render_page_png(pdf_file, page_no, max_side=1600)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(png)
        tmp_path = Path(tmp.name)
    try:
        elements = []
        for attempt in range(3):  # parse_page returns [] on API errors
            elements = nemotron.parse_page(tmp_path, get_settings())
            if elements:
                break
            time.sleep(3 * (attempt + 1))
    finally:
        tmp_path.unlink(missing_ok=True)
    lines = []
    for el in elements:
        # An OCR element is a block (possibly several lines) with one box.
        clean = re.sub(r"<[^>]+>|[#*|`\\]+", " ", el["text"])
        clean = re.sub(r"\s+", " ", clean).strip()
        if clean:
            lines.append({"text": clean, "box": [round(v, 5) for v in el["bbox"]]})
    if not lines:
        return None
    return {"lines": lines, "text": "\n".join(ln["text"] for ln in lines)}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _set(doc_id: str, **fields) -> None:
    cols = ", ".join(f"{k} = ?" for k in fields)
    with store.connect() as conn:
        conn.execute(f"UPDATE documents SET {cols} WHERE id = ?", (*fields.values(), doc_id))


PAGES_PER_TASK = 32


def _extract_pages(args: tuple[str, list[int]]) -> list[dict]:
    """Worker: analyze a chunk of pages (0-based indexes) of one PDF."""
    path, indexes = args
    with pymupdf.open(path) as doc:
        return [extract_page(doc[i]) for i in indexes]


class _InlinePool:
    """Same interface as a process pool, for small PDFs (no spawn cost)."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def map(self, fn, items):
        return map(fn, items)


def _pool_for(total_pages: int):
    if total_pages <= 2 * PAGES_PER_TASK:
        return _InlinePool()
    from concurrent.futures import ProcessPoolExecutor

    workers = max(1, min(6, (os.cpu_count() or 2) - 1))
    return ProcessPoolExecutor(max_workers=workers)


def index_document(doc_id: str) -> None:
    pdf_file = store.pdf_path(doc_id)
    settings = get_settings()
    try:
        no_text: list[int] = []
        with pymupdf.open(pdf_file) as doc:
            total = doc.page_count
        # Page analysis is CPU-bound; spread chunks of pages over processes.
        chunks = [list(range(s, min(s + PAGES_PER_TASK, total))) for s in range(0, total, PAGES_PER_TASK)]
        done = 0
        with _pool_for(total) as pool:
            for pages in pool.map(_extract_pages, [(str(pdf_file), c) for c in chunks]):
                with store.connect() as conn:
                    for info in pages:
                        if info["source"] == "none":
                            no_text.append(info["page_no"])
                        store.upsert_page(conn, doc_id, info)
                    done += len(pages)
                    conn.execute("UPDATE documents SET indexed_pages = ? WHERE id = ?", (done, doc_id))
        ocr_targets = no_text if (settings.ocr_enabled and settings.nvidia_api_key) else []
        _set(doc_id, status="ready", ocr_pages_total=len(ocr_targets))
    except Exception as exc:  # noqa: BLE001
        log.exception("Indexing failed for %s", doc_id)
        _set(doc_id, status="error", error=f"Could not read this PDF: {exc}")
        return
    enrich_document(doc_id, ocr_targets)


def enrich_document(doc_id: str, ocr_targets: list[int] | None = None) -> None:
    """Background pass 2: text embeddings, page-image embeddings, OCR."""
    pdf_file = store.pdf_path(doc_id)
    settings = get_settings()
    ocr_targets = ocr_targets or []
    try:
        embeddings.embed_document(doc_id)
        _set(doc_id, embedded=1)
    except Exception:  # noqa: BLE001 - retrieval falls back to keyword ranking
        log.exception("Embedding failed for %s", doc_id)

    # Visual pages: anything with a figure, or no text layer at all.
    with store.connect() as conn:
        visual = [int(r["page_no"]) for r in conn.execute(
            "SELECT page_no FROM pages WHERE doc_id = ? AND (figures_json != '[]' OR source = 'none') "
            "ORDER BY page_no", (doc_id,))]
    if visual and settings.nvidia_api_key:
        _set(doc_id, visual_pages_total=len(visual))
        try:
            embeddings.embed_page_images(doc_id, visual,
                                         progress=lambda n: _set(doc_id, visual_pages_done=n))
        except Exception:  # noqa: BLE001
            log.exception("Image embedding failed for %s", doc_id)
        _set(doc_id, visual_pages_done=len(visual))

    if not ocr_targets:
        return
    done = 0
    lock = threading.Lock()
    recognized: list[int] = []

    def work(page_no: int) -> None:
        nonlocal done
        try:
            result = _ocr_page(pdf_file, page_no)
            if result is not None:
                with store.connect() as conn:
                    page = store.load_page(conn, doc_id, page_no)
                    if page is not None:
                        page["lines"] = result["lines"]
                        page["text"] = result["text"]
                        page["source"] = "ocr"
                        store.upsert_page(conn, doc_id, page)
                with lock:
                    recognized.append(page_no)
        except Exception:  # noqa: BLE001
            log.exception("OCR failed for %s page %s", doc_id, page_no)
        with lock:
            done += 1
            current = done
        _set(doc_id, ocr_pages_done=current)

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(work, ocr_targets))
    if recognized:
        try:
            embeddings.embed_document(doc_id, only_pages=recognized)
        except Exception:  # noqa: BLE001
            log.exception("Re-embedding OCR pages failed for %s", doc_id)


def start_indexing(doc_id: str) -> None:
    threading.Thread(target=index_document, args=(doc_id,), daemon=True,
                     name=f"index-{doc_id}").start()


def backfill() -> None:
    """Give documents indexed by an older version their missing embeddings."""
    with store.connect() as conn:
        ids = [r["id"] for r in conn.execute(
            "SELECT id FROM documents d WHERE status = 'ready' AND (embedded = 0 OR NOT EXISTS "
            "(SELECT 1 FROM image_embeddings i WHERE i.doc_id = d.id)) ORDER BY opened_at DESC")]
    for doc_id in ids:
        if store.pdf_path(doc_id).exists():
            threading.Thread(target=enrich_document, args=(doc_id,), daemon=True,
                             name=f"enrich-{doc_id}").start()
