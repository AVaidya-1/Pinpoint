"""SQLite storage: documents, per-page text layout, a full-text index,
page embeddings and the chat history of each document."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    page_count INTEGER NOT NULL,
    status TEXT NOT NULL,              -- indexing | ready | error
    indexed_pages INTEGER NOT NULL DEFAULT 0,
    ocr_pages_total INTEGER NOT NULL DEFAULT 0,
    ocr_pages_done INTEGER NOT NULL DEFAULT 0,
    embedded INTEGER NOT NULL DEFAULT 0,
    visual_pages_total INTEGER NOT NULL DEFAULT 0,
    visual_pages_done INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at REAL NOT NULL,
    opened_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_documents_sha ON documents(sha256);
CREATE TABLE IF NOT EXISTS pages (
    doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_no INTEGER NOT NULL,
    width REAL NOT NULL,
    height REAL NOT NULL,
    text TEXT NOT NULL,
    lines_json TEXT NOT NULL,
    figures_json TEXT NOT NULL,
    source TEXT NOT NULL,               -- text | ocr | none
    PRIMARY KEY (doc_id, page_no)
);
CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
    text, doc_id UNINDEXED, page_no UNINDEXED, tokenize = 'porter unicode61'
);
-- Figure captions and the labels printed inside figures, so questions about
-- diagrams can find the page that draws them.
CREATE VIRTUAL TABLE IF NOT EXISTS figures_fts USING fts5(
    text, doc_id UNINDEXED, page_no UNINDEXED, tokenize = 'porter unicode61'
);
CREATE TABLE IF NOT EXISTS embeddings (
    doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_no INTEGER NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    vec BLOB NOT NULL,
    PRIMARY KEY (doc_id, page_no)
);
-- Page images embedded with a vision-language model: finds diagrams and
-- photos by what they show, even when they carry no text.
CREATE TABLE IF NOT EXISTS image_embeddings (
    doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_no INTEGER NOT NULL,
    model TEXT NOT NULL,
    vec BLOB NOT NULL,
    PRIMARY KEY (doc_id, page_no)
);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    role TEXT NOT NULL,                 -- user | assistant
    content TEXT NOT NULL,
    citations_json TEXT NOT NULL DEFAULT '[]',
    meta_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_doc ON messages(doc_id, created_at);
"""


def db_path() -> Path:
    return get_settings().data_dir / "pinpoint.db"


def originals_dir() -> Path:
    p = get_settings().data_dir / "pdfs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def pdf_path(doc_id: str) -> Path:
    return originals_dir() / f"{doc_id}.pdf"


def init() -> None:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(embeddings)")}
        if "model" not in cols:
            conn.execute("ALTER TABLE embeddings ADD COLUMN model TEXT NOT NULL DEFAULT ''")
        doc_cols = {r[1] for r in conn.execute("PRAGMA table_info(documents)")}
        for col in ("visual_pages_total", "visual_pages_done"):
            if col not in doc_cols:
                conn.execute(f"ALTER TABLE documents ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0")
        if conn.execute("SELECT count(*) FROM figures_fts").fetchone()[0] == 0:
            for doc_id, page_no, figs in conn.execute(
                    "SELECT doc_id, page_no, figures_json FROM pages").fetchall():
                _index_figures(conn, doc_id, page_no, json.loads(figs))
        # Indexing threads do not survive a restart.
        conn.execute(
            "UPDATE documents SET status = 'error', error = 'Indexing was interrupted; re-upload the PDF.' "
            "WHERE status = 'indexing'"
        )
        conn.commit()
    finally:
        conn.close()


@contextmanager
def connect():
    conn = sqlite3.connect(db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def document_json(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "filename": row["filename"],
        "page_count": row["page_count"],
        "status": row["status"],
        "indexed_pages": row["indexed_pages"],
        "ocr_pages_total": row["ocr_pages_total"],
        "ocr_pages_done": row["ocr_pages_done"],
        "embedded": bool(row["embedded"]),
        "visual_pages_total": row["visual_pages_total"],
        "visual_pages_done": row["visual_pages_done"],
        "error": row["error"],
    }


def get_document(conn, doc_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()


def upsert_page(conn, doc_id: str, page: dict) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO pages (doc_id, page_no, width, height, text, lines_json, "
        "figures_json, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (doc_id, page["page_no"], page["width"], page["height"], page["text"],
         json.dumps(page["lines"]), json.dumps(page["figures"]), page["source"]),
    )
    conn.execute("DELETE FROM pages_fts WHERE doc_id = ? AND page_no = ?", (doc_id, page["page_no"]))
    if page["text"].strip():
        conn.execute(
            "INSERT INTO pages_fts (text, doc_id, page_no) VALUES (?, ?, ?)",
            (page["text"], doc_id, page["page_no"]),
        )
    _index_figures(conn, doc_id, page["page_no"], page["figures"])


def _figure_text(fig: dict) -> str:
    return " ".join([fig.get("caption") or ""] + list(fig.get("labels") or [])).strip()


def _index_figures(conn, doc_id: str, page_no: int, figures: list[dict]) -> None:
    conn.execute("DELETE FROM figures_fts WHERE doc_id = ? AND page_no = ?", (doc_id, page_no))
    text = "\n".join(t for t in (_figure_text(f) for f in figures) if t)
    if text:
        conn.execute("INSERT INTO figures_fts (text, doc_id, page_no) VALUES (?, ?, ?)",
                     (text, doc_id, page_no))


def load_page(conn, doc_id: str, page_no: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM pages WHERE doc_id = ? AND page_no = ?", (doc_id, page_no)
    ).fetchone()
    if row is None:
        return None
    return {
        "page_no": row["page_no"],
        "width": row["width"],
        "height": row["height"],
        "text": row["text"],
        "lines": json.loads(row["lines_json"]),
        "figures": json.loads(row["figures_json"]),
        "source": row["source"],
    }


def add_message(conn, doc_id: str, role: str, content: str,
                citations: list | None = None, meta: dict | None = None) -> dict:
    mid = new_id("msg")
    now = time.time()
    conn.execute(
        "INSERT INTO messages (id, doc_id, role, content, citations_json, meta_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (mid, doc_id, role, content, json.dumps(citations or []), json.dumps(meta or {}), now),
    )
    return {"id": mid, "role": role, "content": content,
            "citations": citations or [], "meta": meta or {}, "created_at": now}


def list_messages(conn, doc_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM messages WHERE doc_id = ? ORDER BY created_at", (doc_id,)
    ).fetchall()
    return [
        {"id": r["id"], "role": r["role"], "content": r["content"],
         "citations": json.loads(r["citations_json"]), "meta": json.loads(r["meta_json"]),
         "created_at": r["created_at"]}
        for r in rows
    ]
