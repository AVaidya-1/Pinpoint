"""FastAPI application for the P0 import/viewer slice."""

import json
import re
import time
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from . import db
from .config import get_settings
from .ingestion import (
    UploadRejected,
    pdf_page_count,
    render_canonical,
    save_canonical_and_model,
    sha256_bytes,
    validate_upload,
)
from .jobs import create_job, set_job_state
from .schemas import (
    CapacityInfo,
    CoverageInfo,
    DocumentCommit,
    DocumentEnqueued,
    DocumentInfo,
    DocumentListResponse,
    EvidenceItem,
    HealthResponse,
    JobResponse,
    PageInfo,
    SearchCreated,
    SearchRequest,
    SearchResponse,
    UploadResponse,
)

app = FastAPI(title="Visual Evidence (P0 slice)")


def _data_dir() -> Path:
    d = get_settings().data_dir
    d.mkdir(parents=True, exist_ok=True)
    return d


def _uploads_dir() -> Path:
    p = _data_dir() / "uploads"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _sanitize_filename(name: str) -> str:
    base = Path(name).name or "upload.bin"
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    return safe[:120] or "upload.bin"


def _sidecar_path(upload_id: str) -> Path:
    return _uploads_dir() / f"{upload_id}.json"


def _upload_bytes_path(upload_id: str) -> Path:
    return _uploads_dir() / f"{upload_id}.bin"


def _read_sidecar(upload_id: str) -> dict:
    path = _sidecar_path(upload_id)
    if not re.fullmatch(r"[A-Za-z0-9-]+", upload_id) or not path.exists():
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Unknown upload ID"})
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _total_pages(conn) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM pages").fetchone()
    return int(row["n"])


def _document_count(conn) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM documents").fetchone()
    return int(row["n"])


def _doc_info(conn, doc: dict) -> DocumentInfo:
    pages = conn.execute(
        "SELECT id, physical_page_number FROM pages WHERE document_id = ? "
        "ORDER BY physical_page_number",
        (doc["id"],),
    ).fetchall()
    return DocumentInfo(
        id=doc["id"],
        filename=doc["original_filename"],
        mime_type=doc["mime_type"],
        status=doc["status"],
        page_count=len(pages),
        pages=[PageInfo(id=r["id"], physical_page_number=r["physical_page_number"]) for r in pages],
        original_path=doc["original_path"],
    )


@app.on_event("startup")
def _startup() -> None:
    db.init_db(_data_dir())


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    try:
        db.init_db(settings.data_dir)
        db_ok = True
    except Exception:
        db_ok = False
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        model=settings.model,
        key_present=settings.key_present,
        db_ok=db_ok,
    )


@app.post("/api/uploads", response_model=UploadResponse, status_code=201)
async def create_upload(file: UploadFile = File(...)) -> UploadResponse:
    data = await file.read()
    filename = file.filename or "upload.bin"
    try:
        kind, mime = validate_upload(filename, data)
    except UploadRejected as e:
        if e.code == "too_large":
            raise HTTPException(status_code=413, detail={"code": e.code, "message": e.message})
        raise HTTPException(status_code=415, detail={"code": e.code, "message": e.message})
    digest = sha256_bytes(data)
    if kind == "pdf":
        try:
            page_count = pdf_page_count(data)
        except Exception:
            raise HTTPException(
                status_code=422,
                detail={"code": "malformed_pdf", "message": "Could not parse PDF pages"},
            )
    else:
        page_count = 1
    upload_id = db.new_id("upload")
    _upload_bytes_path(upload_id).write_bytes(data)
    sidecar = {
        "upload_id": upload_id,
        "filename": filename,
        "mime_type": mime,
        "kind": kind,
        "sha256": digest,
        "size_bytes": len(data),
        "page_count": page_count,
    }
    with open(_sidecar_path(upload_id), "w", encoding="utf-8") as f:
        json.dump(sidecar, f)
    return UploadResponse(
        upload_id=upload_id,
        filename=filename,
        mime_type=mime,
        page_count=page_count,
        sha256=digest,
        size_bytes=len(data),
    )


