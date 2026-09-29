"""Question -> short answer + exact highlighted evidence in ONE document.

1. Retrieval ranks the document's pages (BM25 + embeddings).
2. Gemma 4 reads the top pages: their text lines (each with an ID), their
   detected figure regions (each with an ID) and images of the best pages.
   It answers and cites evidence by ID, never by free-drawn text boxes, so
   text highlights land exactly on the PDF's own text lines.
3. Diagram citations name a target ("the altimeter gauge"). A second Gemma 4
   call looks at a high-resolution crop of just that figure and boxes the
   target, which is mapped back to page coordinates.
"""

from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor

from . import indexer, llm, retrieval, store

log = logging.getLogger(__name__)

TEXT_PAGES = 8            # pages whose text/figure layout is given to the model
IMAGE_PAGES = 3           # of those, pages also sent as images
MAX_LINES_PER_PAGE = 140
MAX_LINE_CHARS = 220
SECOND_ROUND_PAGES = 8    # if nothing is found, one more round on the next pages

ANSWER_PROMPT = """You are Pinpoint, an assistant that answers questions about ONE PDF and points to the exact evidence on the page.

Document: "{filename}" ({page_count} pages). Below are the pages most relevant to the question, found by search. Every text line has an ID like L12. Every detected figure/diagram/table/photo region has an ID like F2 with its box as [ymin,xmin,ymax,xmax] in 0-1000 page coordinates, plus its caption and the labels printed inside it. Images of pages {image_pages} are attached in that order.
{history}
Question: {question}

Rules:
- Answer ONLY from these pages; never from outside knowledge. Be concise: 1-3 sentences, or a short bullet list for multi-part answers. Put citation markers right after the claim each supports: [1] means the FIRST item of "citations", [2] the second, and so on (never a page number).
- Each citation points to ONE place on ONE page, in one of these forms:
  * text:   {{"page": 7, "lines": ["L40", "L41"]}}  - the 1-6 lines that state the answer, no more.
  * figure: {{"page": 7, "figure": "F1", "target": "<short visual description of the exact part to highlight>"}} - use "target": null only when the whole figure is the answer.
  * region: {{"page": 3, "box_2d": [ymin, xmin, ymax, xmax], "target": "<what is there>"}} - only for something visible in an attached page image that has no line or figure ID (e.g. a scanned page or an undetected drawing).
- When the answer is (also) shown in a diagram, schematic, chart, table or photo, you MUST cite that visual, with a target naming the specific component, label, row, curve or connection. Check the figure labels and captions and the attached images for this. For "where is X" questions about a physical thing, cite the drawing that shows X, and add a text citation too if the text also states it.
- Prefer evidence that directly answers the question (for example the component or system that performs the function asked about) over passages that only mention the topic in passing.
- Cite the smallest sufficient evidence; at most 4 citations.
- For "which / list / all / every" questions, be exhaustive: scan the WHOLE table, list or diagram and include every matching entry in the answer, not just the first. For a table, one figure citation whose target names all matching rows/cells (e.g. "the UART0 TX cells in rows GPIO0, GPIO12, GPIO16") is best.
- Never write line IDs (L12), figure IDs (F1) or page numbers in brackets in the answer text; the only brackets allowed there are citation markers like [1].
- If these pages do not contain the answer, return found=false with a one-sentence answer saying it is not in these pages, and no citations.

Return ONLY this JSON:
{{"found": true, "answer": "... [1] ...", "citations": [ ... ]}}

{pages}"""

REFINE_PROMPT = """This image is a crop of a figure from a PDF page (a diagram, schematic, chart, table or photo).
Locate exactly: {target}
(The user's question was: {question})

Return ONLY JSON: {{"found": true, "boxes_2d": [[ymin, xmin, ymax, xmax]]}} with coordinates in 0-1000 relative to THIS image.
Box tightly around the requested part. Use several boxes only if it consists of separate parts (for example a component and its printed label, or several matching table cells); at most 8. Use {{"found": false, "boxes_2d": []}} if it is not visible."""


