"""Offline tests: extraction, retrieval, citation grounding and the API.

The model and embedding providers are stubbed, so these run without keys.
"""

from __future__ import annotations

import io
import time

import pymupdf
import pytest
from fastapi.testclient import TestClient


def make_pdf(pages: int = 3) -> bytes:
    """A small PDF: text pages, a figure with a caption on page 2."""
    doc = pymupdf.open()
    for n in range(1, pages + 1):
        page = doc.new_page(width=600, height=800)
        page.insert_text((50, 60), f"Chapter {n}", fontsize=18)
        if n == 2:
            page.insert_text((50, 100), "The altimeter is located on the right side of the PFD.")
            shape = page.new_shape()
            shape.draw_rect(pymupdf.Rect(50, 200, 450, 500))
            shape.draw_circle((150, 350), 60)
            shape.finish(color=(0, 0, 0), fill=(0.8, 0.9, 1))
            shape.commit()
            page.insert_text((120, 300), "Frozen altimeter")
            page.insert_text((50, 530), "Figure 7-11. Blocked static system.")
        elif n == 3:
            page.insert_text((50, 100), "The static port is described in Figure 7-11 on the previous page.")
        else:
            page.insert_text((50, 100), "Unrelated introduction text about aircraft.")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.fixture()
def app_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EVIDENCE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NVIDIA_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_KEY", "")
    from app import embeddings, llm, main

    # No network: embeddings unavailable, the model is a stub set per test.
    monkeypatch.setattr(embeddings, "_embed", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")))
    calls: list = []

    def fake_complete(content, max_tokens=1200, deadline_seconds=None):
        if "Rewrite the user's question" in content[0]["text"]:
            return {"query": ""}, "stub:model"  # query expansion: no rewrite
        calls.append(content)
        return fake_complete.reply(content), "stub:model"

    fake_complete.reply = lambda content: {"found": False, "answer": "Not here.", "citations": []}
    monkeypatch.setattr(llm, "complete_json", fake_complete)
    with TestClient(main.app) as client:
        yield client, fake_complete, calls


def upload(client, data: bytes, name: str = "doc.pdf") -> dict:
    res = client.post("/api/documents", files={"file": (name, data, "application/pdf")})
    assert res.status_code == 201, res.text
    doc = res.json()
    for _ in range(100):
        doc = client.get(f"/api/documents/{doc['id']}").json()
        if doc["status"] == "ready":
            return doc
        time.sleep(0.05)
    raise AssertionError(f"indexing did not finish: {doc}")


def test_extract_lines_and_figure_with_caption():
    from app.indexer import extract_page

    doc = pymupdf.open(stream=make_pdf(), filetype="pdf")
    page = extract_page(doc[1])
    assert page["source"] == "text"
    texts = [ln["text"] for ln in page["lines"]]
    assert "The altimeter is located on the right side of the PFD." in texts
    assert page["figures"], "the drawn diagram should be detected"
    fig = page["figures"][0]
    assert fig["caption"] == "Figure 7-11. Blocked static system."
    assert "Frozen altimeter" in fig["labels"]
    x0, y0, x1, y1 = fig["box"]
    assert 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1


def test_upload_rejects_non_pdf(app_env):
    client, _, _ = app_env
    res = client.post("/api/documents", files={"file": ("x.pdf", b"not a pdf", "application/pdf")})
    assert res.status_code == 415


def test_upload_dedupes_same_file(app_env):
    client, _, _ = app_env
    data = make_pdf()
    a = upload(client, data)
    b = client.post("/api/documents", files={"file": ("again.pdf", data, "application/pdf")}).json()
    assert a["id"] == b["id"]
    assert a["page_count"] == 3 and a["indexed_pages"] == 3


def test_retrieval_ranks_one_document_and_follows_figure_refs(app_env):
    client, _, _ = app_env
    doc = upload(client, make_pdf())
    other = upload(client, make_pdf(5), "other.pdf")
    from app import retrieval, store

    with store.connect() as conn:
        ranked = retrieval.rank_pages(conn, doc["id"], "static port")
        # Page 3 states it; page 2 draws Figure 7-11, which page 3 refers to.
        assert set(ranked["pages"][:2]) == {2, 3}
        # Only this document's pages are ever candidates.
        assert set(ranked["pages"]) <= {1, 2, 3}
        assert max(retrieval.rank_pages(conn, other["id"], "altimeter")["pages"]) <= 5


def test_ask_grounds_text_and_figure_citations(app_env):
    client, stub, calls = app_env
    doc = upload(client, make_pdf())
    stub.reply = lambda content: {
        "found": True,
        "answer": "It is on the right side of the PFD [1] and drawn in the figure [2].",
        "citations": [{"page": 2, "lines": ["L2"]}, {"page": 2, "figure": "F1", "target": None}],
    }
    res = client.post(f"/api/documents/{doc['id']}/ask", json={"question": "where is the altimeter"})
    assert res.status_code == 200, res.text
    msg = res.json()
    assert msg["content"].endswith("[2].")
    text, fig = msg["citations"]
    assert text["kind"] == "text" and text["page"] == 2
    assert "altimeter is located" in text["snippet"]
    assert fig["kind"] == "figure" and fig["boxes"] == [fig["figure_box"]]
    # The prompt only ever contains pages of this one document.
    prompt = calls[0][0]["text"]
    assert "=== PAGE 2" in prompt and "L2 The altimeter is located" in prompt
    history = client.get(f"/api/documents/{doc['id']}/messages").json()["messages"]
    assert [m["role"] for m in history] == ["user", "assistant"]


def test_invalid_citations_are_dropped(app_env):
    client, stub, _ = app_env
    doc = upload(client, make_pdf())
    stub.reply = lambda content: {
        "found": True, "answer": "Answer [1] and [2].",
        "citations": [{"page": 99, "lines": ["L1"]}, {"page": 2, "lines": ["L999", "L2"]}],
    }
    msg = client.post(f"/api/documents/{doc['id']}/ask", json={"question": "altimeter"}).json()
    assert len(msg["citations"]) == 1 and msg["citations"][0]["n"] == 1
    assert msg["content"] == "Answer and [1]."


def test_refine_maps_crop_boxes_back_to_page(app_env, monkeypatch):
    client, stub, _ = app_env
    doc = upload(client, make_pdf())

    def reply(content):
        if "Locate exactly" in content[0]["text"]:
            return {"found": True, "boxes_2d": [[0, 0, 500, 500]]}  # top-left quarter of the crop
        return {"found": True, "answer": "Here [1].",
                "citations": [{"page": 2, "figure": "F1", "target": "the altimeter gauge"}]}

    stub.reply = reply
    c = client.post(f"/api/documents/{doc['id']}/ask", json={"question": "altimeter"}).json()["citations"][0]
    assert c["precise"] is True
    fx0, fy0, fx1, fy1 = c["figure_box"]
    bx0, by0, bx1, by1 = c["boxes"][0]
    assert fx0 - 0.03 <= bx0 < bx1 <= fx1 and fy0 - 0.03 <= by0 < by1 <= fy1
    assert bx1 - bx0 < (fx1 - fx0) * 0.6


@pytest.mark.parametrize("raw, expected", [
    ("Sensor [427, L2] is on the extruder [428, L2]. [1][2]", "Sensor [1] is on the extruder [2]."),
    ("Located (L12) in the drive stage [1].", "Located in the drive stage [1]. [2]"),
    ("No markers here.", "No markers here. [1][2]"),
])
def test_renumber_cleans_markers(raw, expected):
    from app.answer import _renumber

    grounded = [{"page": 427, "kind": "text", "boxes": [[0, 0, 1, 1]], "snippet": ""},
                {"page": 428, "kind": "text", "boxes": [[0, 0, 1, 1]], "snippet": ""}]
    assert _renumber(raw, grounded)[0] == expected


def test_parse_json_variants():
    from app.llm import LLMError, parse_json

    assert parse_json('<thought>hmm</thought>```json\n{"found": true}\n```') == {"found": True}
    assert parse_json("found: false, answer: Not in these pages.")["found"] is False
    with pytest.raises(LLMError):
        parse_json("no json at all")


def test_table_cells_are_shown_as_rows():
    from app.answer import _display_rows, _page_block

    def cell(text, x0, y0):
        return {"text": text, "box": [x0, y0, x0 + 0.1, y0 + 0.012]}

    lines = [cell("Intro paragraph", 0.1, 0.05)]
    for r, (gpio, fn) in enumerate([("0", "UART0 TX"), ("1", "UART0 RX"), ("12", "UART0 TX")]):
        y = 0.3 + r * 0.03
        lines += [cell(gpio, 0.1, y), cell("SPI0 RX", 0.3, y), cell(fn, 0.5, y)]
    page = {"page_no": 13, "lines": lines, "source": "text",
            "figures": [{"id": "F1", "box": [0.05, 0.25, 0.95, 0.45], "caption": None,
                         "labels": [ln["text"] for ln in lines[1:]] + ["x"] * 4}]}
    rows = _display_rows(page)
    assert [len(m) for _, m in rows] == [1, 3, 3, 3]
    block = _page_block(page, False)
    assert "L8 12 | SPI0 RX | UART0 TX" in block