@app.post("/api/documents", response_model=DocumentEnqueued, status_code=202)
def commit_document(body: DocumentCommit) -> DocumentEnqueued:
    meta = _read_sidecar(body.upload_id)
    requested = sorted(set(body.pages))
    if not requested:
        raise HTTPException(status_code=422, detail={"code": "empty_selection", "message": "No pages selected"})
    if any(p < 1 or p > meta["page_count"] for p in requested):
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_page_range", "message": "Selected pages are outside the document"},
        )
    settings = get_settings()
    conn = db.get_connection(settings.data_dir)
    try:
        busy = conn.execute(
            "SELECT COUNT(*) AS n FROM jobs WHERE state IN ('queued', 'running')"
        ).fetchone()
        if int(busy["n"]) > 0:
            raise HTTPException(status_code=409, detail={"code": "busy", "message": "Another job is active"})
        total = _total_pages(conn)
        if total + len(requested) > settings.max_pages:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "capacity_exceeded",
                    "message": "Workspace page capacity exceeded",
                    "capacity": {
                        "total_pages": total,
                        "requested": len(requested),
                        "max_pages": settings.max_pages,
                        "remaining": settings.max_pages - total,
                    },
                },
            )
        if _document_count(conn) >= settings.max_documents:
            raise HTTPException(
                status_code=409,
                detail={"code": "too_many_documents", "message": "Workspace document limit reached"},
            )
        data = _upload_bytes_path(body.upload_id).read_bytes()
        if sha256_bytes(data) != meta["sha256"]:
            raise HTTPException(status_code=422, detail={"code": "upload_changed", "message": "Upload changed"})
        doc_id = db.new_id("doc")
        original_name = _sanitize_filename(meta["filename"])
        original_rel = f"data/originals/{doc_id}/{original_name}"
        original_abs = settings.data_dir / "originals" / doc_id / original_name
        original_abs.parent.mkdir(parents=True, exist_ok=True)
        # Persist the original byte-for-byte.
        original_abs.write_bytes(data)
        now = time.time()
        conn.execute(
            "INSERT INTO documents (id, original_filename, sha256, mime_type, "
            "original_path, original_page_count, selected_pages_json, status, "
            "error_code, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                doc_id,
                meta["filename"],
                meta["sha256"],
                meta["mime_type"],
                original_rel,
                meta["page_count"],
                json.dumps(requested),
                "importing",
                None,
                now,
            ),
        )
        conn.commit()
        job_id = create_job(conn, "import", len(requested))
        set_job_state(conn, job_id, "running", 0)
        try:
            for i, physical in enumerate(requested):
                img = render_canonical(meta["kind"], data, physical - 1)
                page_id = db.new_id("page")
                page_dir = settings.data_dir / "pages" / page_id
                canonical_abs, model_abs, raster_hash = save_canonical_and_model(img, page_dir)
                conn.execute(
                    "INSERT INTO pages (id, document_id, physical_page_number, "
                    "canonical_path, model_image_path, width_px, height_px, "
                    "raster_sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        page_id,
                        doc_id,
                        physical,
                        f"data/pages/{page_id}/canonical.png",
                        f"data/pages/{page_id}/model.png",
                        img.size[0],
                        img.size[1],
                        raster_hash,
                    ),
                )
                set_job_state(conn, job_id, "running", i + 1)
            conn.execute("UPDATE documents SET status = 'ready' WHERE id = ?", (doc_id,))
            set_job_state(conn, job_id, "completed", len(requested))
            conn.commit()
        except Exception as e:
            conn.execute("UPDATE documents SET status = 'failed', error_code = ? WHERE id = ?",
                         ("import_failed", doc_id))
            set_job_state(conn, job_id, "failed", error_code="import_failed")
            conn.commit()
            raise HTTPException(
                status_code=422,
                detail={"code": "import_failed", "message": f"Import failed: {e}"},
            )
        return DocumentEnqueued(document_id=doc_id, job_id=job_id, status="ready")
    finally:
        conn.close()