def _box1000(b: list[float]) -> str:
    x0, y0, x1, y1 = b
    return f"[{round(y0 * 1000)},{round(x0 * 1000)},{round(y1 * 1000)},{round(x1 * 1000)}]"


def _display_rows(page: dict) -> list[tuple[int, list[int]]]:
    """Text lines as the model sees them: [(id_index, member line indexes)].

    PDF tables extract one line per cell, which loses which row a value is
    in and bloats the prompt. Lines inside a table-like figure (many labels)
    that share a baseline are joined into one row, "16 | SPI0 RX | UART0 TX";
    the row keeps its first cell's ID, and citing it highlights the row.
    """
    lines = page["lines"]
    tables = [f["box"] for f in page["figures"] if len(f.get("labels") or []) >= 12]

    def table_of(box):
        for i, t in enumerate(tables):
            if (box[0] >= t[0] - 0.005 and box[2] <= t[2] + 0.005
                    and box[1] >= t[1] - 0.005 and box[3] <= t[3] + 0.005):
                return i
        return None

    rows: list[tuple[int, list[int]]] = []
    open_rows: dict[int, list[tuple[float, float, list[int]]]] = {}
    for idx, ln in enumerate(lines):
        t = table_of(ln["box"])
        if t is None:
            rows.append((idx, [idx]))
            continue
        y0, y1 = ln["box"][1], ln["box"][3]
        centre, height = (y0 + y1) / 2, max(0.004, y1 - y0)
        for row_centre, row_height, members in open_rows.setdefault(t, []):
            if abs(row_centre - centre) < 0.5 * min(height, row_height):
                members.append(idx)
                break
        else:
            members = [idx]
            open_rows[t].append((centre, height, members))
            rows.append((idx, members))
    # Cells of a row in left-to-right order.
    for _, members in rows:
        members.sort(key=lambda m: lines[m]["box"][0])
    rows.sort(key=lambda r: r[0])
    return [(min(members), members) for _, members in rows]


def _page_block(page: dict, has_image: bool) -> str:
    out = [f"=== PAGE {page['page_no']}{' (image attached)' if has_image else ''} ==="]
    if page["figures"]:
        out.append("FIGURES:")
        for f in page["figures"]:
            desc = f"{f['id']} {_box1000(f['box'])}"
            if f.get("caption"):
                desc += f' caption: "{f["caption"][:160]}"'
            if f.get("labels"):
                desc += " labels: " + "; ".join(t[:60] for t in f["labels"][:25])
            out.append(desc)
    rows = _display_rows(page)[:MAX_LINES_PER_PAGE]
    if rows:
        out.append("TEXT:")
        for first, members in rows:
            text = " | ".join(page["lines"][m]["text"] for m in members)
            out.append(f"L{first + 1} {text[:MAX_LINE_CHARS * (2 if len(members) > 1 else 1)]}")
    elif not page["figures"]:
        out.append("(no text layer - see the page image if attached)")
    return "\n".join(out)


def _history_block(history: list[dict]) -> str:
    turns = [m for m in history if m["role"] in ("user", "assistant")][-4:]
    if not turns:
        return ""
    lines = ["Earlier in this conversation (for resolving follow-up questions only):"]
    for m in turns:
        lines.append(f"{m['role'].upper()}: {m['content'][:400]}")
    return "\n" + "\n".join(lines) + "\n"


def _clip_box(b) -> list[float] | None:
    try:
        ymin, xmin, ymax, xmax = (float(v) for v in b)
    except (TypeError, ValueError):
        return None
    x0, y0 = max(0.0, min(1.0, xmin / 1000)), max(0.0, min(1.0, ymin / 1000))
    x1, y1 = max(0.0, min(1.0, xmax / 1000)), max(0.0, min(1.0, ymax / 1000))
    if x1 - x0 < 0.002 or y1 - y0 < 0.002:
        return None
    return [x0, y0, x1, y1]


