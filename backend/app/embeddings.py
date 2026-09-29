"""Page embeddings for semantic retrieval, stored as float32 blobs.

Primary: NVIDIA `llama-nemotron-embed-vl-1b-v2` (fast, generous free tier:
~50 pages in 2-3 s). Fallback: Gemini embeddings. Vectors are L2-normalized
so cosine similarity is a dot product. Everything here is optional: without
embeddings, retrieval uses keyword and figure-caption ranking.

A document's pages and its queries must use the same model, so the model
name is stored per vector and queries are embedded with that model.
"""

from __future__ import annotations

import logging
import math
import os
import time
from array import array

import httpx

from . import store
from .config import get_settings

log = logging.getLogger(__name__)

NVIDIA_MODEL = os.environ.get("PINPOINT_NVIDIA_EMBED_MODEL", "nvidia/llama-nemotron-embed-vl-1b-v2")
NVIDIA_URL = "https://integrate.api.nvidia.com/v1/embeddings"
MAX_CHARS = 6000


def _normalize(values) -> array:
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return array("f", (v / norm for v in values))


def _nvidia(texts: list[str], query: bool, images: bool = False) -> list[array]:
    """Embed texts, or (images=True) PNG data URLs, with the NVIDIA VL model."""
    key = get_settings().nvidia_api_key
    if not key:
        raise RuntimeError("NVIDIA_API_KEY is not set")
    out: list[array] = []
    batch = 8 if images else 50
    for start in range(0, len(texts), batch):
        chunk = texts[start:start + batch] if images else [t[:MAX_CHARS] or " " for t in texts[start:start + batch]]
        body = {"model": NVIDIA_MODEL, "input": chunk, "input_type": "query" if query else "passage",
                "encoding_format": "float", "truncate": "END"}
        if images:
            body["modality"] = ["image"] * len(chunk)
        for attempt in range(5):
            resp = httpx.post(NVIDIA_URL, headers={"Authorization": f"Bearer {key}"}, json=body, timeout=90)
            if resp.status_code == 200:
                break
            if attempt == 4 or resp.status_code not in (429, 500, 502, 503, 504, 529):
                raise RuntimeError(f"NVIDIA embeddings HTTP {resp.status_code}: {resp.text[:200]}")
            time.sleep(3 * (attempt + 1))
        data = sorted(resp.json()["data"], key=lambda d: d["index"])
        out.extend(_normalize(d["embedding"]) for d in data)
    return out


def _gemini(texts: list[str], query: bool) -> list[array]:
    from google import genai
    from google.genai import types

    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    client = genai.Client(api_key=settings.gemini_api_key)
    out: list[array] = []
    # Small batches: the free tier limits tokens per minute.
    for start in range(0, len(texts), 20):
        chunk = [t[:2500] or " " for t in texts[start:start + 20]]
        for attempt in range(6):
            try:
                resp = client.models.embed_content(
                    model=settings.embedding_model, contents=chunk,
                    config=types.EmbedContentConfig(
                        task_type="RETRIEVAL_QUERY" if query else "RETRIEVAL_DOCUMENT",
                        output_dimensionality=settings.embedding_dims),
                )
                break
            except Exception:  # noqa: BLE001 - quota/transient; back off
                if attempt == 5:
                    raise
                time.sleep(10 * (attempt + 1))
        out.extend(_normalize(e.values) for e in resp.embeddings)
    return out


def _embed(texts: list[str], query: bool, model: str | None = None) -> tuple[list[array], str]:
    settings = get_settings()
    order = [model] if model else (
        [NVIDIA_MODEL] if settings.nvidia_api_key else []) + [settings.embedding_model]
    last: Exception | None = None
    for name in order:
        try:
            if name == NVIDIA_MODEL:
                return _nvidia(texts, query), name
            return _gemini(texts, query), name
        except Exception as exc:  # noqa: BLE001
            log.warning("embedding with %s failed: %s", name, exc)
            last = exc
    raise RuntimeError(f"No embedding provider worked: {last}")


def embed_document(doc_id: str, only_pages: list[int] | None = None) -> None:
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT page_no, text FROM pages WHERE doc_id = ? AND source != 'none' ORDER BY page_no",
            (doc_id,),
        ).fetchall()
        existing = conn.execute(
            "SELECT model FROM embeddings WHERE doc_id = ? LIMIT 1", (doc_id,)).fetchone()
    if only_pages is not None:
        wanted = set(only_pages)
        rows = [r for r in rows if r["page_no"] in wanted]
    if not rows:
        return
    started = time.monotonic()
    vectors, model = _embed([r["text"] for r in rows], query=False,
                            model=existing["model"] if existing and only_pages else None)
    with store.connect() as conn:
        for row, vec in zip(rows, vectors):
            conn.execute(
                "INSERT OR REPLACE INTO embeddings (doc_id, page_no, model, vec) VALUES (?, ?, ?, ?)",
                (doc_id, row["page_no"], model, vec.tobytes()),
            )
    log.info("embedded %d pages of %s with %s in %.1fs", len(rows), doc_id, model,
             time.monotonic() - started)


def embed_page_images(doc_id: str, page_nos: list[int], progress=None) -> None:
    """Embed rendered page images (diagrams, photos, scans) for visual retrieval."""
    import base64

    from .indexer import render_page_png

    if not get_settings().nvidia_api_key:
        return
    pdf_file = store.pdf_path(doc_id)
    done = 0
    for start in range(0, len(page_nos), 8):
        chunk = page_nos[start:start + 8]
        urls = ["data:image/png;base64," + base64.b64encode(
            render_page_png(pdf_file, p, max_side=768)).decode() for p in chunk]
        vectors = _nvidia(urls, query=False, images=True)
        with store.connect() as conn:
            for p, vec in zip(chunk, vectors):
                conn.execute(
                    "INSERT OR REPLACE INTO image_embeddings (doc_id, page_no, model, vec) "
                    "VALUES (?, ?, ?, ?)", (doc_id, p, NVIDIA_MODEL, vec.tobytes()))
        done += len(chunk)
        if progress:
            progress(done)


def load_vectors(conn, doc_id: str, table: str = "embeddings") -> tuple[dict[int, array], str | None]:
    out: dict[int, array] = {}
    model = None
    for row in conn.execute(f"SELECT page_no, model, vec FROM {table} WHERE doc_id = ?", (doc_id,)):
        vec = array("f")
        vec.frombytes(row["vec"])
        out[row["page_no"]] = vec
        model = row["model"]
    return out, model


def embed_query(question: str, model: str) -> array | None:
    try:
        return _embed([question], query=True, model=model)[0][0]
    except Exception:  # noqa: BLE001
        return None
