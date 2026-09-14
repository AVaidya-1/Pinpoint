"""Bounded visual-scan search engine (PRODUCT_BRIEF.md sections 9–10).

For each page in document order then physical page order: inspect the full
page image, crop accepted-candidate regions with 5% padding, check the crop,
and persist only accepted groups as evidence. Source-only output: no answer
text, quotation, chain-of-thought or confidence is produced or stored.
"""

from __future__ import annotations

import hashlib
import io
import json
import time
from pathlib import Path

from . import db
from .geometry import provider_to_app, validate_app_box

GENERATION_SETTINGS = "temp0-max512"

OUTCOMES = ("found", "no_evidence", "uncertain", "incomplete")


def inspect_cache_key(raster_hash: str, question: str, model: str,
                      prompt_version: str = db.PROMPT_VERSION) -> str:
    return ":".join(["inspect", raster_hash, question, model,
                     GENERATION_SETTINGS, prompt_version])


def check_cache_key(raster_hash: str, question: str, model: str,
                    boxes_app: list, crop_hash: str,
                    prompt_version: str = db.PROMPT_VERSION) -> str:
    return ":".join(["check", raster_hash, question, model,
                     GENERATION_SETTINGS, prompt_version,
                     json.dumps(boxes_app, sort_keys=True), crop_hash])


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def evidence_crop_bounds(boxes_app: list[list[float]]) -> list[float]:
    """Union of app boxes with 5% page padding on each side, clipped to [0,1]."""
    for b in boxes_app:
        validate_app_box(b)
    x0 = min(b[0] for b in boxes_app) - 0.05
    y0 = min(b[1] for b in boxes_app) - 0.05
    x1 = max(b[2] for b in boxes_app) + 0.05
    y1 = max(b[3] for b in boxes_app) + 0.05
    return [max(0.0, x0), max(0.0, y0), min(1.0, x1), min(1.0, y1)]


def make_evidence_crop(canonical_path: Path | str,
                       boxes_app: list[list[float]]) -> tuple[bytes, list[float], str]:
    """Crop the canonical raster to the padded union bounds.

    Returns (crop_png_bytes, crop_bounds, crop_sha256).
    """
    from PIL import Image

    bounds = evidence_crop_bounds(boxes_app)
    img = Image.open(str(canonical_path)).convert("RGB")
    w, h = img.size
    left = int(bounds[0] * w)
    upper = int(bounds[1] * h)
    right = int(bounds[2] * w)
    lower = int(bounds[3] * h)
    right = max(right, left + 1)
    lower = max(lower, upper + 1)
    crop = img.crop((left, upper, min(right, w), min(lower, h)))
    buf = io.BytesIO()
    crop.save(buf, format="PNG")
    raw = buf.getvalue()
    return raw, bounds, _sha256_bytes(raw)


def determine_outcome(*, accepted: int, saw_uncertain: bool,
                      failed_pages: int, unchecked_pages: int,
                      cancelled: bool) -> str:
    if accepted > 0 and not cancelled and failed_pages == 0 and unchecked_pages == 0:
        return "found"
    if accepted > 0 and (cancelled or failed_pages > 0 or unchecked_pages > 0):
        # Partial scan with retained evidence is still reported honestly as
        # incomplete coverage; accepted groups are preserved on the search.
        return "incomplete"
    if cancelled or failed_pages > 0 or unchecked_pages > 0:
        return "incomplete"
    if saw_uncertain:
        return "uncertain"
    return "no_evidence"


def _cancel_requested(conn, job_id: str) -> bool:
    row = conn.execute("SELECT cancel_requested FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return bool(row and int(row["cancel_requested"]))


def _cached_check(conn, cache_key: str):
    return conn.execute(
        "SELECT validated_response_json FROM page_checks WHERE cache_key = ? "
        "ORDER BY created_at DESC LIMIT 1",
        (cache_key,),
    ).fetchone()


def _store_check(conn, cache_key: str, page_id: str, stage: str,
                 model_id: str, validated: dict | str) -> None:
    conn.execute(
        "INSERT INTO page_checks (id, cache_key, page_id, stage, model_id, "
        "validated_response_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (db.new_id("check"), cache_key, page_id, stage, model_id,
         json.dumps(validated), time.time()),
    )
    conn.commit()


