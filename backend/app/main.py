"""Pinpoint API: one PDF at a time, a chat per PDF, highlighted citations."""

from __future__ import annotations

import hashlib
import logging
import shutil
import tempfile
import time
from pathlib import Path

import pymupdf
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import answer, indexer, llm, store
from .config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("pinpoint")

app = FastAPI(title="Pinpoint")


@app.on_event("startup")
def _startup() -> None:
    store.init()
    indexer.backfill()


class AskBody(BaseModel):
    question: str


def _doc_or_404(conn, doc_id: str):
    row = store.get_document(conn, doc_id)
    if row is None:
        raise HTTPException(404, "Document not found.")
    return row


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "providers": [f"{p.name}:{p.model}" for p in llm.available_providers()]}


@app.get("/api/documents")
def recent_documents(limit: int = 15) -> dict:
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM documents WHERE status != 'error' ORDER BY opened_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return {"documents": [store.document_json(r) for r in rows]}


@app.post("/api/documents", status_code=201)
async def upload_document(file: UploadFile = File(...)) -> dict:
    settings = get_settings()
    limit = settings.max_upload_mb * 1024 * 1024 or float("inf")
    digest = hashlib.sha256()
    size = 0
    store.originals_dir()
    with tempfile.NamedTemporaryFile(dir=store.originals_dir(), suffix=".part", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                tmp.close()
                tmp_path.unlink(missing_ok=True)
                raise HTTPException(413, f"PDF is larger than {settings.max_upload_mb} MB.")
            digest.update(chunk)
            tmp.write(chunk)
    try:
        with open(tmp_path, "rb") as fh:
            if b"%PDF" not in fh.read(1024):
                raise ValueError("not a PDF")
        with pymupdf.open(tmp_path, filetype="pdf") as doc:
            page_count = doc.page_count
        if page_count == 0:
            raise ValueError("no pages")
    except Exception:  # noqa: BLE001
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(415, "That file isn't a readable PDF.")

    sha = digest.hexdigest()
    now = time.time()
    with store.connect() as conn:
        existing = conn.execute(
            "SELECT * FROM documents WHERE sha256 = ? AND status != 'error' "
            "ORDER BY created_at DESC LIMIT 1", (sha,),
        ).fetchone()
        if existing is not None:
            tmp_path.unlink(missing_ok=True)
            conn.execute("UPDATE documents SET opened_at = ? WHERE id = ?", (now, existing["id"]))
            return store.document_json(store.get_document(conn, existing["id"]))
        doc_id = store.new_id("doc")
        shutil.move(str(tmp_path), store.pdf_path(doc_id))
        name = Path(file.filename or "document.pdf").name[:200]
        conn.execute(
            "INSERT INTO documents (id, filename, sha256, page_count, status, created_at, opened_at) "
            "VALUES (?, ?, ?, ?, 'indexing', ?, ?)",
            (doc_id, name, sha, page_count, now, now),
        )
        row = store.get_document(conn, doc_id)
    indexer.start_indexing(doc_id)
    return store.document_json(row)


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: str) -> dict:
    with store.connect() as conn:
        return store.document_json(_doc_or_404(conn, doc_id))


@app.post("/api/documents/{doc_id}/open")
def open_document(doc_id: str) -> dict:
    with store.connect() as conn:
        _doc_or_404(conn, doc_id)
        conn.execute("UPDATE documents SET opened_at = ? WHERE id = ?", (time.time(), doc_id))
        return store.document_json(store.get_document(conn, doc_id))


@app.get("/api/documents/{doc_id}/file")
def document_file(doc_id: str) -> FileResponse:
    with store.connect() as conn:
        row = _doc_or_404(conn, doc_id)
    path = store.pdf_path(doc_id)
    if not path.exists():
        raise HTTPException(404, "PDF file is missing.")
    return FileResponse(path, media_type="application/pdf", filename=row["filename"],
                        content_disposition_type="inline")


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str) -> dict:
    with store.connect() as conn:
        _doc_or_404(conn, doc_id)
        conn.execute("DELETE FROM pages_fts WHERE doc_id = ?", (doc_id,))
        conn.execute("DELETE FROM figures_fts WHERE doc_id = ?", (doc_id,))
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    store.pdf_path(doc_id).unlink(missing_ok=True)
    return {"ok": True}


@app.get("/api/documents/{doc_id}/messages")
def messages(doc_id: str) -> dict:
    with store.connect() as conn:
        _doc_or_404(conn, doc_id)
        return {"messages": store.list_messages(conn, doc_id)}


@app.delete("/api/documents/{doc_id}/messages")
def clear_messages(doc_id: str) -> dict:
    with store.connect() as conn:
        _doc_or_404(conn, doc_id)
        conn.execute("DELETE FROM messages WHERE doc_id = ?", (doc_id,))
    return {"ok": True}


@app.post("/api/documents/{doc_id}/ask")
def ask(doc_id: str, body: AskBody) -> dict:
    question = body.question.strip()
    if not question:
        raise HTTPException(422, "Type a question first.")
    with store.connect() as conn:
        row = _doc_or_404(conn, doc_id)
    if row["status"] == "indexing":
        raise HTTPException(409, "Still reading this PDF. Try again in a few seconds.")
    if row["status"] == "error":
        raise HTTPException(409, row["error"] or "This PDF could not be indexed.")
    try:
        return answer.ask(doc_id, question[:2000])
    except llm.LLMError as exc:
        log.warning("ask failed: %s", exc)
        raise HTTPException(503, "The AI model is busy right now. Please try again in a moment.")


# Serve the built frontend from the same origin, so one server on one
# address runs the whole app (no dev proxy to fall over).
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _DIST.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")
