"""PDF text extraction and download helpers."""
import pymupdf
import httpx

MAX_DOWNLOAD_BYTES = 30 * 1024 * 1024


def extract_text(pdf_bytes: bytes) -> str:
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        return "\n".join(page.get_text() for page in doc).strip()


def first_page_text(pdf_bytes: bytes, max_chars: int = 6000) -> str:
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        text = doc[0].get_text() if doc.page_count else ""
        if len(text) < 1500 and doc.page_count > 1:  # short title page; include next page
            text += "\n" + doc[1].get_text()
    return text[:max_chars].strip()


def download_pdf(url: str) -> bytes | None:
    """Best-effort download; returns None on any failure or if it isn't a PDF."""
    try:
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError:
        return None
    if len(resp.content) > MAX_DOWNLOAD_BYTES or not resp.content.startswith(b"%PDF"):
        return None
    return resp.content