def _expand(box: list[float], frac: float) -> list[float]:
    w, h = box[2] - box[0], box[3] - box[1]
    return [max(0.0, box[0] - w * frac), max(0.0, box[1] - h * frac),
            min(1.0, box[2] + w * frac), min(1.0, box[3] + h * frac)]


def _refine(doc_id: str, page_no: int, area: list[float], target: str,
            question: str) -> list[list[float]] | None:
    """Box `target` inside the page `area` using a zoomed crop."""
    png = indexer.render_page_png(store.pdf_path(doc_id), page_no, max_side=1400, clip=area)
    t0 = time.monotonic()
    data, _used = llm.complete_json(
        [llm.text_part(REFINE_PROMPT.format(target=target, question=question)), llm.image_part(png)],
        max_tokens=300,
    )
    log.info("refine '%s' took %.1fs: %s", target, time.monotonic() - t0, data)
    if not data.get("found"):
        return None
    w, h = area[2] - area[0], area[3] - area[1]
    boxes = []
    for b in (data.get("boxes_2d") or [])[:8]:
        c = _clip_box(b)
        if c is None:
            continue
        mapped = [area[0] + c[0] * w, area[1] + c[1] * h, area[0] + c[2] * w, area[1] + c[3] * h]
        # A box covering nearly the whole crop adds nothing over the figure.
        if (c[2] - c[0]) * (c[3] - c[1]) > 0.85:
            return None
        boxes.append([round(v, 5) for v in mapped])
    return boxes or None


def _ground(doc_id: str, pages: dict[int, dict], image_pages: set[int], raw: dict,
            question: str) -> dict | None:
    """Turn one model citation into highlight boxes on the page."""
    try:
        page_no = int(raw.get("page"))
    except (TypeError, ValueError):
        return None
    page = pages.get(page_no)
    if page is None:
        return None
    target = raw.get("target") or None

    if raw.get("lines"):
        boxes, texts = [], []
        row_of = {first: members for first, members in _display_rows(page)}
        for lid in raw["lines"][:8]:
            try:
                idx = int(str(lid).strip().lstrip("Ll")) - 1
            except ValueError:
                continue
            if 0 <= idx < len(page["lines"]):
                members = row_of.get(idx, [idx])
                cells = [page["lines"][m] for m in members]
                # A table row is one highlight spanning all of its cells.
                boxes.append([min(c["box"][0] for c in cells), min(c["box"][1] for c in cells),
                              max(c["box"][2] for c in cells), max(c["box"][3] for c in cells)])
                texts.append(" | ".join(c["text"] for c in cells))
        if boxes:
            return {"page": page_no, "kind": "text", "boxes": boxes,
                    "snippet": " ".join(texts)[:240]}

    if raw.get("figure"):
        fig = next((f for f in page["figures"] if f["id"] == str(raw["figure"]).strip()), None)
        if fig is not None:
            boxes = None
            if target:
                try:
                    boxes = _refine(doc_id, page_no, _expand(fig["box"], 0.02), target, question)
                except Exception:  # noqa: BLE001 - fall back to the whole figure
                    log.exception("refine failed")
            return {"page": page_no, "kind": "figure", "boxes": boxes or [fig["box"]],
                    "figure_box": fig["box"], "precise": bool(boxes),
                    "snippet": target or fig.get("caption") or "Figure"}

    if raw.get("box_2d") is not None and page_no in image_pages:
        box = _clip_box(raw["box_2d"])
        if box is not None:
            boxes = None
            if target:
                try:
                    boxes = _refine(doc_id, page_no, _expand(box, 0.35), target, question)
                except Exception:  # noqa: BLE001
                    log.exception("refine failed")
            return {"page": page_no, "kind": "region", "boxes": boxes or [box],
                    "precise": bool(boxes), "snippet": target or "Region"}
    return None


