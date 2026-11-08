from conftest import auth_error
from helpers import blank_pdf, make_pdf

META = '{"title": "Sparse Widget Routing", "authors": ["Dana Okafor"], "year": 2024, "abstract": "We route widgets."}'


def upload(client, data, name="paper.pdf"):
    return client.post("/api/upload", files={"file": (name, data, "application/pdf")})


def test_upload_extracts_metadata_with_llm(client, fake_llm):
    fake_llm.reply = META
    response = upload(client, make_pdf("Sparse Widget Routing\nDana Okafor\n2024"))
    assert response.status_code == 200
    paper = response.json()
    assert paper["title"] == "Sparse Widget Routing"
    assert paper["authors"] == ["Dana Okafor"]
    assert paper["year"] == 2024
    assert paper["abstract"] == "We route widgets."
    assert paper["source"] == "upload"
    assert paper["has_full_text"] is True


def test_uploaded_paper_is_in_the_library(client, fake_llm):
    fake_llm.reply = META
    upload(client, make_pdf("some text"))
    assert len(client.get("/api/library").json()) == 1


def test_upload_sends_pdf_text_to_the_llm(client, fake_llm):
    fake_llm.reply = META
    upload(client, make_pdf("distinctive first page marker"))
    assert "distinctive first page marker" in fake_llm.calls[-1]["messages"][0]["content"]


def test_upload_rejects_non_pdf(client):
    response = upload(client, b"just some text", name="notes.pdf")
    assert response.status_code == 400
    assert "not a PDF" in response.json()["detail"]


def test_upload_rejects_pdf_without_text(client):
    response = upload(client, blank_pdf())
    assert response.status_code == 400
    assert "No extractable text" in response.json()["detail"]


def test_upload_rejects_corrupt_pdf(client):
    assert upload(client, b"%PDF-1.4 this is not really a pdf").status_code == 400


def test_upload_falls_back_to_filename_when_no_title_found(client, fake_llm):
    fake_llm.reply = '{"title": "", "authors": [], "year": null, "abstract": ""}'
    paper = upload(client, make_pdf("text"), name="my-notes.pdf").json()
    assert paper["title"] == "my-notes"


def test_upload_reports_502_when_llm_key_is_rejected(client, fake_llm):
    fake_llm.error = auth_error()
    response = upload(client, make_pdf("text"))
    assert response.status_code == 502
    assert "API key" in response.json()["detail"]
    assert client.get("/api/library").json() == []


def test_upload_requires_a_file(client):
    assert client.post("/api/upload").status_code == 422
