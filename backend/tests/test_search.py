"""Search/highlight slice tests with deterministic provider doubles.

No real API calls. Covers: inspect persistence, check verdicts, geometry
conversion, malformed-output rejection, outcome determination, cache hits,
cancellation and call budget.
"""

import io
import json
import time
from pathlib import Path

import pytest
from PIL import Image

from app import db
from app.config import get_settings
from app.jobs import create_job
from app.providers import gemma as provider
from app.search import (
    check_cache_key,
    determine_outcome,
    evidence_crop_bounds,
    inspect_cache_key,
    run_search,
)


def _png_bytes(color=(10, 120, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (120, 160), color).save(buf, format="PNG")
    return buf.getvalue()


def _seed(tmp_path, monkeypatch, n_pages: int = 2, max_calls: int = 60):
    monkeypatch.setenv("EVIDENCE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("EVIDENCE_MAX_CALLS_PER_SEARCH", str(max_calls))
    # A non-empty key keeps endpoint guards realistic; doubles never use it.
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    settings = get_settings()
    data_dir = settings.data_dir
    db.init_db(data_dir)
    conn = db.get_connection(data_dir)
    doc_id = db.new_id("doc")
    conn.execute(
        "INSERT INTO documents (id, original_filename, sha256, mime_type, "
        "original_path, original_page_count, selected_pages_json, status, "
        "error_code, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (doc_id, "seed.pdf", "abc", "application/pdf", "data/originals/x",
         n_pages, json.dumps(list(range(1, n_pages + 1))), "ready", None, time.time()),
    )
    pages = []
    for i in range(n_pages):
        page_id = db.new_id("page")
        page_dir = data_dir / "pages" / page_id
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "canonical.png").write_bytes(_png_bytes())
        (page_dir / "model.png").write_bytes(_png_bytes())
        conn.execute(
            "INSERT INTO pages (id, document_id, physical_page_number, "
            "canonical_path, model_image_path, width_px, height_px, "
            "raster_sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (page_id, doc_id, i + 1, f"data/pages/{page_id}/canonical.png",
             f"data/pages/{page_id}/model.png", 120, 160, f"hash-{i}"),
        )
        pages.append(
            {
                "page_id": page_id,
                "document_id": doc_id,
                "raster_sha256": f"hash-{i}",
                "canonical_path": str(page_dir / "canonical.png"),
                "model_image_path": str(page_dir / "model.png"),
            }
        )
    conn.commit()
    job_id = create_job(conn, "search", len(pages))
    search_id = db.new_id("search")
    conn.execute(
        "INSERT INTO searches (id, job_id, question, page_snapshot_json, model_id, "
        "prompt_version, outcome, checked_pages, total_pages, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (search_id, job_id, "Where is the latch?", json.dumps(
            [{"page_id": p["page_id"]} for p in pages]),
         settings.model, db.PROMPT_VERSION, "incomplete", 0, len(pages), time.time()),
    )
    conn.commit()
    return conn, settings, pages, search_id, job_id


def _close(conn):
    try:
        conn.close()
    except Exception:
        pass


FOUND = {"status": "found", "kind": "diagram",
         "boxes_2d": [[220, 150, 480, 670]], "scope": "region"}
NOT_FOUND = {"status": "not_found", "kind": None, "boxes_2d": [], "scope": None}
UNCERTAIN = {"status": "uncertain", "kind": None, "boxes_2d": [], "scope": None}


def _inspect(payload):
    def _fn(question, path, settings, **kwargs):
        assert question == "Where is the latch?"
        assert Path(str(path)).exists()
        return dict(payload)
    return _fn


def _check(verdict):
    def _fn(question, page_path, crop_bytes, boxes, settings, **kwargs):
        assert isinstance(crop_bytes, (bytes, bytearray)) and len(crop_bytes) > 0
        assert isinstance(boxes, list) and len(boxes) >= 1
        return verdict
    return _fn