def _ask_round(doc: dict, question: str, history: list[dict], page_nos: list[int],
               visual_pages: list[int] | None = None) -> dict:
    with store.connect() as conn:
        pages = {p: store.load_page(conn, doc["id"], p) for p in page_nos}
    pages = {k: v for k, v in pages.items() if v is not None}
    order = [p for p in page_nos if p in pages]
    # Image slots: pages without a text layer (only understandable from the
    # image), then pages whose figures/pictures matched the question, then rank.
    image_pages = [p for p in order if pages[p]["source"] == "none"][:IMAGE_PAGES]
    for p in (visual_pages or [])[:2]:
        if p in pages and p not in image_pages and len(image_pages) < IMAGE_PAGES:
            image_pages.append(p)
    for p in order:
        if len(image_pages) >= IMAGE_PAGES:
            break
        if p not in image_pages:
            image_pages.append(p)
    image_pages.sort()
    pdf_file = store.pdf_path(doc["id"])

    with ThreadPoolExecutor(max_workers=IMAGE_PAGES) as pool:
        pngs = list(pool.map(lambda p: indexer.render_page_png(pdf_file, p, max_side=1200), image_pages))
    blocks = "\n\n".join(_page_block(pages[p], p in image_pages) for p in sorted(order))
    prompt = ANSWER_PROMPT.format(
        filename=doc["filename"], page_count=doc["page_count"],
        image_pages=", ".join(map(str, image_pages)) or "(none)",
        history=_history_block(history), question=question, pages=blocks,
    )
    content = [llm.text_part(prompt)]
    for p, png in zip(image_pages, pngs):
        content += [llm.text_part(f"Image of PAGE {p}:"), llm.image_part(png)]
    t0 = time.monotonic()
    data, used = llm.complete_json(content, max_tokens=1200)
    log.info("answer call took %.1fs via %s: %s", time.monotonic() - t0, used, data)

    raw_cites = [c for c in (data.get("citations") or []) if isinstance(c, dict)][:4]
    with ThreadPoolExecutor(max_workers=4) as pool:
        grounded = list(pool.map(
            lambda c: _ground(doc["id"], pages, set(image_pages), c, question), raw_cites))
    return {"found": bool(data.get("found")) and any(grounded),
            "answer": str(data.get("answer") or "").strip(),
            "grounded": grounded, "model": used, "pages": sorted(order)}


EXPAND_PROMPT = """You help search a PDF titled "{filename}".
Rewrite the user's question as a short search query in the precise technical vocabulary this kind of document uses: the formal names of the components, systems, parameters, figures or tables involved (for example "front wheel wobbling" -> "shimmy damper nose gear oscillation"). Resolve follow-up questions using the conversation.
{history}
Question: {question}

Return ONLY JSON: {{"query": "<8-20 words of technical search terms>"}}"""
EXPAND_DEADLINE_SECONDS = 8


def _expand_query(doc: dict, question: str, history: list[dict]) -> str | None:
    """Rewrite the question into document vocabulary; skipped if it is slow."""
    prompt = EXPAND_PROMPT.format(filename=doc["filename"], question=question,
                                  history=_history_block(history))
    t0 = time.monotonic()
    try:
        data, _used = llm.complete_json([llm.text_part(prompt)], max_tokens=120,
                                        deadline_seconds=EXPAND_DEADLINE_SECONDS)
    except llm.LLMError:
        log.info("query expansion skipped after %.1fs", time.monotonic() - t0)
        return None
    query = str(data.get("query") or "").strip()
    return query[:300] or None


