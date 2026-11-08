"""Edge cases and failure modes, written against the INTENDED behaviour.

Tests marked xfail(strict=True) document confirmed bugs: they assert what the app
should do and currently fail. strict=True turns an unexpected pass (i.e. the bug being
fixed) into a failure, so the marker must be removed together with the fix.
"""
import gc
import warnings

import pytest

import db
import pdf
import search
from helpers import PAPER, make_pdf


def upload(client, data, name="paper.pdf"):
    return client.post("/api/upload", files={"file": (name, data, "application/pdf")})


# ---------- metadata extraction must be best-effort ----------
@pytest.mark.xfail(strict=True, reason="BUG-1: malformed JSON from the LLM crashes the upload (HTTP 500)")
def test_upload_survives_malformed_json_from_the_llm(lenient_client, fake_llm):
    fake_llm.reply = '{title: "no quotes", authors: [Ann]}'
    response = upload(lenient_client, make_pdf("some text"), name="paper.pdf")
    assert response.status_code == 200
    assert response.json()["title"] == "paper"  # falls back to the filename


@pytest.mark.xfail(strict=True, reason="BUG-2: wrongly typed metadata fields crash the upload or corrupt authors")
@pytest.mark.parametrize(
    "reply, acceptable_authors",
    [
        ('{"title": 123, "authors": ["A"], "year": 2020, "abstract": "x"}', [["A"]]),
        ('{"title": "T", "authors": ["A"], "year": 2020, "abstract": 5}', [["A"]]),
        # A bare string must be kept whole (or dropped), never split into letters.
        ('{"title": "T", "authors": "Ann Smith", "year": 2020, "abstract": "x"}', [[], ["Ann Smith"]]),
    ],
    ids=["numeric-title", "numeric-abstract", "authors-as-string"],
)
def test_upload_tolerates_wrongly_typed_metadata(lenient_client, fake_llm, reply, acceptable_authors):
    fake_llm.reply = reply
    response = upload(lenient_client, make_pdf("some text"))
    assert response.status_code == 200
    paper = response.json()
    assert isinstance(paper["title"], str)
    assert isinstance(paper["abstract"], str)
    assert paper["authors"] in acceptable_authors


# ---------- input validation ----------
@pytest.mark.xfail(strict=True, reason="BUG-3: non-positive search limits are passed straight to the providers")
@pytest.mark.parametrize("limit", [0, -5])
def test_search_does_not_accept_a_non_positive_limit(client, mock_http, limit):
    route = mock_http.get(search.S2_URL).respond(json={"data": []})
    response = client.get("/api/search", params={"q": "x", "limit": limit})
    rejected = response.status_code in (400, 422)
    clamped = route.called and route.calls.last.request.url.params["limit"] == "1"
    assert rejected or clamped


# ---------- resources ----------
@pytest.mark.xfail(strict=True, reason="BUG-4: sqlite3 connections opened with `with db.get_conn()` are never closed")
def test_database_connections_are_closed(client, saved_paper):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ResourceWarning)
        client.get("/api/library")
        client.get(f"/api/library/{saved_paper['id']}")
        client.delete(f"/api/library/{saved_paper['id']}")
        gc.collect()
    leaks = [w for w in caught if issubclass(w.category, ResourceWarning) and "sqlite3" in str(w.message)]
    assert leaks == []


# ---------- races ----------
@pytest.mark.xfail(strict=True, reason="BUG-5: saving a paper twice at once hits the UNIQUE constraint (HTTP 500)")
def test_simultaneous_duplicate_save_is_idempotent(lenient_client, monkeypatch):
    def racing_download(url):
        # Another request saves the same paper after our duplicate check but before our INSERT.
        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO papers (external_id, title, authors, source) VALUES (?, ?, '[]', 'search')",
                (PAPER["external_id"], PAPER["title"]),
            )
        return None

    monkeypatch.setattr(pdf, "download_pdf", racing_download)
    response = lenient_client.post("/api/library", json={**PAPER, "pdf_url": "https://example.org/p.pdf"})
    assert response.status_code == 200
    assert len(lenient_client.get("/api/library").json()) == 1


# ---------- other failure modes that already behave correctly ----------
def test_empty_llm_reply_for_upload_falls_back_to_the_filename(client, fake_llm):
    fake_llm.reply = "I could not find any metadata."  # no JSON at all
    paper = upload(client, make_pdf("some text"), name="notes.pdf").json()
    assert paper["title"] == "notes"
    assert paper["authors"] == []


def test_search_survives_a_provider_returning_unexpected_markup(client, mock_http):
    mock_http.get(search.S2_URL).respond(500)
    mock_http.get(search.ARXIV_URL).respond(text="<feed xmlns='http://www.w3.org/2005/Atom'></feed>")
    body = client.get("/api/search", params={"q": "x"}).json()
    assert body == {"provider": "arxiv", "results": []}
