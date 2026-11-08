import httpx

import db
from helpers import PAPER, make_pdf


def test_library_starts_empty(client):
    assert client.get("/api/library").json() == []


def test_save_paper_stores_metadata(client):
    saved = client.post("/api/library", json=PAPER).json()
    assert saved["title"] == "Sparse Widget Routing"
    assert saved["authors"] == ["Dana Okafor", "Lee Whitfield"]
    assert saved["year"] == 2024
    assert saved["source"] == "search"
    assert saved["has_full_text"] is False


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


def test_get_unknown_paper_is_404(client):
    assert client.get("/api/library/999").status_code == 404


def test_delete_removes_paper(client, saved_paper):
    assert client.delete(f"/api/library/{saved_paper['id']}").json() == {"deleted": saved_paper["id"]}
    assert client.get("/api/library").json() == []


def test_delete_unknown_paper_is_404(client):
    assert client.delete("/api/library/999").status_code == 404


def test_saved_papers_persist_in_the_database_file(client, saved_paper):
    # A brand-new connection (as after an app restart) still sees the paper.
    with db.get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0] == 1