def _renumber(answer: str, grounded: list[dict | None]) -> tuple[str, list[dict]]:
    """Drop citations that could not be grounded and renumber the markers.

    Models sometimes write the page number as the marker ([7]) or omit
    markers; both are repaired so every chip in the answer is clickable.
    """
    mapping: dict[int, int] = {}
    citations: list[dict] = []
    for i, g in enumerate(grounded, 1):
        if g is not None:
            citations.append({**g, "n": len(citations) + 1})
            mapping[i] = len(citations)
    markers = [int(m) for m in re.findall(r"\[(\d+)\]", answer)]
    by_page: dict[int, int] = {}
    for c in citations:
        by_page.setdefault(c["page"], c["n"])
    use_pages = bool(markers) and all(m not in mapping for m in markers) \
        and any(m in by_page for m in markers)

    def sub(m):
        num = int(m.group(1))
        new = by_page.get(num) if use_pages else mapping.get(num)
        return f"[{new}]" if new else ""

    # Internal IDs must never reach the reader. "[427, L2]" names a page, so
    # it becomes that page's citation marker; bare "(L12)" / "[F1]" go away.
    def page_ref(m):
        n = by_page.get(int(m.group(1)))
        return f"[{n}]" if n else ""

    answer = re.sub(r"\[\s*(?:p(?:age)?\s*)?(\d+)\s*,\s*[LF]\d+(?:\s*[-,]\s*[LF]?\d+)*\s*\]",
                    lambda m: "\x00" + page_ref(m)[1:-1] + "\x01" if page_ref(m) else "", answer)
    answer = re.sub(r"\(\s*(?:[LF]\d+(?:\s*[-,]\s*)?)+\)", "", answer)
    answer = re.sub(r"\[\s*[LF]\d+(?:\s*[-,]\s*[LF]?\d+)*\s*\]", "", answer)
    answer = re.sub(r"\[(\d+)\]", sub, answer)
    answer = answer.replace("\x00", "[").replace("\x01", "]")
    answer = re.sub(r"(\[\d+\])(?:\1)+", r"\1", answer)
    answer = re.sub(r"[ \t]{2,}", " ", answer)
    answer = re.sub(r"\s+([.,;:])", r"\1", answer).strip()
    # A trailing "[1][2]" that only repeats markers used inline is noise.
    tail = re.search(r"(?:\s*\[\d+\])+\s*$", answer)
    if tail and tail.start() > 0:
        body = answer[:tail.start()]
        kept = [m for m in re.findall(r"\[\d+\]", tail.group(0)) if m not in body]
        answer = (body + (" " + "".join(kept) if kept else "")).strip()
    missing = [c["n"] for c in citations if f"[{c['n']}]" not in answer]
    if missing:
        answer += " " + "".join(f"[{n}]" for n in missing)
    return answer, citations


def ask(doc_id: str, question: str) -> dict:
    started = time.monotonic()
    with store.connect() as conn:
        doc_row = store.get_document(conn, doc_id)
        if doc_row is None:
            raise KeyError(doc_id)
        doc = dict(doc_row)
        history = store.list_messages(conn, doc_id)
    expansion = _expand_query(doc, question, history)
    with store.connect() as conn:
        ranking = retrieval.rank_pages(conn, doc_id, question, expansion)
    log.info("retrieval took %.1fs (expansion %r): %s", time.monotonic() - started, expansion,
             ranking["pages"][:10])
    ranked = ranking["pages"] or list(range(1, doc["page_count"] + 1))
    if doc["page_count"] <= TEXT_PAGES:
        ranked = ranked + [p for p in range(1, doc["page_count"] + 1) if p not in ranked]

    visual = ranking.get("visual_pages", [])
    first = ranked[:TEXT_PAGES]
    # Make sure the best visual matches are read in the first round.
    for p in visual[:2]:
        if p not in first:
            first = first[:TEXT_PAGES - 1] + [p]
    result = _ask_round(doc, question, history, first, visual)
    searched = list(result["pages"])
    rest = [p for p in ranked if p not in first]
    if not result["found"] and rest:
        try:
            second = _ask_round(doc, question, history, rest[:SECOND_ROUND_PAGES], visual)
            searched += second["pages"]
            if second["found"]:
                result = second
        except llm.LLMError:
            log.warning("second round failed; keeping the first answer")

    answer, citations = _renumber(result["answer"], result["grounded"])
    if not citations:
        answer = answer or "I couldn't find that in this document."
    meta = {"model": result["model"], "pages_read": sorted(searched),
            "seconds": round(time.monotonic() - started, 1), "retrieval": ranking["signals"]}
    with store.connect() as conn:
        store.add_message(conn, doc_id, "user", question)
        msg = store.add_message(conn, doc_id, "assistant", answer, citations, meta)
    return msg
