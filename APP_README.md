# Pinpoint

Open a PDF, ask a question in the chat on the left, and the PDF on the right scrolls to the answer and highlights it: the exact text lines, or the exact part of a diagram, schematic, table or photo.

## Run

Double-click **`Start Pinpoint.cmd`**. It builds the frontend, starts one server and opens **http://127.0.0.1:8000** (use `127.0.0.1`, not `localhost`). Close its window to stop.

For frontend development with hot reload, `backend\.venv\Scripts\python.exe app_tools\dev.py` still runs Vite on http://127.0.0.1:5173 with the backend behind it.

Keys go in the root `.env` (see `.env.example`); `NVIDIA_API_KEY` alone is enough for everything.

## How it works

| Step | What | Where |
|---|---|---|
| View | Mozilla **pdf.js** `PDFViewer` (virtualized pages, text selection, zoom, find) | `frontend/src/PdfViewer.tsx` |
| Index (seconds, local) | **PyMuPDF** extracts every text line with its box and detects figure regions (images + vector-drawing clusters) with their captions and in-figure labels | `backend/app/indexer.py` |
| Index (background) | Text embeddings and **page-image embeddings** (`llama-nemotron-embed-vl-1b-v2`) so diagrams/photos are found by what they show; **Nemotron Parse** OCR for scanned pages | `embeddings.py`, `indexer.py` |
| Retrieve | Only the open PDF. BM25 over text + BM25 over figure captions/labels + text and image embeddings, fused; "see Figure 2.1-1" references are followed to the page that draws it | `retrieval.py` |
| Answer | **Gemma 4** reads the top 8 pages (text lines with IDs, figure list, images of the best 3) and cites evidence by line/figure ID, so text highlights land on the PDF's own lines | `answer.py` |
| Pinpoint in diagrams | A second Gemma 4 call on a high-resolution crop of the cited figure boxes the exact component/label | `answer.py` (`_refine`) |
| Hosts | Gemma 4 on NVIDIA, Google AI Studio and OpenRouter, raced with retries; Gemini Flash as last resort | `llm.py` |

A 509-page PDF indexes in about 7 s (askable immediately); embeddings and diagram indexing finish in the background in about a minute.

## Verify

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests -q -p no:cacheprovider --basetemp out\pytest-pinpoint
frontend\node_modules\.bin\tsc.cmd --noEmit -p frontend\tsconfig.json
npm --prefix frontend run build
```

## Limits

- Answer latency depends on free-tier hosts: 4-10 s when they are idle, 30-75 s when they queue. Paid endpoints (e.g. OpenRouter credit for `google/gemma-4-31b-it`) make it consistently fast.
- Highlights are model choices; the citation bar and "Zoom to highlight" make them easy to check.
- The previous page-by-page search engine and UI are archived in git history and `out/pre-rewrite/`.
