import httpx
import pytest
import respx

import search

S2 = search.S2_URL
ARXIV = search.ARXIV_URL

ATOM_ONE = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <published>2017-06-12T17:57:34Z</published>
    <title>Attention Is
      All You Need</title>
    <summary>The dominant   sequence
      transduction models.</summary>
    <author><name>Ashish Vaswani</name></author>
    <author><name>Noam Shazeer</name></author>
  </entry>
</feed>"""
ATOM_EMPTY = '<feed xmlns="http://www.w3.org/2005/Atom"></feed>'


def s2_body(*papers):
    return {"data": list(papers)}


S2_PAPER = {
    "paperId": "p1",
    "title": "A Paper",
    "authors": [{"name": "Ann"}, {"name": "Bob"}],
    "year": 2021,
    "abstract": "An abstract.",
    "url": "https://www.semanticscholar.org/paper/p1",
    "openAccessPdf": {"url": "https://example.org/p1.pdf"},
}


def test_semantic_scholar_maps_fields(mock_http):
    mock_http.get(S2).respond(json=s2_body(S2_PAPER))
    [paper] = search.search_semantic_scholar("x", 5)
    assert paper == {
        "external_id": "s2:p1",
        "title": "A Paper",
        "authors": ["Ann", "Bob"],
        "year": 2021,
        "abstract": "An abstract.",
        "url": "https://www.semanticscholar.org/paper/p1",
        "pdf_url": "https://example.org/p1.pdf",
    }


def test_semantic_scholar_empty_pdf_url_becomes_none(mock_http):
    mock_http.get(S2).respond(json=s2_body({**S2_PAPER, "openAccessPdf": {"url": ""}}))
    assert search.search_semantic_scholar("x", 5)[0]["pdf_url"] is None


def test_semantic_scholar_missing_pdf_and_title(mock_http):
    mock_http.get(S2).respond(json=s2_body({"paperId": "p2", "openAccessPdf": None}))
    paper = search.search_semantic_scholar("x", 5)[0]
    assert paper["pdf_url"] is None
    assert paper["title"] == "(untitled)"


def test_semantic_scholar_sends_api_key_when_configured(mock_http, monkeypatch):
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "secret-key")
    route = mock_http.get(S2).respond(json=s2_body())
    search.search_semantic_scholar("x", 5)
    assert route.calls.last.request.headers["x-api-key"] == "secret-key"


def test_semantic_scholar_omits_api_key_when_absent(mock_http):
    route = mock_http.get(S2).respond(json=s2_body())
    search.search_semantic_scholar("x", 5)
    assert "x-api-key" not in route.calls.last.request.headers


def test_semantic_scholar_retries_once_on_429(mock_http):
    route = mock_http.get(S2).mock(
        side_effect=[httpx.Response(429), httpx.Response(200, json=s2_body(S2_PAPER))]
    )
    assert len(search.search_semantic_scholar("x", 5)) == 1
    assert route.call_count == 2


def test_semantic_scholar_gives_up_after_two_429s(mock_http):
    route = mock_http.get(S2).respond(429)
    with pytest.raises(httpx.HTTPStatusError):
        search.search_semantic_scholar("x", 5)
    assert route.call_count == 2


def test_arxiv_parses_atom_entry(mock_http):
    mock_http.get(ARXIV).respond(text=ATOM_ONE)
    [paper] = search.search_arxiv("attention", 5)
    assert paper["external_id"] == "arxiv:1706.03762v7"
    assert paper["title"] == "Attention Is All You Need"
    assert paper["abstract"] == "The dominant sequence transduction models."
    assert paper["authors"] == ["Ashish Vaswani", "Noam Shazeer"]
    assert paper["year"] == 2017
    assert paper["pdf_url"] == "https://arxiv.org/pdf/1706.03762v7"


def test_arxiv_requires_all_terms_first(mock_http):
    route = mock_http.get(ARXIV).respond(text=ATOM_ONE)
    search.search_arxiv("duck db", 5)
    assert route.calls.last.request.url.params["search_query"] == "all:duck AND all:db"


def test_arxiv_falls_back_to_any_term_when_strict_query_is_empty(mock_http):
    route = mock_http.get(ARXIV).mock(
        side_effect=[httpx.Response(200, text=ATOM_EMPTY), httpx.Response(200, text=ATOM_ONE)]
    )
    assert len(search.search_arxiv("duck db", 5)) == 1
    assert route.calls.last.request.url.params["search_query"] == "all:duck OR all:db"


def test_arxiv_single_term_does_not_retry_with_or(mock_http):
    route = mock_http.get(ARXIV).respond(text=ATOM_EMPTY)
    assert search.search_arxiv("duckdb", 5) == []
    assert route.call_count == 1


def test_arxiv_retries_after_a_failure(mock_http):
    route = mock_http.get(ARXIV).mock(
        side_effect=[httpx.ConnectTimeout("slow"), httpx.Response(200, text=ATOM_ONE)]
    )
    assert len(search.search_arxiv("attention", 5)) == 1
    assert route.call_count == 2


def test_arxiv_raises_after_exhausting_retries(mock_http):
    mock_http.get(ARXIV).mock(side_effect=httpx.ConnectTimeout("slow"))
    with pytest.raises(httpx.HTTPError):
        search.search_arxiv("attention", 5)


def test_search_papers_prefers_semantic_scholar(mock_http):
    mock_http.get(S2).respond(json=s2_body(S2_PAPER))
    out = search.search_papers("x")
    assert out["provider"] == "semantic_scholar"
    assert len(out["results"]) == 1


def test_search_papers_falls_back_to_arxiv(mock_http):
    mock_http.get(S2).respond(429)
    mock_http.get(ARXIV).respond(text=ATOM_ONE)
    out = search.search_papers("x")
    assert out["provider"] == "arxiv"
    assert out["results"][0]["external_id"].startswith("arxiv:")


def test_search_papers_raises_when_both_fail(mock_http):
    mock_http.get(S2).respond(500)
    mock_http.get(ARXIV).mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(httpx.HTTPError):
        search.search_papers("x")


def test_throttle_spaces_requests_apart(monkeypatch):
    clock = {"now": 100.0, "slept": []}

    class FakeTime:
        @staticmethod
        def monotonic():
            return clock["now"]

        @staticmethod
        def sleep(seconds):
            clock["slept"].append(seconds)
            clock["now"] += seconds

    monkeypatch.setattr(search, "time", FakeTime)
    monkeypatch.setattr(search, "S2_MIN_INTERVAL", 1.1)
    monkeypatch.setattr(search, "_s2_last_call", 0.0)
    search._s2_throttle()  # long since the last call: no wait
    search._s2_throttle()  # immediately after: must wait the full interval
    assert clock["slept"] == [pytest.approx(1.1)]