def run_search(conn, settings, *, search_id: str, job_id: str, question: str,
               pages: list[dict], inspect_fn=None, check_fn=None) -> dict:
    """Execute the bounded scan synchronously. Returns a summary dict.

    pages: ordered list of dicts with keys page_id, raster_sha256,
    canonical_path, model_image_path. inspect_fn/check_fn are injectable
    doubles with the same signatures as the provider functions minus the
    trailing keyword args.
    """
    from .providers import gemma as _provider

    question = question.strip()
    model_id = settings.model
    prompt_version = db.PROMPT_VERSION
    inspect_fn = inspect_fn or _provider.inspect_page
    check_fn = check_fn or _provider.check_evidence

    total = len(pages)
    checked = 0
    calls_made = 0
    accepted = 0
    saw_uncertain = False
    failed_pages = 0
    budget = int(settings.max_calls_per_search)
    cancelled = False

    from .jobs import set_job_state

    set_job_state(conn, job_id, "running", 0)
    conn.execute(
        "UPDATE searches SET total_pages = ?, checked_pages = 0 WHERE id = ?",
        (total, search_id),
    )
    conn.commit()

    for page in pages:
        if _cancel_requested(conn, job_id):
            cancelled = True
            break
        if calls_made >= budget:
            break
        page_id = page["page_id"]
        raster_hash = page["raster_sha256"]
        key = inspect_cache_key(raster_hash, question, model_id)
        cached = _cached_check(conn, key)
        if cached is not None:
            inspect_res = json.loads(cached["validated_response_json"])
        else:
            if calls_made >= budget:
                break
            try:
                try:
                    inspect_res = inspect_fn(
                        question, Path(page["model_image_path"]), settings,
                        job_id=job_id, conn=None,
                    )
                except TypeError:
                    inspect_res = inspect_fn(question, Path(page["model_image_path"]), settings)
            except Exception:
                # Transport/quota/timeout failures are never cached as
                # negative evidence; they mark the page failed.
                failed_pages += 1
                _bump(conn, search_id, job_id, checked, total)
                continue
            calls_made += 1
            try:
                # Re-validate through the provider schema when a double
                # returns raw JSON (extra fields / injection attempts fail).
                inspect_res = _provider.validate_inspect(inspect_res)
            except (ValueError, AttributeError, TypeError):
                failed_pages += 1
                _bump(conn, search_id, job_id, checked, total)
                continue
            _store_check(conn, key, page_id, "inspect", model_id, inspect_res)

        status = inspect_res.get("status")
        if status == "uncertain":
            saw_uncertain = True
            checked += 1
            _bump(conn, search_id, job_id, checked, total)
            continue
        if status != "found":
            checked += 1
            _bump(conn, search_id, job_id, checked, total)
            continue

        # status == found: convert boxes once, then check.
        try:
            boxes_app = [provider_to_app(b) for b in inspect_res["boxes_2d"]]
        except (ValueError, KeyError, TypeError):
            failed_pages += 1
            _bump(conn, search_id, job_id, checked, total)
            continue
        try:
            crop_bytes, _bounds, crop_hash = make_evidence_crop(
                page["canonical_path"], boxes_app)
        except Exception:
            failed_pages += 1
            _bump(conn, search_id, job_id, checked, total)
            continue

        ckey = check_cache_key(raster_hash, question, model_id, boxes_app, crop_hash)
        cached_check = _cached_check(conn, ckey)
        if cached_check is not None:
            verdict = json.loads(cached_check["validated_response_json"])
            if isinstance(verdict, dict):
                verdict = verdict.get("verdict")
        else:
            if calls_made >= budget:
                break
            try:
                try:
                    verdict = check_fn(
                        question, Path(page["model_image_path"]), crop_bytes,
                        boxes_app, settings, job_id=job_id, conn=None,
                    )
                except TypeError:
                    verdict = check_fn(question, Path(page["model_image_path"]),
                                       crop_bytes, boxes_app, settings)
            except Exception:
                failed_pages += 1
                _bump(conn, search_id, job_id, checked, total)
                continue
            calls_made += 1
            if verdict not in ("accepted", "rejected", "uncertain"):
                failed_pages += 1
                _bump(conn, search_id, job_id, checked, total)
                continue
            _store_check(conn, ckey, page_id, "check", model_id, {"verdict": verdict})

        checked += 1
        if verdict == "accepted":
            accepted += 1
            conn.execute(
                "INSERT INTO evidence (id, search_id, page_id, kind, boxes_json, "
                "scope, check_status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (db.new_id("ev"), search_id, page_id,
                 inspect_res.get("kind", "diagram"),
                 json.dumps(boxes_app), inspect_res.get("scope", "region"),
                 "accepted"),
            )
            conn.commit()
        elif verdict in ("rejected", "uncertain"):
            saw_uncertain = True
        _bump(conn, search_id, job_id, checked, total)

    unchecked = total - checked
    if _cancel_requested(conn, job_id):
        cancelled = True
    outcome = determine_outcome(accepted=accepted, saw_uncertain=saw_uncertain,
                                failed_pages=failed_pages,
                                unchecked_pages=unchecked, cancelled=cancelled)
    conn.execute(
        "UPDATE searches SET outcome = ?, checked_pages = ? WHERE id = ?",
        (outcome, checked, search_id),
    )
    conn.commit()
    if cancelled:
        set_job_state(conn, job_id, "cancelled", checked)
    elif unchecked > 0 or failed_pages > 0:
        set_job_state(conn, job_id, "completed", checked,
                      error_code="incomplete_coverage")
    else:
        set_job_state(conn, job_id, "completed", checked)
    # Keep total_units accurate for polling UI.
    conn.execute("UPDATE jobs SET total_units = ? WHERE id = ?", (total, job_id))
    conn.commit()
    return {
        "outcome": outcome,
        "checked_pages": checked,
        "total_pages": total,
        "calls_made": calls_made,
        "accepted": accepted,
        "failed_pages": failed_pages,
        "cancelled": cancelled,
    }


def _bump(conn, search_id: str, job_id: str, checked: int, total: int) -> None:
    from .jobs import set_job_state

    conn.execute("UPDATE searches SET checked_pages = ? WHERE id = ?", (checked, search_id))
    conn.commit()
    set_job_state(conn, job_id, "running", checked)
    conn.execute("UPDATE jobs SET total_units = ? WHERE id = ?", (total, job_id))
    conn.commit()
