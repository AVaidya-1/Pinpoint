import sqlite3
import threading
from contextlib import contextmanager

from app.config import DB_PATH

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    original_filename TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    original_path TEXT NOT NULL,
    original_page_count INTEGER,
    selected_pages_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'importing',
    error_code TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pages (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    physical_page_number INTEGER NOT NULL,
    canonical_path TEXT NOT NULL,
    model_image_path TEXT NOT NULL,
    width_px INTEGER NOT NULL,
    height_px INTEGER NOT NULL,
    raster_sha256 TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'queued',
    completed_units INTEGER NOT NULL DEFAULT 0,
    total_units INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS searches (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id),
    question TEXT NOT NULL,
    page_snapshot_json TEXT NOT NULL DEFAULT '[]',
    model_id TEXT NOT NULL,
    prompt_version TEXT NOT NULL DEFAULT 'v1',
    outcome TEXT,
    checked_pages INTEGER NOT NULL DEFAULT 0,
    total_pages INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS page_checks (
    id TEXT PRIMARY KEY,
    cache_key TEXT NOT NULL,
    page_id TEXT NOT NULL REFERENCES pages(id),
    search_id TEXT NOT NULL REFERENCES searches(id),
    stage TEXT NOT NULL,
    model_id TEXT NOT NULL,
    validated_response_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    search_id TEXT NOT NULL REFERENCES searches(id),
    page_id TEXT NOT NULL REFERENCES pages(id),
    kind TEXT,
    boxes_json TEXT NOT NULL DEFAULT '[]',
    scope TEXT,
    check_status TEXT NOT NULL DEFAULT 'accepted'
);

CREATE INDEX IF NOT EXISTS idx_pages_document ON pages(document_id);
CREATE INDEX IF NOT EXISTS idx_evidence_search ON evidence(search_id);
CREATE INDEX IF NOT EXISTS idx_page_checks_cache ON page_checks(cache_key);
"""


def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return _local.conn


def init_db() -> None:
    conn = _get_conn()
    conn.executescript(SCHEMA)
    conn.commit()


@contextmanager
def get_db():
    conn = _get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def mark_interrupted_jobs() -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE jobs SET state='interrupted', updated_at=datetime('now') "
            "WHERE state IN ('queued','running')"
        )
