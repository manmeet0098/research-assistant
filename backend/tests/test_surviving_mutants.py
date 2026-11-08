"""Tests aimed at fault classes that the mutation run showed the earlier suite could not detect."""
from types import SimpleNamespace

import httpx
import pytest

import llm
import pdf
import search
from helpers import PAPER, make_pdf

PAPER_TEXT = {"title": "T", "abstract": "A", "full_text": "BODY"}


# ---- the exact request sent to Claude (HW1's cut-off bug was a bad max_tokens) ----
@pytest.mark.parametrize(
    "call",
    [
        lambda: llm.summarize(PAPER_TEXT),
        lambda: list(llm.stream_summary(PAPER_TEXT)),
        lambda: llm.answer(PAPER_TEXT, "q"),
        lambda: list(llm.stream_answer(PAPER_TEXT, "q")),
        lambda: llm.extract_metadata("first page"),
    ],
    ids=["summarize", "stream_summary", "answer", "stream_answer", "extract_metadata"],
)
def test_every_claude_request_is_fully_specified(fake_llm, call):
    fake_llm.reply = "{}"
    call()
    sent = fake_llm.calls[-1]
    assert sent["model"] == llm.MODEL
    assert isinstance(sent["system"], str) and sent["system"]
    assert sent["messages"] and sent["messages"][-1]["role"] == "user"
    assert sent["max_tokens"] >= 1000  # generous enough for a full summary


def test_summary_budget_covers_the_requested_length(fake_llm):
    llm.summarize(PAPER_TEXT)
    # 350 words is about 500 tokens; leave real headroom so summaries are never cut off.
    assert fake_llm.calls[-1]["max_tokens"] >= 1500


# ---- metadata extraction ----
def test_extract_metadata_handles_multiline_json(fake_llm):
    fake_llm.reply = '{\n  "title": "Multi",\n  "authors": ["A"],\n  "year": 2020,\n  "abstract": "line one\\nline two"\n}'
    assert llm.extract_metadata("page")["title"] == "Multi"


def test_extract_metadata_without_json_returns_empty_fields(fake_llm):
    fake_llm.reply = "Sorry, I cannot do that."
    assert llm.extract_metadata("page") == {"title": "", "authors": [], "year": None, "abstract": ""}


def test_abstract_only_paper_without_an_abstract_is_marked(fake_llm):
    llm.summarize({"title": "T", "abstract": None, "full_text": None})
    assert "(none)" in fake_llm.calls[-1]["messages"][0]["content"]


# ---- streaming responses ----
def test_stream_response_headers_allow_live_text(client, fake_llm, saved_paper):
    fake_llm.chunks = ["a", "b"]
    response = client.post(f"/api/library/{saved_paper['id']}/ask/stream", json={"question": "q"})
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"


def test_empty_llm_stream_is_a_valid_empty_response(client, fake_llm, saved_paper):
    fake_llm.chunks = []
    response = client.post(f"/api/library/{saved_paper['id']}/ask/stream", json={"question": "q"})
    assert response.status_code == 200
    assert response.text == ""


def test_stream_error_message_names_the_failure(client, fake_llm, saved_paper):
    fake_llm.chunks = ["ok ", "never sent"]
    fake_llm.error_after = 1
    text = client.post(f"/api/library/{saved_paper['id']}/ask/stream", json={"question": "q"}).text
    assert text.startswith("ok ")
    assert "Stream interrupted: Connection error." in text


def test_rejected_key_message_tells_the_user_what_to_check(client, fake_llm, saved_paper):
    from conftest import auth_error

    fake_llm.error = auth_error()
    detail = client.post(f"/api/library/{saved_paper['id']}/ask", json={"question": "q"}).json()["detail"]
    assert "ANTHROPIC_API_KEY" in detail


