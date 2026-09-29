# Pinpoint

Open a PDF, type a question into the search bar, and Pinpoint scrolls to the answer and highlights it on the page: the exact text lines, or the exact part of a diagram, schematic, table or photo. The written answer is one click away in a side panel.

## Setup

Requirements: Windows, [Python 3.12+](https://www.python.org/) with [uv](https://docs.astral.sh/uv/), and [Node.js 20+](https://nodejs.org/).

```powershell
git clone https://github.com/AVaidya-1/Pinpoint.git
cd Pinpoint
copy .env.example .env          # then add at least one API key (NVIDIA_API_KEY covers everything)
cd backend; uv sync; cd ..      # creates backend\.venv
npm --prefix frontend install
```

## Run

Double-click **`Start Pinpoint.cmd`**. It builds the frontend, starts one server and opens **http://127.0.0.1:8000** (use `127.0.0.1`, not `localhost`). Close its window to stop.

For frontend development with hot reload, `backend\.venv\Scripts\python.exe app_tools\dev.py` runs Vite on http://127.0.0.1:5173 with the backend behind it.

## Using it

- **Search bar** (bottom): ask a question and press Enter. `/` focuses it from anywhere.
- **Sources**: the numbered chips above the search bar jump between highlights; the buttons beside them hide/show, zoom to and re-center the highlight.
- **Answer panel**: the panel button (top left) or **Ctrl+B** opens the full written answers.
- **Open PDF** (top right) or drag a PDF onto the window. Recent PDFs are under the clock icon.

## How it works

| Step | What | Where |
|---|---|---|
| View | Mozilla **pdf.js** `PDFViewer` (virtualized pages, text selection, zoom, find) | `frontend/src/PdfViewer.tsx` |
| Search bar | A glass slab rendered with **[vgpu](https://vgpu.sh)** (WebGPU): Snell refraction through bevelled edges, spectral dispersion, absorption tint and Fresnel reflections, with a frosted top for legibility. Falls back to a CSS/SVG glass effect without WebGPU | `frontend/src/glassGpu.ts`, `SearchDock.tsx` |
| Index (seconds, local) | **PyMuPDF** extracts every text line with its box and detects figure regions (images + vector-drawing clusters) with their captions and in-figure labels | `backend/app/indexer.py` |
| Index (background) | Text embeddings and **page-image embeddings** (`llama-nemotron-embed-vl-1b-v2`) so diagrams/photos are found by what they show; **Nemotron Parse** OCR for scanned pages | `embeddings.py`, `indexer.py` |
| Retrieve | Only the open PDF. BM25 over text + BM25 over figure captions/labels + text and image embeddings, fused; "see Figure 2.1-1" references are followed to the page that draws it | `retrieval.py` |
| Answer | **Gemma 4** reads the top 8 pages (text lines with IDs, figure list, images of the best 3) and cites evidence by line/figure ID, so text highlights land on the PDF's own lines | `answer.py` |
| Pinpoint in diagrams | A second Gemma 4 call on a high-resolution crop of the cited figure boxes the exact component/label | `answer.py` (`_refine`) |
| Hosts | Gemma 4 on NVIDIA, Google AI Studio and OpenRouter, raced with retries; Gemini Flash as last resort | `llm.py` |

A 509-page PDF indexes in about 7 s (askable immediately); embeddings and diagram indexing finish in the background in about a minute. Uploaded PDFs and the index live in `data/` (git-ignored).

## Tests

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests -q
npm --prefix frontend run build
```

## Limits

- Answer latency depends on free-tier hosts: 4-10 s when they are idle, 30-75 s when they queue. Paid endpoints (e.g. OpenRouter credit for `google/gemma-4-31b-it`) make it consistently fast.
- Highlights are model choices; zoom to the highlight to check it against the page.
