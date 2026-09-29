"""Nemotron Parse 2.0 provider for document parsing.

Sends a page image to the NVIDIA NIM endpoint and extracts text elements
with bounding boxes and semantic classes in one pass.  The model uses an
OpenAI-compatible chat completions API and returns markdown annotated with
``<bbox>ymin,xmin,ymax,xmax</bbox>`` coordinates on the 0-1000 scale.

The single public entry point is ``parse_page``, which returns a list of
element dicts ready for the app coordinate system ([x0,y0,x1,y1] in 0-1).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"
_MODEL_ID = "nvidia/nemotron-parse-2.0"

# Regex for <bbox>ymin,xmin,ymax,xmax</bbox> tags in the model output.
_BBOX_RE = re.compile(
    r"<bbox>\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,"
    r"\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*</bbox>"
)

# ---------------------------------------------------------------------------
# Semantic-class heuristic: infer from surrounding markdown structure.
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^#{1,6}\s+")
_TABLE_RE = re.compile(r"\|.*\|")
_LIST_RE = re.compile(r"^(\s*[-*+]|\s*\d+\.)\s+")


def _infer_semantic_class(text: str) -> str:
    """Return a best-effort semantic class for *text*."""
    stripped = text.strip()
    if not stripped:
        return "paragraph"
    if _HEADING_RE.match(stripped):
        return "heading"
    if _TABLE_RE.search(stripped):
        return "table"
    if _LIST_RE.match(stripped):
        return "list"
    # "figure" and "chart" are hard to detect from text alone; callers can
    # refine later if the model output carries explicit class annotations.
    return "paragraph"


# ---------------------------------------------------------------------------
# Coordinate conversion
# ---------------------------------------------------------------------------

def _provider_box_to_app(ymin: float, xmin: float, ymax: float, xmax: float) -> list[float]:
    """Convert provider [ymin,xmin,ymax,xmax] in 0-1000 to app
    [x0,y0,x1,y1] in 0-1.  Returns the box, or raises ValueError."""
    for v in (ymin, xmin, ymax, xmax):
        if v < 0 or v > 1000:
            raise ValueError(f"coordinate {v} outside [0, 1000]")
    if not (ymin < ymax and xmin < xmax):
        raise ValueError("degenerate box (zero area)")
    return [xmin / 1000.0, ymin / 1000.0, xmax / 1000.0, ymax / 1000.0]


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

def _parse_response(content: str) -> list[dict]:
    """Extract elements from the model's markdown+bbox response.

    Each ``<bbox>`` tag is associated with the text that immediately
    precedes it (up to the previous ``</bbox>`` or start of string).
    """
    elements: list[dict] = []

    # Split on <bbox>...</bbox> to pair text chunks with their boxes.
    parts = _BBOX_RE.split(content)

    # parts layout: [text0, y0, x0, y1, x1, text1, y0, x0, y1, x1, ...]
    # Every 5 items after the first text is one (ymin, xmin, ymax, xmax) group.
    idx = 0
    while idx < len(parts):
        text_chunk = parts[idx].strip()
        idx += 1

        if idx + 3 < len(parts):
            try:
                ymin = float(parts[idx])
                xmin = float(parts[idx + 1])
                ymax = float(parts[idx + 2])
                xmax = float(parts[idx + 3])
                idx += 4
            except (ValueError, IndexError):
                continue

            # Clean the text: strip residual markdown fences and bbox tags.
            clean_text = re.sub(r"</bbox>", "", text_chunk).strip()
            # Remove trailing markdown line noise.
            clean_text = clean_text.strip("-").strip()

            if not clean_text:
                continue

            try:
                bbox = _provider_box_to_app(ymin, xmin, ymax, xmax)
            except ValueError as exc:
                logger.debug("Skipping bad bbox: %s", exc)
                continue

            elements.append({
                "text": clean_text,
                "bbox": bbox,
                "semantic_class": _infer_semantic_class(clean_text),
            })

    return elements


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_page(image_path: Path, settings) -> list[dict]:
    """Parse a single page image with Nemotron Parse 2.0.

    Parameters
    ----------
    image_path:
        Path to a PNG (or JPEG) page image on disk.
    settings:
        App settings object (only used for timeout; the API key comes
        from the ``NVIDIA_API_KEY`` environment variable).

    Returns
    -------
    list[dict]
        Each dict has ``text`` (str), ``bbox`` ([x0,y0,x1,y1] normalised
        0-1), and ``semantic_class`` (str).  Returns an empty list on any
        failure.
    """
    api_key = os.environ.get("NVIDIA_API_KEY", "")
    if not api_key:
        logger.error("NVIDIA_API_KEY not set; cannot call Nemotron Parse 2.0")
        return []

    # Read and base64-encode the page image.
    try:
        raw = Path(image_path).read_bytes()
    except OSError as exc:
        logger.error("Failed to read image %s: %s", image_path, exc)
        return []

    b64 = base64.b64encode(raw).decode("ascii")

    # Detect MIME type from file extension.
    suffix = Path(image_path).suffix.lower()
    mime = "image/png" if suffix in (".png",) else "image/jpeg"

    timeout_s = int(getattr(settings, "provider_timeout_seconds", 60))

    payload = {
        "model": _MODEL_ID,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime};base64,{b64}",
                        },
                    }
                ],
            }
        ],
        "max_tokens": 4096,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=timeout_s) as client:
            resp = client.post(_ENDPOINT, headers=headers, json=payload)
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Nemotron API returned %s: %s",
            exc.response.status_code,
            exc.response.text[:500],
        )
        return []
    except httpx.HTTPError as exc:
        logger.error("Nemotron API request failed: %s", exc)
        return []

    # Parse the chat completion response.
    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except (json.JSONDecodeError, KeyError, IndexError) as exc:
        logger.error("Unexpected Nemotron response structure: %s", exc)
        return []

    elements = _parse_response(content)
    logger.info(
        "Nemotron Parse 2.0: extracted %d elements from %s",
        len(elements),
        image_path,
    )
    return elements


# ---------------------------------------------------------------------------
# Local PDF text extraction fallback (no API needed)
# ---------------------------------------------------------------------------

def parse_pdf_page_local(pdf_data: bytes, page_index: int) -> list[dict]:
    """Extract text blocks with bounding boxes directly from PDF data.

    Uses PyMuPDF to get text blocks with positions. No external API needed.
    Returns the same format as parse_page: list of {text, bbox, semantic_class}.
    """
    try:
        import pymupdf
    except ImportError:
        logger.warning("PyMuPDF not installed; local PDF parsing unavailable")
        return []

    try:
        doc = pymupdf.open(stream=pdf_data, filetype="pdf")
    except Exception as exc:
        logger.error("Failed to open PDF: %s", exc)
        return []

    if page_index >= len(doc):
        doc.close()
        return []

    page = doc[page_index]
    pw, ph = page.rect.width, page.rect.height
    if pw <= 0 or ph <= 0:
        doc.close()
        return []

    elements: list[dict] = []
    blocks = page.get_text("blocks")
    for block in blocks:
        x0_pt, y0_pt, x1_pt, y1_pt, text, block_no, block_type = block
        if block_type != 0:
            continue
        text = text.strip()
        if not text:
            continue
        nx0 = max(0.0, min(1.0, x0_pt / pw))
        ny0 = max(0.0, min(1.0, y0_pt / ph))
        nx1 = max(0.0, min(1.0, x1_pt / pw))
        ny1 = max(0.0, min(1.0, y1_pt / ph))
        if nx1 <= nx0 or ny1 <= ny0:
            continue
        elements.append({
            "text": text,
            "bbox": [nx0, ny0, nx1, ny1],
            "semantic_class": _infer_semantic_class(text),
        })

    doc.close()
    logger.info("Local PDF parse: extracted %d elements from page %d", len(elements), page_index)
    return elements