@app.get("/api/documents", response_model=DocumentListResponse)
def list_documents() -> DocumentListResponse:
    settings = get_settings()
    conn = db.get_connection(settings.data_dir)
    try:
        docs = conn.execute("SELECT * FROM documents ORDER BY created_at").fetchall()
        infos = [_doc_info(conn, dict(r)) for r in docs]
        total = _total_pages(conn)
        capacity = CapacityInfo(
            total_pages=total,
            max_pages=settings.max_pages,
            remaining=settings.max_pages - total,
            document_count=len(infos),
            max_documents=settings.max_documents,
        )
        return DocumentListResponse(documents=infos, capacity=capacity)
    finally:
        conn.close()


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str) -> JSONResponse:
    settings = get_settings()
    conn = db.get_connection(settings.data_dir)
    try:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if doc is None:
            raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Unknown document"})
        busy = conn.execute(
            "SELECT COUNT(*) AS n FROM jobs WHERE state IN ('queued', 'running')"
        ).fetchone()
        if int(busy["n"]) > 0:
            raise HTTPException(status_code=409, detail={"code": "busy", "message": "A job is active"})
        pages = conn.execute("SELECT * FROM pages WHERE document_id = ?", (doc_id,)).fetchall()
        page_ids = [p["id"] for p in pages]
        # Invalidate searches that referenced this document: remove their
        # evidence and search records so old results cannot reopen removed
        # pages. Page-level rows cascade via foreign keys.
        if page_ids:
            for srow in conn.execute("SELECT id, page_snapshot_json FROM searches").fetchall():
                try:
                    snap = json.loads(srow["page_snapshot_json"])
                except (ValueError, TypeError):
                    continue
                snap_ids = {p.get("page_id") for p in snap if isinstance(p, dict)}
                if snap_ids & set(page_ids):
                    conn.execute("DELETE FROM evidence WHERE search_id = ?", (srow["id"],))
                    conn.execute("DELETE FROM searches WHERE id = ?", (srow["id"],))
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        conn.commit()
        # Remove associated local files; stale result links cannot resolve
        # afterwards because rows (and their page IDs) are gone.
        import shutil

        for base in (settings.data_dir / "originals" / doc_id,):
            shutil.rmtree(base, ignore_errors=True)
        for p in pages:
            shutil.rmtree(settings.data_dir / "pages" / p["id"], ignore_errors=True)
        return JSONResponse({"deleted": doc_id})
    finally:
        conn.close()


@app.get("/api/pages/{page_id}/image")
def page_image(page_id: str) -> FileResponse:
    if not re.fullmatch(r"[A-Za-z0-9-]+", page_id):
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Unknown page"})
    settings = get_settings()
    conn = db.get_connection(settings.data_dir)
    try:
        row = conn.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Unknown page"})
        path = settings.data_dir / "pages" / page_id / "canonical.png"
        if not path.exists():
            raise HTTPException(status_code=404, detail={"code": "missing_raster", "message": "Raster missing"})
        return FileResponse(str(path), media_type="image/png")
    finally:
        conn.close()


@app.get("/api/documents/{doc_id}/original")
def document_original(doc_id: str) -> FileResponse:
    if not re.fullmatch(r"[A-Za-z0-9-]+", doc_id):
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Unknown document"})
    settings = get_settings()
    conn = db.get_connection(settings.data_dir)
    try:
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Unknown document"})
        # Resolve strictly under the application data directory by ID.
        original_dir = settings.data_dir / "originals" / doc_id
        candidates = list(original_dir.glob("*")) if original_dir.exists() else []
        if not candidates:
            raise HTTPException(status_code=404, detail={"code": "missing_original", "message": "Original missing"})
        return FileResponse(
            str(candidates[0]),
            media_type=row["mime_type"],
            filename=row["original_filename"],
        )
    finally:
        conn.close()