def test_inspect_found_persists_check_and_evidence(tmp_path, monkeypatch):
    conn, settings, pages, search_id, job_id = _seed(tmp_path, monkeypatch, 1)
    try:
        summary = run_search(conn, settings, search_id=search_id, job_id=job_id,
                             question="Where is the latch?", pages=pages,
                             inspect_fn=_inspect(FOUND), check_fn=_check("accepted"))
        assert summary["outcome"] == "found"
        rows = conn.execute("SELECT * FROM page_checks").fetchall()
        stages = sorted(r["stage"] for r in rows)
        assert stages == ["check", "inspect"]
        ev = conn.execute("SELECT * FROM evidence").fetchall()
        assert len(ev) == 1
        # Geometry: provider [ymin,xmin,ymax,xmax] -> app [x0,y0,x1,y1].
        got = json.loads(ev[0]["boxes_json"])
        assert len(got) == 1 and len(got[0]) == 4
        assert got[0] == pytest.approx([0.15, 0.22, 0.67, 0.48])
        assert ev[0]["kind"] == "diagram"
        job = conn.execute("SELECT state FROM jobs WHERE id = ?", (job_id,)).fetchone()
        assert job["state"] == "completed"
    finally:
        _close(conn)


def test_check_rejected_gives_uncertain_without_evidence(tmp_path, monkeypatch):
    conn, settings, pages, search_id, job_id = _seed(tmp_path, monkeypatch, 1)
    try:
        summary = run_search(conn, settings, search_id=search_id, job_id=job_id,
                             question="Where is the latch?", pages=pages,
                             inspect_fn=_inspect(FOUND), check_fn=_check("rejected"))
        assert summary["outcome"] == "uncertain"
        assert conn.execute("SELECT COUNT(*) AS n FROM evidence").fetchone()["n"] == 0
    finally:
        _close(conn)


def test_check_uncertain_gives_uncertain(tmp_path, monkeypatch):
    conn, settings, pages, search_id, job_id = _seed(tmp_path, monkeypatch, 1)
    try:
        summary = run_search(conn, settings, search_id=search_id, job_id=job_id,
                             question="Where is the latch?", pages=pages,
                             inspect_fn=_inspect(FOUND), check_fn=_check("uncertain"))
        assert summary["outcome"] == "uncertain"
    finally:
        _close(conn)


def test_all_not_found_gives_no_evidence(tmp_path, monkeypatch):
    conn, settings, pages, search_id, job_id = _seed(tmp_path, monkeypatch, 2)
    try:
        summary = run_search(conn, settings, search_id=search_id, job_id=job_id,
                             question="Where is the latch?", pages=pages,
                             inspect_fn=_inspect(NOT_FOUND), check_fn=_check("accepted"))
        assert summary["outcome"] == "no_evidence"
        assert summary["checked_pages"] == 2
    finally:
        _close(conn)


def test_malformed_extra_fields_rejected(tmp_path, monkeypatch):
    bad = dict(FOUND)
    bad["answer"] = "The latch is on the left."  # injection attempt
    conn, settings, pages, search_id, job_id = _seed(tmp_path, monkeypatch, 1)
    try:
        with pytest.raises(Exception):
            provider.validate_inspect(bad)
        summary = run_search(conn, settings, search_id=search_id, job_id=job_id,
                             question="Where is the latch?", pages=pages,
                             inspect_fn=_inspect(bad), check_fn=_check("accepted"))
        assert summary["outcome"] == "incomplete"
        assert conn.execute("SELECT COUNT(*) AS n FROM evidence").fetchone()["n"] == 0
    finally:
        _close(conn)


def test_malformed_invalid_boxes_rejected(tmp_path, monkeypatch):
    bad = {"status": "found", "kind": "diagram",
           "boxes_2d": [[100, 100, 100, 200]], "scope": "region"}  # zero area
    conn, settings, pages, search_id, job_id = _seed(tmp_path, monkeypatch, 1)
    try:
        with pytest.raises(ValueError):
            provider.validate_inspect(bad)
        summary = run_search(conn, settings, search_id=search_id, job_id=job_id,
                             question="Where is the latch?", pages=pages,
                             inspect_fn=_inspect(bad), check_fn=_check("accepted"))
        assert summary["outcome"] == "incomplete"
    finally:
        _close(conn)


