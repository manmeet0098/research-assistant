import httpx

import search

PAPER = {
    "paperId": "p1",
    "title": "A Paper",
    "authors": [{"name": "Ann"}],
    "year": 2021,
    "abstract": "An abstract.",
    "url": "https://www.semanticscholar.org/paper/p1",
    "openAccessPdf": None,
}


def test_search_returns_provider_and_results(client, mock_http):
    mock_http.get(search.S2_URL).respond(json={"data": [PAPER]})
    body = client.get("/api/search", params={"q": "widgets"}).json()
    assert body["provider"] == "semantic_scholar"
    assert body["results"][0]["title"] == "A Paper"


def test_search_strips_the_query(client, mock_http):
    route = mock_http.get(search.S2_URL).respond(json={"data": []})
    client.get("/api/search", params={"q": "  widgets  "})
    assert route.calls.last.request.url.params["query"] == "widgets"


def test_search_empty_query_is_rejected(client):
    assert client.get("/api/search", params={"q": ""}).status_code == 400


def test_search_whitespace_query_is_rejected(client):
    assert client.get("/api/search", params={"q": "   "}).status_code == 400


def test_search_missing_query_is_rejected(client):
    assert client.get("/api/search").status_code == 422


def test_search_limit_is_capped_at_25(client, mock_http):
    route = mock_http.get(search.S2_URL).respond(json={"data": []})
    client.get("/api/search", params={"q": "x", "limit": 1000})
    assert route.calls.last.request.url.params["limit"] == "25"


def test_search_reports_502_when_both_providers_fail(client, mock_http):
    mock_http.get(search.S2_URL).respond(429)
    mock_http.get(search.ARXIV_URL).mock(side_effect=httpx.ConnectTimeout("slow"))
    response = client.get("/api/search", params={"q": "x"})
    assert response.status_code == 502
    assert "temporarily unavailable" in response.json()["detail"]