def _search_pages_snapshot(conn, document_ids: list[str]) -> list[dict]:
    """Ready pages in document order then physical page order."""
    pages: list[dict] = []
    for doc_id in document_ids:
        rows = conn.execute(
            "SELECT * FROM pages WHERE document_id = ? ORDER BY physical_page_number",
            (doc_id,),
        ).fetchall()
        for r in rows:
            pages.append(
                {
                    "page_id": r["id"],
                    "document_id": doc_id,
                    "raster_sha256": r["raster_sha256"],
                }
            )
    return pages


def _job_response(conn, job_id: str) -> JobResponse:
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Unknown job"})
    return JobResponse(
        id=row["id"],
        kind=row["kind"],
        state=row["state"],
        completed_units=int(row["completed_units"]),
        total_units=int(row["total_units"]),
        error_code=row["error_code"],
        cancel_requested=bool(row["cancel_requested"]),
    )


def _search_response(conn, search_id: str) -> SearchResponse:
    srow = conn.execute("SELECT * FROM searches WHERE id = ?", (search_id,)).fetchone()
    if srow is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Unknown search"})
    jrow = conn.execute("SELECT * FROM jobs WHERE id = ?", (srow["job_id"],)).fetchone()
    state = jrow["state"] if jrow else "unknown"
    ev_rows = conn.execute(
        "SELECT e.*, p.physical_page_number, p.document_id, d.original_filename "
        "FROM evidence e JOIN pages p ON p.id = e.page_id "
        "JOIN documents d ON d.id = p.document_id "
        "WHERE e.search_id = ? ORDER BY p.document_id, p.physical_page_number",
        (search_id,),
    ).fetchall()
    items = [
        EvidenceItem(
            id=r["id"],
            document_id=r["document_id"],
            filename=r["original_filename"],
            page_id=r["page_id"],
            physical_page_number=int(r["physical_page_number"]),
            kind=r["kind"],
            scope=r["scope"],
            boxes=json.loads(r["boxes_json"]),
            image_url=f"/api/pages/{r['page_id']}/image",
        )
        for r in ev_rows
    ]
    errors: list[dict] = []
    if jrow and jrow["error_code"]:
        errors.append({"code": jrow["error_code"]})
    return SearchResponse(
        id=srow["id"],
        state=state,
        outcome=srow["outcome"],
        coverage=CoverageInfo(
            checked_pages=int(srow["checked_pages"]), total_pages=int(srow["total_pages"])
        ),
        evidence=items,
        model_id=srow["model_id"],
        errors=errors,
    )


