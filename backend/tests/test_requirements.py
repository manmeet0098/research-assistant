"""Acceptance tests derived from the HW1 requirements (not from the implementation).

1. Search: results show title, authors, year, abstract and a link when available.
2. Save papers to a local library that persists and can be browsed.
3. Upload a PDF; extract title, authors, year and abstract so it renders like a search result.
4. Summarize a paper with an LLM based on its CONTENT, not just its title/metadata.
5. Ask natural-language questions about a selected paper.
"""
import pytest

import search
from helpers import PAPER, make_pdf

RESULT_FIELDS = {"title", "authors", "year", "abstract", "url"}

S2_ITEM = {
    "paperId": "p1",
    "title": "A Paper",
    "authors": [{"name": "Ann"}],
    "year": 2021,
    "abstract": "An abstract.",
    "url": "https://www.semanticscholar.org/paper/p1",
}
ATOM = """<feed xmlns="http://www.w3.org/2005/Atom"><entry>
<id>http://arxiv.org/abs/1706.03762v7</id><published>2017-06-12T00:00:00Z</published>
<title>Attention</title><summary>Abs.</summary><author><name>Ann</name></author></entry></feed>"""


# ---- 1. search ----
@pytest.mark.parametrize("provider", ["semantic_scholar", "arxiv"])
def test_every_search_result_has_the_required_fields(client, mock_http, provider):
    if provider == "semantic_scholar":
        mock_http.get(search.S2_URL).respond(json={"data": [S2_ITEM]})
    else:
        mock_http.get(search.S2_URL).respond(429)
        mock_http.get(search.ARXIV_URL).respond(text=ATOM)
    body = client.get("/api/search", params={"q": "x"}).json()
    assert body["provider"] == provider
    result = body["results"][0]
    assert RESULT_FIELDS <= result.keys()
    assert result["title"] and result["authors"] and result["year"] and result["abstract"] and result["url"]


# ---- 2. library ----
def test_library_can_be_browsed_after_saving_several_papers(client):
    for i in range(3):
        client.post("/api/library", json={**PAPER, "external_id": f"s2:{i}", "title": f"Paper {i}"})
    titles = {p["title"] for p in client.get("/api/library").json()}
    assert titles == {"Paper 0", "Paper 1", "Paper 2"}


def test_saved_paper_keeps_every_displayed_field(client):
    client.post("/api/library", json=PAPER)
    [shown] = client.get("/api/library").json()
    assert shown["title"] == PAPER["title"]
    assert shown["authors"] == PAPER["authors"]
    assert shown["year"] == PAPER["year"]
    assert shown["abstract"] == PAPER["abstract"]
    assert shown["url"] == PAPER["url"]


# ---- 3. upload ----
def test_uploaded_paper_renders_like_a_search_result(client, fake_llm):
    fake_llm.reply = '{"title": "T", "authors": ["A B"], "year": 2020, "abstract": "abs"}'
    uploaded = client.post("/api/upload", files={"file": ("p.pdf", make_pdf("text"), "application/pdf")}).json()
    saved = client.post("/api/library", json=PAPER).json()
    assert set(uploaded.keys()) == set(saved.keys())  # same shape, so the UI treats them alike
    # Newest first: the search-saved paper was added after the upload.
    assert [p["id"] for p in client.get("/api/library").json()] == [saved["id"], uploaded["id"]]


def test_upload_metadata_is_extracted_from_the_pdf_not_invented(client, fake_llm):
    fake_llm.reply = '{"title": "T", "authors": [], "year": null, "abstract": ""}'
    client.post("/api/upload", files={"file": ("p.pdf", make_pdf("Title line\nBody of the paper"), "application/pdf")})
    prompt = fake_llm.calls[-1]["messages"][0]["content"]
    assert "Title line" in prompt
    assert "never invent" in fake_llm.calls[-1]["system"]


# ---- 4. summary based on content ----
def test_summary_is_based_on_the_full_text_not_just_metadata(client, fake_llm, mock_http):
    mock_http.get("https://example.org/p.pdf").respond(content=make_pdf("UNIQUE-BODY-SENTENCE appears only in the body"))
    paper = client.post("/api/library", json={**PAPER, "pdf_url": "https://example.org/p.pdf"}).json()
    client.post(f"/api/library/{paper['id']}/summarize")
    assert "UNIQUE-BODY-SENTENCE" in fake_llm.calls[-1]["messages"][0]["content"]


def test_summary_of_an_abstract_only_paper_says_so(client, fake_llm, saved_paper):
    client.post(f"/api/library/{saved_paper['id']}/summarize")
    assert "abstract alone" in fake_llm.calls[-1]["system"]


# ---- 5. questions ----
def test_question_and_paper_content_reach_the_llm(client, fake_llm, mock_http):
    mock_http.get("https://example.org/p.pdf").respond(content=make_pdf("The dataset is WidgetBench."))
    paper = client.post("/api/library", json={**PAPER, "pdf_url": "https://example.org/p.pdf"}).json()
    client.post(f"/api/library/{paper['id']}/ask", json={"question": "Which dataset?"})
    call = fake_llm.calls[-1]
    assert "WidgetBench" in call["system"]
    assert call["messages"][-1] == {"role": "user", "content": "Which dataset?"}


def test_answers_only_use_the_selected_paper(client, fake_llm, mock_http):
    mock_http.get("https://example.org/a.pdf").respond(content=make_pdf("ALPHA-ONLY content"))
    mock_http.get("https://example.org/b.pdf").respond(content=make_pdf("BRAVO-ONLY content"))
    a = client.post("/api/library", json={**PAPER, "external_id": "s2:a", "pdf_url": "https://example.org/a.pdf"}).json()
    b = client.post("/api/library", json={**PAPER, "external_id": "s2:b", "pdf_url": "https://example.org/b.pdf"}).json()
    client.post(f"/api/library/{b['id']}/ask", json={"question": "q"})
    system = fake_llm.calls[-1]["system"]
    assert "BRAVO-ONLY" in system and "ALPHA-ONLY" not in system
    client.post(f"/api/library/{a['id']}/ask", json={"question": "q"})
    assert "ALPHA-ONLY" in fake_llm.calls[-1]["system"]


def test_the_model_is_told_not_to_guess(client, fake_llm, saved_paper):
    client.post(f"/api/library/{saved_paper['id']}/ask", json={"question": "q"})
    assert "instead of guessing" in fake_llm.calls[-1]["system"]
