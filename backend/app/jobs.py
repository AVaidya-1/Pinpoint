"""Simple in-process job worker for imports (P0 slice).

Jobs are persisted in SQLite. The HTTP request creates the job record and the
import runs synchronously in-process; on restart, jobs left active are marked
interrupted by db.init_db.
"""

import time

from . import db


def create_job(conn, kind: str, total_units: int) -> str:
    job_id = db.new_id("job")
    now = time.time()
    conn.execute(
        "INSERT INTO jobs (id, kind, state, completed_units, total_units, "
        "cancel_requested, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (job_id, kind, "queued", 0, total_units, 0, now, now),
    )
    conn.commit()
    return job_id


def set_job_state(conn, job_id: str, state: str, completed: int | None = None,
                  error_code: str | None = None) -> None:
    if completed is None:
        conn.execute(
            "UPDATE jobs SET state = ?, error_code = ?, updated_at = ? WHERE id = ?",
            (state, error_code, time.time(), job_id),
        )
    else:
        conn.execute(
            "UPDATE jobs SET state = ?, completed_units = ?, error_code = ?, "
            "updated_at = ? WHERE id = ?",
            (state, completed, error_code, time.time(), job_id),
        )
    conn.commit()
