"""Gemma provider for page inspection and evidence checking.

Uses the official ``google-genai`` SDK against the Gemini API with the
``gemma-4-31b-it`` model (or the documented ``gemma-4-26b-a4b-it`` fallback
selected before a run, never switched silently mid-search).

No web search, tool execution, URL fetching, code execution or grounding
tools are used inside inference. Model output is never eval'd; only an
enclosing Markdown code fence is stripped before JSON parsing.
"""

from __future__ import annotations

import json
import math
import random
import threading
import time
from pathlib import Path

PROMPT_VERSION = "locate-v1/check-v1"

# Evidence-checking input mode. "full-page-plus-crop" when two-image input
# works (established by preflight); "single-image" if two-image input fails
# and the box-coordinate fallback is used. Recorded, never silent.
CHECK_MODE = "full-page-plus-crop"

_VALID_STATUS = {"found", "not_found", "uncertain"}
_VALID_KIND = {"text", "table", "diagram", "chart", "photo"}
_VALID_SCOPE = {"region", "page"}
_VALID_CHECK = {"accepted", "rejected", "uncertain"}

_pace_lock = threading.Lock()
_last_call_ts = 0.0


class ProviderError(Exception):
    """Structured provider failure with a stable code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def get_check_mode() -> str:
    return CHECK_MODE


def _prompts_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "prompts"


def load_prompt(name: str) -> str:
    return (_prompts_dir() / name).read_text(encoding="utf-8")


def _pace(settings) -> None:
    """Sleep-based pacer respecting settings.requests_per_minute."""
    global _last_call_ts
    rpm = max(1, int(getattr(settings, "requests_per_minute", 6)))
    min_gap = 60.0 / rpm
    with _pace_lock:
        now = time.monotonic()
        wait = min_gap - (now - _last_call_ts)
        if wait > 0:
            time.sleep(wait)
        _last_call_ts = time.monotonic()


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        # Drop opening fence (``` or ```json).
        lines = lines[1:]
        # Drop closing fence if present.
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, (TimeoutError,)):
        return True
    msg = f"{type(exc).__name__}: {exc}"
    for token in ("429", "500", "502", "503", "504", "timeout", "timed out",
                  "temporarily", "overloaded", "UNAVAILABLE", "DEADLINE"):
        if token.lower() in msg.lower():
            return True
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    try:
        if code is not None and int(code) in (429, 500, 502, 503, 504):
            return True
    except (TypeError, ValueError):
        pass
    return False


def _classify_fatal(exc: Exception) -> str:
    msg = f"{type(exc).__name__}: {exc}".lower()
    if "quota" in msg or "429" in msg or "resource_exhausted" in msg:
        return "quota"
    if "timeout" in msg or "timed out" in msg or "deadline" in msg:
        return "timeout"
    return "transport"


def validate_inspect(obj) -> dict:
    """Strictly validate a parsed locate response. Raises ValueError."""
    if not isinstance(obj, dict):
        raise ValueError("response must be a JSON object")
    allowed = {"status", "kind", "boxes_2d", "scope"}
    extra = set(obj.keys()) - allowed
    if extra:
        raise ValueError(f"extra fields not allowed: {sorted(extra)}")
    for key in ("status", "kind", "boxes_2d", "scope"):
        if key not in obj:
            raise ValueError(f"missing field: {key}")
    status = obj["status"]
    kind = obj["kind"]
    boxes = obj["boxes_2d"]
    scope = obj["scope"]
    if status not in _VALID_STATUS:
        raise ValueError(f"invalid status: {status!r}")
    if status in ("not_found", "uncertain"):
        if boxes != []:
            raise ValueError("boxes_2d must be empty for non-found responses")
        if kind is not None:
            raise ValueError("kind must be null for non-found responses")
        if scope is not None:
            raise ValueError("scope must be null for non-found responses")
        return {"status": status, "kind": None, "boxes_2d": [], "scope": None}
    # status == "found"
    if kind not in _VALID_KIND:
        raise ValueError(f"invalid kind: {kind!r}")
    if scope not in _VALID_SCOPE:
        raise ValueError(f"invalid scope: {scope!r}")
    if not isinstance(boxes, list) or not (1 <= len(boxes) <= 3):
        raise ValueError("found requires 1–3 boxes")
    norm_boxes: list[list[int]] = []
    for b in boxes:
        if not isinstance(b, (list, tuple)) or len(b) != 4:
            raise ValueError("each box must have exactly 4 numbers")
        vals = []
        for v in b:
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise ValueError("box coordinates must be numbers")
            if not math.isfinite(v):
                raise ValueError("box coordinates must be finite")
            if float(v) != int(float(v)):
                raise ValueError("box coordinates must be integers")
            iv = int(float(v))
            if iv < 0 or iv > 1000:
                raise ValueError("box coordinates must be within [0, 1000]")
            vals.append(iv)
        ymin, xmin, ymax, xmax = vals
        if not (ymin < ymax and xmin < xmax):
            raise ValueError("box must satisfy ymin<ymax and xmin<xmax (non-zero area)")
        norm_boxes.append(vals)
    return {"status": "found", "kind": kind, "boxes_2d": norm_boxes, "scope": scope}


def _parse_inspect_json(text: str) -> dict:
    cleaned = _strip_fences(text)
    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"response is not valid JSON: {e}") from e
    return validate_inspect(obj)


def _parse_check_verdict(text: str) -> str:
    verdict = _strip_fences(text).strip().lower()
    # Accept a single trailing period; nothing else.
    verdict = verdict.rstrip(".").strip()
    if verdict not in _VALID_CHECK:
        raise ValueError(f"invalid check verdict: {text!r}")
    return verdict


def _build_client(settings, client_override=None):
    if client_override is not None:
        return client_override
    api_key = getattr(settings, "gemini_api_key", "")
    if not api_key:
        raise ProviderError("missing_key",
                            "Add a Gemini API key to the backend environment, then restart.")
    try:
        from google import genai
    except ImportError as e:
        raise ProviderError("transport", f"google-genai SDK not installed: {e}") from e
    return genai.Client(api_key=api_key)


def _generate_text(client, settings, prompt_text: str, images: list[tuple[bytes, str]],
                   client_override=None) -> tuple[str, dict | None]:
    """Send one text+images request. Returns (response_text, token_usage).

    images: list of (raw_bytes, mime_type).
    """
    model_id = getattr(settings, "model", "gemma-4-31b-it")
    timeout_s = int(getattr(settings, "provider_timeout_seconds", 60))
    max_tokens = 512
    if client_override is not None and hasattr(client_override, "generate"):
        return client_override.generate(prompt_text, images), None
    from google.genai import types

    parts = [types.Part.from_text(text=prompt_text)]
    for raw, mime in images:
        parts.append(types.Part.from_bytes(data=raw, mime_type=mime))
    config = types.GenerateContentConfig(
        temperature=0.0,
        max_output_tokens=max_tokens,
        http_options=types.HttpOptions(timeout=timeout_s * 1000),
    )
    response = client.models.generate_content(
        model=model_id, contents=parts, config=config,
    )
    usage = None
    meta = getattr(response, "usage_metadata", None)
    if meta is not None:
        try:
            usage = {
                "prompt_token_count": getattr(meta, "prompt_token_count", None),
                "candidates_token_count": getattr(meta, "candidates_token_count", None),
                "total_token_count": getattr(meta, "total_token_count", None),
            }
        except Exception:
            usage = None
    return (response.text or ""), usage


def _call_with_retry(settings, fn, *, job_id=None, conn=None):
    """Run fn() with pacing, retries and usage recording."""
    _pace(settings)
    attempts = 0
    last_exc: Exception | None = None
    model_id = getattr(settings, "model", "gemma-4-31b-it")
    while attempts < 3:  # initial + at most two retries
        start = time.monotonic()
        try:
            result = fn()
            latency_ms = int((time.monotonic() - start) * 1000)
            if conn is not None:
                from . import db as _db

                _db.record_usage(conn, job_id, "gemini", model_id, "ok", latency_ms, None)
            return result
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001 - classified below
            latency_ms = int((time.monotonic() - start) * 1000)
            if not _is_transient(exc):
                if conn is not None:
                    from . import db as _db

                    _db.record_usage(conn, job_id, "gemini", model_id,
                                     _classify_fatal(exc), latency_ms, None)
                raise ProviderError(_classify_fatal(exc), str(exc)) from exc
            last_exc = exc
            attempts += 1
            if attempts >= 3:
                if conn is not None:
                    from . import db as _db

                    _db.record_usage(conn, job_id, "gemini", model_id,
                                     _classify_fatal(exc), latency_ms, None)
                raise ProviderError(_classify_fatal(exc),
                                    f"transient failure after retries: {exc}") from exc
            delay = (2.0 * attempts) + random.uniform(0, 1.0)
            time.sleep(delay)
    assert last_exc is not None
    raise ProviderError("transport", str(last_exc)) from last_exc


def inspect_page(question: str, page_image_path: Path, settings,
                 *, job_id=None, conn=None, client=None) -> dict:
    """Send the locate prompt + full page image; return validated JSON."""
    prompt_tpl = load_prompt("locate.txt")
    prompt = prompt_tpl.replace("{question}", question.strip())
    raw = Path(page_image_path).read_bytes()
    sdk_client = _build_client(settings, client)

    def _do() -> str:
        text, _usage = _generate_text(sdk_client, settings, prompt, [(raw, "image/png")],
                                      client_override=client)
        return text

    text = _call_with_retry(settings, _do, job_id=job_id, conn=conn)
    try:
        return _parse_inspect_json(text)
    except ValueError:
        # At most one schema-repair attempt, charged against the same budget.
        repair_prompt = (
            "Your previous output did not match the required schema. "
            "Return ONLY one JSON object with exactly the keys "
            "status, kind, boxes_2d, scope. status is found|not_found|uncertain; "
            "kind is text|table|diagram|chart|photo|null; scope is region|page|null; "
            "boxes_2d is [] unless status is found (then 1–3 [ymin,xmin,ymax,xmax] "
            "integer boxes in [0,1000]). No extra fields, no other text.\n\n"
            f"Question:\n{question.strip()}"
        )

        def _repair() -> str:
            fixed, _u = _generate_text(sdk_client, settings, repair_prompt,
                                       [(raw, "image/png")], client_override=client)
            return fixed

        try:
            fixed_text = _call_with_retry(settings, _repair, job_id=job_id, conn=conn)
        except ProviderError as e:
            raise ProviderError("malformed_response",
                                f"model output failed validation and repair failed: {e}") from e
        try:
            return _parse_inspect_json(fixed_text)
        except ValueError as e:
            raise ProviderError("malformed_response",
                                f"model output failed validation: {e}") from e


def check_evidence(question: str, page_image_path: Path, crop_image: bytes,
                   proposed_boxes: list, settings,
                   *, job_id=None, conn=None, client=None) -> str:
    """Check a proposed evidence group. Returns accepted|rejected|uncertain."""
    global CHECK_MODE
    prompt_tpl = load_prompt("check.txt")
    boxes_text = json.dumps(proposed_boxes)
    prompt = prompt_tpl.replace("{question}", question.strip()).replace("{boxes}", boxes_text)
    page_raw = Path(page_image_path).read_bytes()
    sdk_client = _build_client(settings, client)

    def _do_full() -> str:
        text, _u = _generate_text(sdk_client, settings, prompt,
                                  [(page_raw, "image/png"), (bytes(crop_image), "image/png")],
                                  client_override=client)
        return text

    try:
        text = _call_with_retry(settings, _do_full, job_id=job_id, conn=conn)
        CHECK_MODE = "full-page-plus-crop"
    except ProviderError as e:
        # Fall back to single-image checking with box coordinates overlaid
        # as text, and record the reduced mode.
        if "missing_key" in (e.code or "") or "quota" in (e.code or ""):
            raise
        reduced_prompt = prompt + (
            "\n\nNote: only the full page image is attached; the crop could not "
            "be sent. Judge from the page image and the proposed coordinates above."
        )

        def _do_reduced() -> str:
            rtext, _u = _generate_text(sdk_client, settings, reduced_prompt,
                                       [(page_raw, "image/png")],
                                       client_override=client)
            return rtext

        try:
            text = _call_with_retry(settings, _do_reduced, job_id=job_id, conn=conn)
        except ProviderError:
            raise
        CHECK_MODE = "single-image"
    try:
        return _parse_check_verdict(text)
    except ValueError as e:
        raise ProviderError("malformed_response",
                            f"check verdict failed validation: {e}") from e