def test_outcome_determination_matrix():
    assert determine_outcome(accepted=2, saw_uncertain=False, failed_pages=0,
                             unchecked_pages=0, cancelled=False) == "found"
    assert determine_outcome(accepted=0, saw_uncertain=False, failed_pages=0,
                             unchecked_pages=0, cancelled=False) == "no_evidence"
    assert determine_outcome(accepted=0, saw_uncertain=True, failed_pages=0,
                             unchecked_pages=0, cancelled=False) == "uncertain"
    assert determine_outcome(accepted=0, saw_uncertain=False, failed_pages=1,
                             unchecked_pages=0, cancelled=False) == "incomplete"
    assert determine_outcome(accepted=1, saw_uncertain=False, failed_pages=0,
                             unchecked_pages=2, cancelled=False) == "incomplete"
    assert determine_outcome(accepted=0, saw_uncertain=False, failed_pages=0,
                             unchecked_pages=0, cancelled=True) == "incomplete"


def test_cache_hit_skips_provider_call(tmp_path, monkeypatch):
    conn, settings, pages, search_id, job_id = _seed(tmp_path, monkeypatch, 1)
    try:
        calls = {"n": 0}

        def counting_inspect(question, path, settings, **kwargs):
            calls["n"] += 1
            return dict(NOT_FOUND)

        first = run_search(conn, settings, search_id=search_id, job_id=job_id,
                           question="Where is the latch?", pages=pages,
                           inspect_fn=counting_inspect, check_fn=_check("accepted"))
        assert first["outcome"] == "no_evidence"
        assert calls["n"] == 1
        # Second identical search reuses the cached page_check.
        job2 = create_job(conn, "search", len(pages))
        search2 = db.new_id("search")
        conn.execute(
            "INSERT INTO searches (id, job_id, question, page_snapshot_json, model_id, "
            "prompt_version, outcome, checked_pages, total_pages, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (search2, job2, "Where is the latch?", "[]", settings.model,
             db.PROMPT_VERSION, "incomplete", 0, len(pages), time.time()),
        )
        conn.commit()
        second = run_search(conn, settings, search_id=search2, job_id=job2,
                            question="Where is the latch?", pages=pages,
                            inspect_fn=counting_inspect, check_fn=_check("accepted"))
        assert second["outcome"] == "no_evidence"
        assert calls["n"] == 1, "cached inspect must not call the provider again"
    finally:
        _close(conn)


def test_transport_failure_is_not_cached_as_negative(tmp_path, monkeypatch):
    conn, settings, pages, search_id, job_id = _seed(tmp_path, monkeypatch, 1)
    try:
        def failing(question, path, settings, **kwargs):
            raise RuntimeError("boom: 503 overloaded")

        summary = run_search(conn, settings, search_id=search_id, job_id=job_id,
                             question="Where is the latch?", pages=pages,
                             inspect_fn=failing, check_fn=_check("accepted"))
        assert summary["outcome"] == "incomplete"
        assert conn.execute("SELECT COUNT(*) AS n FROM page_checks").fetchone()["n"] == 0
    finally:
        _close(conn)


def test_cancel_stops_scheduling_new_pages(tmp_path, monkeypatch):
    conn, settings, pages, search_id, job_id = _seed(tmp_path, monkeypatch, 3)
    try:
        conn.execute("UPDATE jobs SET cancel_requested = 1 WHERE id = ?", (job_id,))
        conn.commit()
        calls = {"n": 0}

        def counting(question, path, settings, **kwargs):
            calls["n"] += 1
            return dict(NOT_FOUND)

        summary = run_search(conn, settings, search_id=search_id, job_id=job_id,
                             question="Where is the latch?", pages=pages,
                             inspect_fn=counting, check_fn=_check("accepted"))
        assert summary["cancelled"] is True
        assert summary["checked_pages"] == 0
        assert calls["n"] == 0
        assert summary["outcome"] == "incomplete"
    finally:
        _close(conn)


def test_budget_exhaustion_stops_incomplete(tmp_path, monkeypatch):
    conn, settings, pages, search_id, job_id = _seed(tmp_path, monkeypatch, 3, max_calls=1)
    try:
        summary = run_search(conn, settings, search_id=search_id, job_id=job_id,
                             question="Where is the latch?", pages=pages,
                             inspect_fn=_inspect(FOUND), check_fn=_check("accepted"))
        assert summary["calls_made"] <= 1
        assert summary["outcome"] == "incomplete"
        assert summary["checked_pages"] < 3
    finally:
        _close(conn)


