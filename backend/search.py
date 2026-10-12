"""Paper search via Semantic Scholar, falling back to arXiv when rate-limited."""
import os
import time
import xml.etree.ElementTree as ET

import httpx

S2_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
S2_FIELDS = "title,authors,year,abstract,url,openAccessPdf"
ARXIV_URL = "https://export.arxiv.org/api/query"
ATOM = {"a": "http://www.w3.org/2005/Atom"}
S2_TIMEOUT = 10
S2_ATTEMPTS = 2
S2_RETRY_DELAY = 1.2  # seconds; just over the 1 request/second limit
ARXIV_TIMEOUT = 30  # arXiv's API is often slow (10s+ is common)
ARXIV_ATTEMPTS = 2


def search_semantic_scholar(query: str, limit: int) -> list[dict]:
    headers = {}
    if key := os.getenv("SEMANTIC_SCHOLAR_API_KEY"):
        headers["x-api-key"] = key
    for attempt in range(S2_ATTEMPTS):
        resp = httpx.get(
            S2_URL,
            params={"query": query, "limit": limit, "fields": S2_FIELDS},
            headers=headers,
            timeout=S2_TIMEOUT,
        )
        # The key's rate limit is about 1 request/second, so a lone 429 usually
        # clears after a short wait; retry once before falling back to arXiv.
        if resp.status_code == 429 and attempt < S2_ATTEMPTS - 1:
            time.sleep(S2_RETRY_DELAY)
            continue
        break
    resp.raise_for_status()
    results = []
    for p in resp.json().get("data", []):
        pdf = (p.get("openAccessPdf") or {}).get("url") or None
        results.append(
            {
                "external_id": f"s2:{p['paperId']}",
                "title": p.get("title") or "(untitled)",
                "authors": [a["name"] for a in p.get("authors", []) if a.get("name")],
                "year": p.get("year"),
                "abstract": p.get("abstract"),
                "url": p.get("url"),
                "pdf_url": pdf,
            }
        )
    return results


def search_arxiv(query: str, limit: int) -> list[dict]:
    terms = [f"all:{t}" for t in query.split()]
    # Prefer results matching every term; if that finds nothing (e.g. "duck db"),
    # fall back to matching any term rather than returning an empty page.
    results = _arxiv_fetch(" AND ".join(terms), limit)
    if not results and len(terms) > 1:
        results = _arxiv_fetch(" OR ".join(terms), limit)
    return results


def _arxiv_fetch(search_query: str, limit: int) -> list[dict]:
    params = {"search_query": search_query, "max_results": limit}
    for attempt in range(ARXIV_ATTEMPTS):
        try:
            resp = httpx.get(ARXIV_URL, params=params, timeout=ARXIV_TIMEOUT, follow_redirects=True)
            resp.raise_for_status()
            break
        except httpx.HTTPError:
            if attempt == ARXIV_ATTEMPTS - 1:
                raise
    root = ET.fromstring(resp.text)
    results = []
    for entry in root.findall("a:entry", ATOM):
        abs_url = entry.findtext("a:id", default="", namespaces=ATOM).strip()
        arxiv_id = abs_url.rsplit("/abs/", 1)[-1]
        published = entry.findtext("a:published", default="", namespaces=ATOM)
        results.append(
            {
                "external_id": f"arxiv:{arxiv_id}",
                "title": " ".join(entry.findtext("a:title", default="", namespaces=ATOM).split()),
                "authors": [
                    a.findtext("a:name", default="", namespaces=ATOM)
                    for a in entry.findall("a:author", ATOM)
                ],
                "year": int(published[:4]) if published[:4].isdigit() else None,
                "abstract": " ".join(
                    entry.findtext("a:summary", default="", namespaces=ATOM).split()
                ),
                "url": abs_url,
                "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
            }
        )
    return results


def search_papers(query: str, limit: int = 10) -> dict:
    """Returns {"provider": ..., "results": [...]}."""
    try:
        return {"provider": "semantic_scholar", "results": search_semantic_scholar(query, limit)}
    except httpx.HTTPError:
        # Typically a 429 without an API key; arXiv needs no key.
        return {"provider": "arxiv", "results": search_arxiv(query, limit)}
