# Task 5: API Preflight & Model Integration Verification

## Goal
Verify the Gemini API connection works, the model can process images and return valid geometry, and the search pipeline produces real results.

## Context
The app uses `gemma-4-31b-it` through the Gemini API (via `google-genai` SDK). The free tier sends page images to Google for processing. The backend provider is in `backend/app/providers/gemma.py`.

The preflight script is at `app_tools/preflight.py`. It should verify:
1. GEMINI_API_KEY is present
2. The model is accessible
3. Image input works
4. The model returns valid geometry (bounding boxes)
5. Two-image input works (for evidence checking)

## Steps

### 1. Check the existing preflight script

Read `app_tools/preflight.py`. If it's incomplete or just a stub, write a proper one:

```python
"""Preflight check for Gemini API access and model capability.

Verifies:
1. GEMINI_API_KEY is set (without printing it)
2. The selected model accepts image input
3. The model returns valid bounding box geometry
4. Two-image input works (for evidence checking)
5. Response validates against the application schema
6. Timeout and error behavior is documented
"""

import sys
import os
import json
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.config import get_settings
from app.providers.gemma import (
    _build_client, _generate_text, validate_inspect, _parse_check_verdict
)

def main():
    settings = get_settings()
    results = {}
    
    # 1. Key present
    results["key_present"] = settings.key_present
    if not settings.key_present:
        print("FAIL: GEMINI_API_KEY not set")
        return 1
    print("PASS: API key present")
    
    # 2. Model accessible
    print(f"Model: {settings.model}")
    client = _build_client(settings)
    
    # 3. Simple image test — create a 100x100 red square
    from PIL import Image
    import io
    img = Image.new("RGB", (100, 100), (255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img_bytes = buf.getvalue()
    
    try:
        text, usage = _generate_text(
            client, settings,
            "What color is this image? Reply with one word.",
            [(img_bytes, "image/png")]
        )
        results["simple_image"] = True
        print(f"PASS: Simple image request succeeded: {text.strip()[:50]}")
    except Exception as e:
        results["simple_image"] = False
        print(f"FAIL: Simple image request failed: {e}")
        return 1
    
    # 4. Geometry test — create image with a known red rectangle
    geo_img = Image.new("RGB", (1000, 1000), (255, 255, 255))
    from PIL import ImageDraw
    d = ImageDraw.Draw(geo_img)
    d.rectangle([200, 300, 600, 700], fill=(255, 0, 0))
    d.text((250, 480), "TARGET ZONE", fill=(0, 0, 0))
    buf = io.BytesIO()
    geo_img.save(buf, format="PNG")
    geo_bytes = buf.getvalue()
    
    locate_prompt = (
        "Locate visible source evidence relevant to the user's question in this image.\n"
        "Question: Where is the red rectangle?\n\n"
        "Respond with exactly one JSON object:\n"
        '{"status": "found", "kind": "diagram", "boxes_2d": [[ymin,xmin,ymax,xmax]], "scope": "region"}\n'
        "Boxes use integers in [0,1000] relative to this image."
    )
    try:
        text, usage = _generate_text(
            client, settings, locate_prompt,
            [(geo_bytes, "image/png")]
        )
        parsed = validate_inspect(json.loads(text.strip().strip("`").removeprefix("json").strip()))
        results["geometry"] = True
        print(f"PASS: Geometry test succeeded: {json.dumps(parsed)}")
    except Exception as e:
        results["geometry"] = False
        print(f"WARN: Geometry test failed: {e}")
        # Try with fence stripping
        try:
            from app.providers.gemma import _strip_fences
            cleaned = _strip_fences(text)
            parsed = validate_inspect(json.loads(cleaned))
            results["geometry"] = True
            print(f"PASS: Geometry test succeeded after fence strip: {json.dumps(parsed)}")
        except Exception as e2:
            print(f"FAIL: Geometry test failed even after fence strip: {e2}")
    
    # 5. Two-image test
    crop_img = Image.new("RGB", (400, 400), (255, 0, 0))
    buf = io.BytesIO()
    crop_img.save(buf, format="PNG")
    crop_bytes = buf.getvalue()
    
    check_prompt = (
        "Does this crop show a red rectangle relevant to the question?\n"
        "Question: Where is the red rectangle?\n"
        "Reply with one word: accepted | rejected | uncertain"
    )
    try:
        text, usage = _generate_text(
            client, settings, check_prompt,
            [(geo_bytes, "image/png"), (crop_bytes, "image/png")]
        )
        verdict = _parse_check_verdict(text)
        results["two_image"] = True
        results["check_mode"] = "full-page-plus-crop"
        print(f"PASS: Two-image check succeeded: {verdict}")
    except Exception as e:
        results["two_image"] = False
        results["check_mode"] = "single-image"
        print(f"WARN: Two-image check failed (will use single-image mode): {e}")
    
    # Write results
    out_dir = PROJECT_ROOT / "out" / "preflight"
    out_dir.mkdir(parents=True, exist_ok=True)
    results["model"] = settings.model
    results["timestamp"] = time.time()
    with open(out_dir / "report.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\nPreflight report saved to {out_dir / 'report.json'}")
    passed = results.get("key_present") and results.get("simple_image")
    return 0 if passed else 1

if __name__ == "__main__":
    sys.exit(main())
```

### 2. Run the preflight

```
cd backend && .venv/Scripts/python.exe ../app_tools/preflight.py
```

### 3. If preflight passes, test a real search

Start the dev server, upload one of the generated fixture pages, and ask a question:
```
curl -X POST http://127.0.0.1:8000/api/uploads -F "file=@fixtures/generated/test_pages.pdf"
# Note the upload_id, then:
curl -X POST http://127.0.0.1:8000/api/documents -H "Content-Type: application/json" -d '{"upload_id": "UPLOAD_ID", "pages": [1,2,3]}'
# Note the document_id, then:
curl -X POST http://127.0.0.1:8000/api/searches -H "Content-Type: application/json" -d '{"question": "Where are the compact housing dimensions?", "document_ids": ["DOC_ID"]}'
# Check the search result
```

### 4. If the API key is not set or the model is unavailable

The preflight will fail gracefully. Document the failure in `out/preflight/report.json`. The app still works for upload/view — just search requires the API key. This is expected and acceptable.

If `gemma-4-31b-it` is unavailable, try `gemma-4-26b-a4b-it` as the documented fallback:
- Update `.env`: `EVIDENCE_MODEL=gemma-4-26b-a4b-it`
- Re-run preflight

## Success Criteria
- `app_tools/preflight.py` runs and produces `out/preflight/report.json`
- API key presence is verified without printing the key
- If API is accessible: at least simple image and geometry tests pass
- If API is not accessible: failure is documented clearly, not hidden
- Check mode (two-image vs single-image) is recorded