def test_schema_v2_tables_exist(tmp_path, monkeypatch):
    monkeypatch.setenv("EVIDENCE_DATA_DIR", str(tmp_path / "data"))
    settings = get_settings()
    db.init_db(settings.data_dir)
    conn = db.get_connection(settings.data_dir)
    try:
        names = {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
        for t in ("documents", "pages", "jobs", "searches",
                  "page_checks", "evidence", "usage_events"):
            assert t in names
        ver = conn.execute("SELECT version FROM schema_version").fetchone()
        assert int(ver["version"]) == 2
    finally:
        _close(conn)


def test_crop_bounds_padding_and_clipping():
    bounds = evidence_crop_bounds([[0.15, 0.22, 0.67, 0.48]])
    assert bounds == pytest.approx([0.10, 0.17, 0.72, 0.53])
    edge = evidence_crop_bounds([[0.0, 0.0, 0.98, 0.99]])
    assert edge == pytest.approx([0.0, 0.0, 1.0, 1.0])


def test_cache_keys_cover_model_and_prompt(tmp_path, monkeypatch):
    k1 = inspect_cache_key("h", "q", "gemma-4-31b-it")
    k2 = inspect_cache_key("h", "q", "gemma-4-26b-a4b-it")
    assert k1 != k2
    c1 = check_cache_key("h", "q", "m", [[0.1, 0.1, 0.2, 0.2]], "crop1")
    c2 = check_cache_key("h", "q", "m", [[0.1, 0.1, 0.3, 0.3]], "crop1")
    assert c1 != c2


LIVE_STYLE_FOUND = (
    '{"status": "found", "kind": "text", '
    '"boxes_2d": [[300, 203, 601, 503]], "scope": "region"}'
)


def test_strip_fences_handles_gemma_markdown_wrapping():
    assert provider._strip_fences(
        "```json\n" + LIVE_STYLE_FOUND + "\n```") == LIVE_STYLE_FOUND
    assert provider._strip_fences(
        "```\n" + LIVE_STYLE_FOUND + "\n```") == LIVE_STYLE_FOUND
    # No fence passes through unchanged (apart from outer whitespace).
    assert provider._strip_fences("  " + LIVE_STYLE_FOUND + "  ") == LIVE_STYLE_FOUND
    # Missing closing fence still recovers the payload.
    assert provider._strip_fences("```json\n" + LIVE_STYLE_FOUND) == LIVE_STYLE_FOUND


def test_parse_inspect_handles_live_style_fenced_response():
    parsed = provider._parse_inspect_json("```json\n" + LIVE_STYLE_FOUND + "\n```")
    assert parsed == {"status": "found", "kind": "text",
                      "boxes_2d": [[300, 203, 601, 503]], "scope": "region"}


def test_live_style_response_flows_to_found_evidence(tmp_path, monkeypatch):
    """A double returning the exact validated shape of a live Gemma payload
    (as inspect_page would return after parsing) produces evidence."""
    live_parsed = provider._parse_inspect_json(
        "```json\n" + LIVE_STYLE_FOUND + "\n```")
    conn, settings, pages, search_id, job_id = _seed(tmp_path, monkeypatch, 1)
    try:
        summary = run_search(conn, settings, search_id=search_id, job_id=job_id,
                             question="Where is the latch?", pages=pages,
                             inspect_fn=_inspect(live_parsed), check_fn=_check("accepted"))
        assert summary["outcome"] == "found"
        ev = conn.execute("SELECT * FROM evidence").fetchall()
        assert len(ev) == 1
        assert json.loads(ev[0]["boxes_json"])[0] == pytest.approx([0.203, 0.3, 0.503, 0.601])
    finally:
        _close(conn)


def test_coordinate_conversion_matches_viewer_overlay():
    from app.geometry import provider_to_app, validate_app_box, app_to_viewbox

    # Live locate box [ymin,xmin,ymax,xmax] -> viewer overlay [x0,y0,x1,y1].
    app_box = provider_to_app([300, 203, 601, 503])
    assert app_box == pytest.approx([0.203, 0.3, 0.503, 0.601])
    validate_app_box(app_box)
    x, y, w, h = app_to_viewbox(app_box)
    assert (x, y, w, h) == pytest.approx((203.0, 300.0, 300.0, 301.0))
    assert w > 0 and h > 0
    # Full-page scope box maps to the whole overlay.
    assert provider_to_app([0, 0, 1000, 1000]) == pytest.approx([0.0, 0.0, 1.0, 1.0])
