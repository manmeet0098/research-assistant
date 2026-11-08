import sqlite3

import httpx
import pytest

import db
from helpers import PAPER, make_pdf


def test_library_starts_empty(client):
    assert client.get("/api/library").json() == []


def test_save_paper_stores_metadata(client):
    saved = client.post("/api/library", json=PAPER).json()
    assert saved == {
        "id": saved["id"],
        "external_id": "s2:abc123",
        "title": "Sparse Widget Routing",
        "authors": ["Dana Okafor", "Lee Whitfield"],
        "year": 2024,
        "abstract": "We route widgets sparsely.",
        "url": "https://example.org/paper",
        "source": "search",
        "has_full_text": False,
        "summary": None,
        "created_at": saved["created_at"],
    }
    assert saved["created_at"]  # timestamp is set


def test_saved_paper_appears_in_library_and_by_id(client, saved_paper):
    assert [p["id"] for p in client.get("/api/library").json()] == [saved_paper["id"]]
    assert client.get(f"/api/library/{saved_paper['id']}").json()["title"] == PAPER["title"]


def test_saving_the_same_paper_twice_does_not_duplicate(client):
    first = client.post("/api/library", json=PAPER).json()
    second = client.post("/api/library", json=PAPER).json()
    assert first["id"] == second["id"]
    assert len(client.get("/api/library").json()) == 1


def test_save_downloads_pdf_text_when_available(client, mock_http):
    mock_http.get("https://example.org/p.pdf").respond(content=make_pdf("full text of the paper"))
    saved = client.post("/api/library", json={**PAPER, "pdf_url": "https://example.org/p.pdf"}).json()
    assert saved["has_full_text"] is True


def test_save_still_works_when_pdf_download_fails(client, mock_http):
    mock_http.get("https://example.org/p.pdf").mock(side_effect=httpx.ConnectError("down"))
    saved = client.post("/api/library", json={**PAPER, "pdf_url": "https://example.org/p.pdf"}).json()
    assert saved["has_full_text"] is False
    assert client.get("/api/library").json()[0]["title"] == PAPER["title"]


def test_save_requires_a_title(client):
    bad = {k: v for k, v in PAPER.items() if k != "title"}
    assert client.post("/api/library", json=bad).status_code == 422


def test_library_lists_newest_first(client):
    client.post("/api/library", json={**PAPER, "external_id": "s2:1", "title": "first"})
    client.post("/api/library", json={**PAPER, "external_id": "s2:2", "title": "second"})
    assert [p["title"] for p in client.get("/api/library").json()] == ["second", "first"]


@pytest.mark.parametrize(
    "method, path, body",
    [
        ("get", "/api/library/999", None),
        ("delete", "/api/library/999", None),
        ("post", "/api/library/999/summarize", None),
        ("post", "/api/library/999/summarize/stream", None),
        ("post", "/api/library/999/ask", {"question": "q"}),
        ("post", "/api/library/999/ask/stream", {"question": "q"}),
    ],
)
def test_unknown_paper_is_404_on_every_route(client, method, path, body):
    response = client.request(method, path, json=body)
    assert response.status_code == 404
    assert response.json()["detail"] == "Paper not found"


def test_delete_removes_paper(client, saved_paper):
    assert client.delete(f"/api/library/{saved_paper['id']}").json() == {"deleted": saved_paper["id"]}
    assert client.get("/api/library").json() == []


def test_saved_papers_persist_in_the_database_file(client, saved_paper):
    # Read the file with an independent connection, as a restarted app would.
    raw = sqlite3.connect(db.DB_PATH)
    try:
        rows = raw.execute("SELECT title, authors FROM papers").fetchall()
    finally:
        raw.close()
    assert rows == [("Sparse Widget Routing", '["Dana Okafor", "Lee Whitfield"]')]


def test_save_survives_a_failed_text_extraction(client, mock_http):
    # Looks like a PDF (passes the download check) but cannot be parsed.
    mock_http.get("https://example.org/p.pdf").respond(content=b"%PDF-1.4 not really a pdf")
    saved = client.post("/api/library", json={**PAPER, "pdf_url": "https://example.org/p.pdf"}).json()
    assert saved["has_full_text"] is False


def test_startup_creates_the_schema_on_a_fresh_database(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import main

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "fresh.db")
    assert not (tmp_path / "fresh.db").exists()
    with TestClient(main.app) as fresh:  # entering the context runs startup
        assert fresh.get("/api/library").json() == []


def test_save_without_an_external_id_is_allowed(client):
    saved = client.post("/api/library", json={**PAPER, "external_id": None}).json()
    assert saved["external_id"] is None
    assert saved["title"] == PAPER["title"]