@app.post("/api/searches", response_model=SearchCreated, status_code=202)
def create_search(body: SearchRequest) -> SearchCreated:
    from . import search as search_engine

    question = (body.question or "").strip()
    if not question:
        raise HTTPException(status_code=422, detail={"code": "empty_question", "message": "Question is empty"})
    if len(question) > 1000:
        raise HTTPException(
            status_code=422,
            detail={"code": "question_too_long", "message": "Question exceeds 1000 characters"},
        )
    if not body.document_ids:
        raise HTTPException(
            status_code=422, detail={"code": "no_documents", "message": "No documents selected"}
        )
    settings = get_settings()
    conn = db.get_connection(settings.data_dir)
    try:
        ready_total = conn.execute(
            "SELECT COUNT(*) AS n FROM documents WHERE status = 'ready'"
        ).fetchone()
        if int(ready_total["n"]) == 0:
            raise HTTPException(
                status_code=422,
                detail={"code": "no_ready_documents", "message": "No ready documents in the workspace"},
            )
        for doc_id in body.document_ids:
            drow = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
            if drow is None:
                raise HTTPException(
                    status_code=404, detail={"code": "not_found", "message": f"Unknown document: {doc_id}"}
                )
            if drow["status"] != "ready":
                raise HTTPException(
                    status_code=422,
                    detail={"code": "document_not_ready", "message": f"Document not ready: {doc_id}"},
                )
        busy = conn.execute(
            "SELECT COUNT(*) AS n FROM jobs WHERE state IN ('queued', 'running')"
        ).fetchone()
        if int(busy["n"]) > 0:
            raise HTTPException(status_code=409, detail={"code": "busy", "message": "Another job is active"})
        if not settings.key_present:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "missing_key",
                    "message": "Add a Gemini API key to the backend environment, then restart.",
                },
            )
        snapshot = _search_pages_snapshot(conn, body.document_ids)
        if not snapshot:
            raise HTTPException(
                status_code=422,
                detail={"code": "no_pages", "message": "Selected documents have no pages"},
            )
        job_id = create_job(conn, "search", len(snapshot))
        search_id = db.new_id("search")
        import time as _time

        conn.execute(
            "INSERT INTO searches (id, job_id, question, page_snapshot_json, model_id, "
            "prompt_version, outcome, checked_pages, total_pages, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                search_id,
                job_id,
                question,
                json.dumps(snapshot),
                settings.model,
                db.PROMPT_VERSION,
                "incomplete",
                0,
                len(snapshot),
                _time.time(),
            ),
        )
        conn.commit()
        # Resolve absolute raster paths for the engine.
        pages = []
        for entry in snapshot:
            prow = conn.execute("SELECT * FROM pages WHERE id = ?", (entry["page_id"],)).fetchone()
            data_dir = settings.data_dir
            pages.append(
                {
                    "page_id": entry["page_id"],
                    "document_id": entry["document_id"],
                    "raster_sha256": entry["raster_sha256"],
                    "canonical_path": str(data_dir / "pages" / entry["page_id"] / "canonical.png"),
                    "model_image_path": str(data_dir / "pages" / entry["page_id"] / "model.png"),
                }
            )
            _ = prow
        if body.force_refresh:
            conn.execute(
                "DELETE FROM page_checks WHERE page_id IN "
                "(SELECT value FROM json_each(?))",
                (json.dumps([p["page_id"] for p in pages]),),
            )
            conn.commit()
        try:
            search_engine.run_search(
                conn, settings, search_id=search_id, job_id=job_id,
                question=question, pages=pages,
            )
        except HTTPException:
            raise
        except Exception as e:
            set_job_state(conn, job_id, "failed", error_code="search_failed")
            raise HTTPException(
                status_code=500,
                detail={"code": "search_failed", "message": f"Search failed: {e}"},
            )
        return SearchCreated(search_id=search_id, job_id=job_id)
    finally:
        conn.close()


@app.get("/api/searches")
def list_searches() -> dict:
    settings = get_settings()
    conn = db.get_connection(settings.data_dir)
    try:
        rows = conn.execute("SELECT * FROM searches ORDER BY created_at DESC LIMIT 50").fetchall()
        return {
            "searches": [
                {
                    "id": r["id"],
                    "job_id": r["job_id"],
                    "question": r["question"],
                    "outcome": r["outcome"],
                    "checked_pages": int(r["checked_pages"]),
                    "total_pages": int(r["total_pages"]),
                    "model_id": r["model_id"],
                }
                for r in rows
            ]
        }
    finally:
        conn.close()


@app.get("/api/searches/{search_id}", response_model=SearchResponse)
def get_search(search_id: str) -> SearchResponse:
    settings = get_settings()
    conn = db.get_connection(settings.data_dir)
    try:
        return _search_response(conn, search_id)
    finally:
        conn.close()


@app.get("/api/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str) -> JobResponse:
    settings = get_settings()
    conn = db.get_connection(settings.data_dir)
    try:
        return _job_response(conn, job_id)
    finally:
        conn.close()


@app.post("/api/jobs/{job_id}/cancel", response_model=JobResponse)
def cancel_job(job_id: str) -> JobResponse:
    import time as _time

    settings = get_settings()
    conn = db.get_connection(settings.data_dir)
    try:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Unknown job"})
        conn.execute(
            "UPDATE jobs SET cancel_requested = 1, updated_at = ? WHERE id = ?",
            (_time.time(), job_id),
        )
        conn.commit()
        return _job_response(conn, job_id)
    finally:
        conn.close()
