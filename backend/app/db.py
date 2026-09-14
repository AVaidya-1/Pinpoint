"""SQLite storage for the P0 import/viewer slice.

Tables: documents, pages, jobs. Versioned with an explicit schema version row.
All SQL is parameterized; foreign keys are enforced per connection.
"""

import json
import sqlite3
import time
import uuid
from pathlib import Path

from .config import get_settings

SCHEMA_VERSION = 1


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def db_path_for(data_dir: Path | None = None) -> Path:
    base = data_dir if data_dir is not None else get_settings().data_dir
    return base / "evidence.db"


def init_db(data_dir: Path | None = None) -> Path:
    """Create schema if needed and mark jobs left running by a previous
    process as interrupted. Returns the database path."""
    db_path = db_path_for(data_dir)
    conn = _connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_version "
            "(version INTEGER PRIMARY KEY, created_at REAL NOT NULL)"
        )
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO schema_version (version, created_at) VALUES (?, ?)",
                (SCHEMA_VERSION, time.time()),
            )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS documents ("
            "id TEXT PRIMARY KEY, original_filename TEXT NOT NULL, "
            "sha256 TEXT NOT NULL, mime_type TEXT NOT NULL, "
            "original_path TEXT NOT NULL, original_page_count INTEGER NOT NULL, "
            "selected_pages_json TEXT NOT NULL, status TEXT NOT NULL, "
            "error_code TEXT, created_at REAL NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS pages ("
            "id TEXT PRIMARY KEY, document_id TEXT NOT NULL, "
            "physical_page_number INTEGER NOT NULL, "
            "canonical_path TEXT NOT NULL, model_image_path TEXT NOT NULL, "
            "width_px INTEGER NOT NULL, height_px INTEGER NOT NULL, "
            "raster_sha256 TEXT NOT NULL, "
            "FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS jobs ("
            "id TEXT PRIMARY KEY, kind TEXT NOT NULL, state TEXT NOT NULL, "
            "completed_units INTEGER NOT NULL DEFAULT 0, "
            "total_units INTEGER NOT NULL DEFAULT 0, "
            "error_code TEXT, cancel_requested INTEGER NOT NULL DEFAULT 0, "
            "created_at REAL NOT NULL, updated_at REAL NOT NULL)"
        )
        # A restart must not pretend background work survived: previously
        # active jobs become interrupted.
        conn.execute(
            "UPDATE jobs SET state = 'interrupted', updated_at = ? "
            "WHERE state IN ('queued', 'running')",
            (time.time(),),
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def get_connection(data_dir: Path | None = None) -> sqlite3.Connection:
    db_path = db_path_for(data_dir)
    if not db_path.exists():
        init_db(data_dir)
    return _connect(db_path)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def selected_pages_of(doc_row: dict) -> list[int]:
    return json.loads(doc_row["selected_pages_json"])
