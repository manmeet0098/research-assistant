import json
import sqlite3

import db


def insert(conn, **overrides):
    row = {
        "external_id": None,
        "title": "T",
        "authors": json.dumps(["A", "B"]),
        "year": 2020,
        "abstract": "abs",
        "url": "http://x",
        "source": "search",
        "full_text": None,
    }
    row.update(overrides)
    cur = conn.execute(
        "INSERT INTO papers (external_id, title, authors, year, abstract, url, source, full_text)"
        " VALUES (:external_id, :title, :authors, :year, :abstract, :url, :source, :full_text)",
        row,
    )
    return cur.lastrowid


def test_init_db_creates_papers_table():
    with db.get_conn() as conn:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    assert "papers" in tables


def test_init_db_is_idempotent():
    db.init_db()
    db.init_db()
    with db.get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0] == 0


def test_row_to_paper_decodes_authors_and_hides_text_by_default():
    with db.get_conn() as conn:
        pid = insert(conn, full_text="body text")
        row = conn.execute("SELECT * FROM papers WHERE id = ?", (pid,)).fetchone()
    paper = db.row_to_paper(row)
    assert paper["authors"] == ["A", "B"]
    assert paper["has_full_text"] is True
    assert "full_text" not in paper


def test_row_to_paper_can_include_text():
    with db.get_conn() as conn:
        pid = insert(conn, full_text="body text")
        row = conn.execute("SELECT * FROM papers WHERE id = ?", (pid,)).fetchone()
    assert db.row_to_paper(row, include_text=True)["full_text"] == "body text"


def test_has_full_text_false_when_missing():
    with db.get_conn() as conn:
        pid = insert(conn)
        row = conn.execute("SELECT * FROM papers WHERE id = ?", (pid,)).fetchone()
    assert db.row_to_paper(row)["has_full_text"] is False


def test_external_id_is_unique():
    with db.get_conn() as conn:
        insert(conn, external_id="s2:1")
        try:
            insert(conn, external_id="s2:1")
        except sqlite3.IntegrityError:
            return
    raise AssertionError("duplicate external_id was accepted")
