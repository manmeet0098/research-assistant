"""PDF builders shared by the tests."""
import pymupdf


def make_pdf(*pages: str) -> bytes:
    """Build a small text PDF with one page per string."""
    doc = pymupdf.open()
    for text in pages:
        doc.new_page().insert_textbox(pymupdf.Rect(50, 50, 550, 750), text, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def blank_pdf() -> bytes:
    doc = pymupdf.open()
    doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


PAPER = {
    "external_id": "s2:abc123",
    "title": "Sparse Widget Routing",
    "authors": ["Dana Okafor", "Lee Whitfield"],
    "year": 2024,
    "abstract": "We route widgets sparsely.",
    "url": "https://example.org/paper",
    "pdf_url": None,
}
