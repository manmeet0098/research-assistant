import httpx

import pdf
from helpers import blank_pdf, make_pdf


def test_extract_text_reads_all_pages():
    text = pdf.extract_text(make_pdf("first page words", "second page words"))
    assert "first page words" in text
    assert "second page words" in text


def test_extract_text_of_blank_pdf_is_empty():
    assert pdf.extract_text(blank_pdf()) == ""


def test_first_page_text_is_truncated():
    data = make_pdf("word " * 400)
    assert len(pdf.first_page_text(data, max_chars=100)) <= 100


def test_first_page_text_includes_second_page_when_first_is_short():
    text = pdf.first_page_text(make_pdf("tiny title page", "abstract lives here"))
    assert "tiny title page" in text
    assert "abstract lives here" in text


def test_download_pdf_returns_bytes(mock_http):
    data = make_pdf("hello")
    mock_http.get("https://example.org/p.pdf").respond(content=data)
    assert pdf.download_pdf("https://example.org/p.pdf") == data


def test_download_pdf_returns_none_on_http_error(mock_http):
    mock_http.get("https://example.org/p.pdf").respond(404)
    assert pdf.download_pdf("https://example.org/p.pdf") is None


def test_download_pdf_returns_none_for_non_pdf_content(mock_http):
    mock_http.get("https://example.org/p.pdf").respond(content=b"<html>login</html>")
    assert pdf.download_pdf("https://example.org/p.pdf") is None


def test_download_pdf_returns_none_when_too_large(mock_http, monkeypatch):
    monkeypatch.setattr(pdf, "MAX_DOWNLOAD_BYTES", 10)
    mock_http.get("https://example.org/p.pdf").respond(content=make_pdf("hello"))
    assert pdf.download_pdf("https://example.org/p.pdf") is None


def test_download_pdf_returns_none_on_network_error(mock_http):
    mock_http.get("https://example.org/p.pdf").mock(side_effect=httpx.ConnectError("down"))
    assert pdf.download_pdf("https://example.org/p.pdf") is None