# ---- PDF handling ----
class StubDoc:
    def __init__(self, pages):
        self.pages = pages
        self.page_count = len(pages)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __getitem__(self, i):
        return SimpleNamespace(get_text=lambda: self.pages[i])

    def __iter__(self):
        return (SimpleNamespace(get_text=lambda t=t: t) for t in self.pages)


def stub_pages(monkeypatch, *pages):
    monkeypatch.setattr(pdf.pymupdf, "open", lambda **kwargs: StubDoc(list(pages)))


def test_pages_are_separated_when_extracting_text(monkeypatch):
    stub_pages(monkeypatch, "page one", "page two")
    assert pdf.extract_text(b"x") == "page one\npage two"


def test_first_page_only_when_it_is_long_enough(monkeypatch):
    stub_pages(monkeypatch, "a" * 1500, "SECOND")
    assert "SECOND" not in pdf.first_page_text(b"x")


def test_second_page_added_just_below_the_threshold(monkeypatch):
    stub_pages(monkeypatch, "a" * 1499, "SECOND")
    assert "SECOND" in pdf.first_page_text(b"x")


def test_first_page_text_defaults_to_6000_characters(monkeypatch):
    stub_pages(monkeypatch, "a" * 10_000)
    assert len(pdf.first_page_text(b"x")) == 6000


def test_empty_document_yields_empty_first_page(monkeypatch):
    stub_pages(monkeypatch)
    assert pdf.first_page_text(b"x") == ""


def test_download_follows_redirects(mock_http):
    data = make_pdf("redirected")
    mock_http.get("https://example.org/old.pdf").respond(302, headers={"Location": "https://example.org/new.pdf"})
    mock_http.get("https://example.org/new.pdf").respond(content=data)
    assert pdf.download_pdf("https://example.org/old.pdf") == data


def test_download_has_a_timeout(mock_http):
    route = mock_http.get("https://example.org/p.pdf").respond(content=make_pdf("x"))
    pdf.download_pdf("https://example.org/p.pdf")
    assert route.calls.last.request.extensions["timeout"]["read"] == 30


def test_download_exactly_at_the_size_limit_is_accepted(mock_http, monkeypatch):
    data = make_pdf("x")
    monkeypatch.setattr(pdf, "MAX_DOWNLOAD_BYTES", len(data))
    mock_http.get("https://example.org/p.pdf").respond(content=data)
    assert pdf.download_pdf("https://example.org/p.pdf") == data


# ---- search throttle ----
@pytest.mark.parametrize("interval", [0.5, 1.1])
def test_throttle_waits_the_configured_interval(monkeypatch, interval):
    slept = []
    clock = {"now": 100.0}

    class FakeTime:
        monotonic = staticmethod(lambda: clock["now"])

        @staticmethod
        def sleep(seconds):
            slept.append(seconds)
            clock["now"] += seconds

    monkeypatch.setattr(search, "time", FakeTime)
    monkeypatch.setattr(search, "S2_MIN_INTERVAL", interval)
    monkeypatch.setattr(search, "_s2_last_call", 0.0)
    search._s2_throttle()
    search._s2_throttle()
    assert slept == [pytest.approx(interval)]


def test_throttle_does_not_wait_once_the_interval_has_passed(monkeypatch):
    slept = []
    clock = {"now": 100.0}

    class FakeTime:
        monotonic = staticmethod(lambda: clock["now"])
        sleep = staticmethod(slept.append)

    monkeypatch.setattr(search, "time", FakeTime)
    monkeypatch.setattr(search, "S2_MIN_INTERVAL", 1.1)
    monkeypatch.setattr(search, "_s2_last_call", 0.0)
    search._s2_throttle()
    clock["now"] += 5
    search._s2_throttle()
    assert slept == []


def test_api_key_header_is_sent_to_semantic_scholar(mock_http, monkeypatch):
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "k")
    route = mock_http.get(search.S2_URL).respond(json={"data": []})
    search.search_semantic_scholar("x", 5)
    assert route.calls.last.request.headers["x-api-key"] == "k"
