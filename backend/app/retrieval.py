"""Rank the pages of ONE document for a question.

Three signals fused by reciprocal rank: BM25 over page text (exact terms,
part numbers), BM25 over figure captions and in-figure labels (finds the page
that *draws* something), and embedding similarity (synonyms, paraphrases).
Then figure references are followed: when a top page says "see Figure 2.1-1"
the page that holds that figure is pulled in, because the drawing is often
on a different page from the text that discusses it.
"""

from __future__ import annotations

import json
import re

from . import embeddings

_STOP = {
    "the", "a", "an", "is", "in", "on", "at", "to", "for", "of", "and", "or", "with",
    "what", "where", "when", "how", "which", "who", "why", "this", "that", "these",
    "those", "it", "be", "was", "were", "are", "by", "from", "as", "do", "does",
    "did", "have", "has", "had", "will", "would", "could", "should", "its", "their",
    "there", "then", "than", "into", "not", "no", "but", "if", "about", "can", "may",
    "show", "shown", "find", "located", "location", "tell", "me", "document", "page",
    "pdf", "i", "you", "my", "your", "please", "any", "all", "some",
}
RRF_K = 60


def keywords(question: str) -> list[str]:
    words = re.findall(r"[\w][\w\-./]*", question.lower())
    seen: list[str] = []
    for w in words:
        w = w.strip(".-/")
        if len(w) >= 2 and w not in _STOP and w not in seen:
            seen.append(w)
    return seen


def _fts_query(terms: list[str]) -> str:
    parts = []
    for t in terms:
        cleaned = re.sub(r'["]', "", t)
        if cleaned:
            parts.append(f'"{cleaned}"')
    return " OR ".join(parts)


def keyword_rank(conn, doc_id: str, question: str, limit: int = 60,
                 table: str = "pages_fts") -> list[int]:
    terms = keywords(question)
    if not terms:
        return []
    try:
        rows = conn.execute(
            f"SELECT page_no FROM {table} WHERE {table} MATCH ? AND doc_id = ? "
            f"ORDER BY bm25({table}) LIMIT ?",
            (_fts_query(terms), doc_id, limit),
        ).fetchall()
    except Exception:  # noqa: BLE001 - malformed query; fall back to no keyword signal
        return []
    return [int(r["page_no"]) for r in rows]


def semantic_rank(conn, doc_id: str, question: str, limit: int = 60,
                  table: str = "embeddings", cache: dict | None = None) -> list[int]:
    vectors, model = embeddings.load_vectors(conn, doc_id, table)
    if not vectors or not model:
        return []
    cache = cache if cache is not None else {}
    if model not in cache:
        cache[model] = embeddings.embed_query(question, model)
    query = cache[model]
    if query is None:
        return []
    scored = []
    for page_no, vec in vectors.items():
        scored.append((sum(a * b for a, b in zip(query, vec)), page_no))
    scored.sort(reverse=True)
    return [p for _, p in scored[:limit]]


_VISUAL = re.compile(
    r"\b(where|diagram|figure|fig|schematic|drawing|chart|graph|plot|curve|table|pinout|pin|"
    r"layout|picture|photo|image|illustration|flow ?chart|wiring|circuit|dimension|shown|located)\b", re.I)
_FIG_REF = re.compile(r"\b(fig(?:ure)?\.?|table)\s*([A-Z]?\d+(?:[.\-]\d+)*[a-z]?)", re.I)


def _figure_pages(conn, doc_id: str) -> dict[str, int]:
    """Map a normalized figure/table label ("figure 2.1-1") to its page."""
    out: dict[str, int] = {}
    for row in conn.execute("SELECT page_no, figures_json FROM pages WHERE doc_id = ?", (doc_id,)):
        for fig in json.loads(row["figures_json"]):
            m = _FIG_REF.match(fig.get("caption") or "")
            if m:
                key = f"{'table' if m.group(1).lower() == 'table' else 'figure'} {m.group(2).lower()}"
                out.setdefault(key, int(row["page_no"]))
    return out


def _follow_references(conn, doc_id: str, question: str, top: list[int]) -> list[int]:
    fig_pages: dict[str, int] | None = None
    found: list[int] = []
    texts = [question] + [
        (conn.execute("SELECT text FROM pages WHERE doc_id = ? AND page_no = ?", (doc_id, p))
         .fetchone() or {"text": ""})["text"]
        for p in top
    ]
    terms = keywords(question)
    for i, text in enumerate(texts):
        for line in text.splitlines():
            # Only references in lines about the question's subject.
            if i and not any(t in line.lower() for t in terms):
                continue
            for m in _FIG_REF.finditer(line):
                if fig_pages is None:
                    fig_pages = _figure_pages(conn, doc_id)
                key = f"{'table' if m.group(1).lower() == 'table' else 'figure'} {m.group(2).lower()}"
                page = fig_pages.get(key)
                if page is not None and page not in found:
                    found.append(page)
    return found[:3]


def rank_pages(conn, doc_id: str, question: str, expansion: str | None = None) -> dict:
    """Return {"pages": [page_no, ...] best first, "signals": {...}}.

    `expansion` is the question rewritten in the document's technical terms
    ("front wheel wobbling" -> "shimmy damper nose gear oscillation"); it is
    ranked like the question and fused with it.
    """
    visual_q = bool(_VISUAL.search(question))
    fig_weight = 1.3 if visual_q else 0.7
    rankings: list[tuple[list[int], float]] = []
    kw = fig = sem = vis = []
    for i, query in enumerate(q for q in (question, expansion) if q):
        cache: dict = {}
        k = keyword_rank(conn, doc_id, query)
        f = keyword_rank(conn, doc_id, query, table="figures_fts")
        se = semantic_rank(conn, doc_id, query, cache=cache)
        vi = semantic_rank(conn, doc_id, query, limit=30, table="image_embeddings", cache=cache)
        rankings += [(k, 1.0), (f, fig_weight), (se, 1.0), (vi, 1.2 if visual_q else 0.8)]
        if i == 0:
            kw, fig, sem, vis = k, f, se, vi
        else:
            fig, vis = fig + [p for p in f if p not in fig], vis + [p for p in vi if p not in vis]
    scores: dict[int, float] = {}
    for ranking, weight in rankings:
        for rank, page_no in enumerate(ranking):
            scores[page_no] = scores.get(page_no, 0.0) + weight / (RRF_K + rank + 1)
    ordered = sorted(scores, key=lambda p: -scores[p])
    # Pull in pages holding figures that the best pages refer to.
    refs = [p for p in _follow_references(conn, doc_id, question, ordered[:5]) if p not in ordered[:4]]
    if refs:
        ordered = ordered[:2] + refs + [p for p in ordered[2:] if p not in refs]
    # Pages with no text layer yet (scans awaiting OCR) cannot be ranked by
    # text; list them after ranked pages so small documents still see them.
    unranked = [
        int(r["page_no"]) for r in conn.execute(
            "SELECT page_no FROM pages WHERE doc_id = ? AND source = 'none' ORDER BY page_no",
            (doc_id,),
        )
        if int(r["page_no"]) not in scores
    ]
    return {"pages": ordered + unranked,
            "visual_pages": [p for p in (fig[:6] + vis[:6]) if p in scores],
            "signals": {"keyword": len(kw), "figure": len(fig), "semantic": len(sem), "image": len(vis),
                        "followed_refs": refs, "unranked": len(unranked)}}
