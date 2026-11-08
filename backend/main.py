from dotenv import load_dotenv

load_dotenv()  # must run before importing modules that read env vars

import json
import sqlite3

import anthropic
import httpx
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import db
import llm
import pdf
from search import search_papers

app = FastAPI(title="AI Research Assistant")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    db.init_db()


class PaperIn(BaseModel):
    external_id: str | None = None
    title: str
    authors: list[str] = []
    year: int | None = None
    abstract: str | None = None
    url: str | None = None
    pdf_url: str | None = None


class AskIn(BaseModel):
    question: str
    history: list[dict] = []


def get_paper_row(paper_id: int) -> sqlite3.Row:
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Paper not found")
    return row


def llm_call(fn, *args):
    try:
        return fn(*args)
    except anthropic.AuthenticationError:
        raise HTTPException(502, "Anthropic API key was rejected. Check ANTHROPIC_API_KEY in backend/.env")
    except anthropic.APIError as e:
        raise HTTPException(502, f"LLM request failed: {e}")


def text_stream(chunks, on_done=None) -> StreamingResponse:
    """Stream LLM text to the client as plain text.

    The first chunk is pulled before the response starts, so a rejected API key or
    an upstream failure becomes a normal HTTP error instead of a half-open stream.
    `on_done` receives the full text once the stream finishes normally.
    """
    chunks = iter(chunks)
    first = llm_call(next, chunks, "")

    def body():
        parts = [first]
        yield first
        try:
            for chunk in chunks:
                parts.append(chunk)
                yield chunk
        except anthropic.APIError as e:
            yield f"\n\n*(Stream interrupted: {e})*"
            return
        if on_done:
            on_done("".join(parts))

    return StreamingResponse(
        body(),
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------- search ----------
@app.get("/api/search")
def search(q: str, limit: int = Query(10, ge=1)):
    if not q.strip():
        raise HTTPException(400, "Query is empty")
    try:
        return search_papers(q.strip(), min(limit, 25))
    except httpx.HTTPError as e:
        raise HTTPException(
            502,
            "Paper search is temporarily unavailable (Semantic Scholar is rate-limited and "
            f"arXiv didn't respond: {type(e).__name__}). Please try again in a moment.",
        )


# ---------- library ----------
@app.get("/api/library")
def list_library():
    with db.get_conn() as conn:
        rows = conn.execute("SELECT * FROM papers ORDER BY created_at DESC, id DESC").fetchall()
    return [db.row_to_paper(r) for r in rows]


@app.get("/api/library/{paper_id}")
def get_paper(paper_id: int):
    return db.row_to_paper(get_paper_row(paper_id))


@app.post("/api/library")
def save_paper(p: PaperIn):
    if p.external_id:
        with db.get_conn() as conn:
            existing = conn.execute(
                "SELECT * FROM papers WHERE external_id = ?", (p.external_id,)
            ).fetchone()
        if existing:
            return db.row_to_paper(existing)

    # Best effort: fetch the PDF so summaries/Q&A can use the full text.
    full_text = None
    if p.pdf_url:
        pdf_bytes = pdf.download_pdf(p.pdf_url)
        if pdf_bytes:
            try:
                full_text = pdf.extract_text(pdf_bytes) or None
            except Exception:
                full_text = None

    try:
        with db.get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO papers (external_id, title, authors, year, abstract, url, source, full_text)"
                " VALUES (?, ?, ?, ?, ?, ?, 'search', ?)",
                (p.external_id, p.title, json.dumps(p.authors), p.year, p.abstract, p.url, full_text),
            )
            paper_id = cur.lastrowid
    except sqlite3.IntegrityError:
        # A simultaneous request saved the same paper first; saving is idempotent.
        with db.get_conn() as conn:
            existing = conn.execute(
                "SELECT * FROM papers WHERE external_id = ?", (p.external_id,)
            ).fetchone()
        if existing is None:
            raise
        return db.row_to_paper(existing)
    return db.row_to_paper(get_paper_row(paper_id))


@app.delete("/api/library/{paper_id}")
def delete_paper(paper_id: int):
    get_paper_row(paper_id)
    with db.get_conn() as conn:
        conn.execute("DELETE FROM papers WHERE id = ?", (paper_id,))
    return {"deleted": paper_id}


# ---------- upload ----------
@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)):
    data = await file.read()
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "That file is not a PDF")
    try:
        text = pdf.extract_text(data)
        first = pdf.first_page_text(data)
    except Exception as e:
        raise HTTPException(400, f"Could not read PDF: {e}")
    if not text:
        raise HTTPException(400, "No extractable text (scanned PDFs are not supported)")

    meta = llm_call(llm.extract_metadata, first)
    title = meta["title"] or (file.filename or "Untitled").removesuffix(".pdf")
    with db.get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO papers (title, authors, year, abstract, source, full_text)"
            " VALUES (?, ?, ?, ?, 'upload', ?)",
            (title, json.dumps(meta["authors"]), meta["year"], meta["abstract"], text),
        )
        paper_id = cur.lastrowid
    return db.row_to_paper(get_paper_row(paper_id))


# ---------- LLM features ----------
@app.post("/api/library/{paper_id}/summarize")
def summarize_paper(paper_id: int, refresh: bool = False):
    row = get_paper_row(paper_id)
    if row["summary"] and not refresh:
        return {"summary": row["summary"], "cached": True}
    paper = db.row_to_paper(row, include_text=True)
    summary = llm_call(llm.summarize, paper)
    with db.get_conn() as conn:
        conn.execute("UPDATE papers SET summary = ? WHERE id = ?", (summary, paper_id))
    return {"summary": summary, "cached": False}


@app.post("/api/library/{paper_id}/ask")
def ask_paper(paper_id: int, body: AskIn):
    if not body.question.strip():
        raise HTTPException(400, "Question is empty")
    paper = db.row_to_paper(get_paper_row(paper_id), include_text=True)
    return {"answer": llm_call(llm.answer, paper, body.question.strip(), body.history)}


# Streaming variants: same behavior, but text arrives as it is generated.
@app.post("/api/library/{paper_id}/summarize/stream")
def summarize_paper_stream(paper_id: int, refresh: bool = False):
    row = get_paper_row(paper_id)
    if row["summary"] and not refresh:
        return text_stream([row["summary"]])

    def save(summary: str) -> None:
        with db.get_conn() as conn:
            conn.execute("UPDATE papers SET summary = ? WHERE id = ?", (summary, paper_id))

    paper = db.row_to_paper(row, include_text=True)
    return text_stream(llm.stream_summary(paper), on_done=save)


@app.post("/api/library/{paper_id}/ask/stream")
def ask_paper_stream(paper_id: int, body: AskIn):
    if not body.question.strip():
        raise HTTPException(400, "Question is empty")
    paper = db.row_to_paper(get_paper_row(paper_id), include_text=True)
    return text_stream(llm.stream_answer(paper, body.question.strip(), body.history))
