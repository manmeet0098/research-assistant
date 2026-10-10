import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "library.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT UNIQUE,          -- e.g. "s2:<paperId>" or "arxiv:<id>"; NULL for uploads
    title TEXT NOT NULL,
    authors TEXT NOT NULL DEFAULT '[]',  -- JSON list of names
    year INTEGER,
    abstract TEXT,
    url TEXT,
    source TEXT NOT NULL,             -- 'search' or 'upload'
    full_text TEXT,                   -- extracted PDF text; NULL if unavailable
    summary TEXT,                     -- cached LLM summary
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def row_to_paper(row: sqlite3.Row, include_text: bool = False) -> dict:
    paper = {
        "id": row["id"],
        "external_id": row["external_id"],
        "title": row["title"],
        "authors": json.loads(row["authors"]),
        "year": row["year"],
        "abstract": row["abstract"],
        "url": row["url"],
        "source": row["source"],
        "has_full_text": bool(row["full_text"]),
        "summary": row["summary"],
        "created_at": row["created_at"],
    }
    if include_text:
        paper["full_text"] = row["full_text"]
    return paper
