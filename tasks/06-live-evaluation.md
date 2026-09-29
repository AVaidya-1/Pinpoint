# Task 6: Live Model Evaluation

## Goal
Run the frozen holdout evaluation against the live model and produce a structured report. This tests whether the VLM can actually locate evidence in technical documentation with diagrams, tables, flowcharts, and raster-only pages.

## Context
The holdout suite is at `fixtures/holdout.json` with 20 questions:
- 4 text lookups
- 4 table/label-and-unit lookups
- 8 genuinely visual questions (flow direction, spatial relation, graphical branch, chart)
- 4 absent-answer questions (should produce no accepted evidence)

The evaluation script should be at `app_tools/evaluate.py`. The generated fixtures are in `fixtures/generated/` — they are deterministic PDFs with known target regions.

**This task requires a working GEMINI_API_KEY.** If the preflight (Task 5) failed due to API access, skip this task and document it.

## Steps

### 1. Write or complete `app_tools/evaluate.py`

The evaluator should:

1. Start the backend (or connect to a running instance)
2. Upload the generated fixture PDF (`fixtures/generated/test_pages.pdf`, 8 pages)
3. For each holdout question:
   a. Run the search via the API
   b. Compare returned evidence against expected page and region
   c. Score: correct page? sufficiently localized? (union of returned boxes covers ≥80% of expected region, occupies ≤3× expected area)
4. For absent-answer questions: verify no accepted evidence returned
5. Produce a structured JSON report

**Scoring (from spec Section 15B):**
- Correct source page for ≥14 of 16 answerable questions
- Sufficiently localized evidence for ≥12 of 16 answerable questions
- ≥6 of 8 visual questions pass localization
- ≥3 of 4 absent-answer questions produce no accepted evidence
- Report false-positive groups and total groups

**Localization metric:**
The union of returned boxes must cover ≥80% of required evidence pixels while occupying ≤3× the allowed evidence area. Use raster masks or geometry to compute union area. A whole-page box must not pass a small-target question.

### 2. Run evaluation

```
cd backend && .venv/Scripts/python.exe ../app_tools/evaluate.py --suite ../fixtures/holdout.json --live
```

### 3. Save results

Save to `out/evaluation/`:
- `report.json` — structured results with question ID, expected vs actual regions, status, timing, call count
- `summary.txt` — human-readable pass/fail summary against thresholds

### 4. Handle failures honestly

From the spec:
- Every live call failure is reported separately; it cannot be dropped from the denominator
- If execution is quota-blocked, mark the evaluation incomplete
- If quality misses thresholds, report "technical hypothesis not yet validated"
- Never replace real results with fixture answers to manufacture a pass

## Success Criteria
- `out/evaluation/report.json` exists with all 20 questions evaluated (or documented as incomplete)
- Summary reports counts against the fixed thresholds
- No fabricated results
- Visual questions are scored separately from text/table questions
- False positives are reported, not hidden

## Evaluation report format

```json
{
  "timestamp": "...",
  "model": "gemma-4-31b-it",
  "fixture": "fixtures/holdout.json",
  "status": "complete" | "incomplete",
  "thresholds": {
    "correct_page": {"required": 14, "actual": 0, "pass": false},
    "localized": {"required": 12, "actual": 0, "pass": false},
    "visual_localized": {"required": 6, "actual": 0, "pass": false},
    "absent_correct": {"required": 3, "actual": 0, "pass": false}
  },
  "questions": [
    {
      "id": "h01",
      "type": "text",
      "question": "...",
      "expected_page_sig": [128, 128, 0],
      "expected_region": [0.1, 0.1, 0.8, 0.3],
      "actual_page_correct": true,
      "actual_boxes": [[0.15, 0.12, 0.75, 0.28]],
      "localization_pass": true,
      "coverage_ratio": 0.85,
      "area_ratio": 1.2,
      "api_calls": 8,
      "latency_ms": 12000,
      "error": null
    }
  ],
  "totals": {
    "total_api_calls": 160,
    "total_latency_ms": 240000,
    "false_positive_groups": 0,
    "total_evidence_groups": 14
  }
}
```
