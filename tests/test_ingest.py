import sqlite3
from pathlib import Path

import pytest

from personal_ai_brain.ingest import ingest_file, ingest_path

from .conftest import CORPUS


def counts(conn: sqlite3.Connection) -> tuple[int, int, int]:
    docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    fts = conn.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0]
    return docs, chunks, fts


def test_reingesting_unchanged_files_is_a_no_op(conn: sqlite3.Connection) -> None:
    first = ingest_path(conn, CORPUS)
    before = counts(conn)
    second = ingest_path(conn, CORPUS)
    assert {r.status for r in first} == {"added"}
    assert {r.status for r in second} == {"unchanged"}
    assert counts(conn) == before


def test_changed_file_replaces_its_chunks(conn: sqlite3.Connection, tmp_path: Path) -> None:
    doc = tmp_path / "note.md"
    doc.write_text("# Old\n\nThe pressure limit is 4 bar.")
    ingest_file(conn, doc)
    doc.write_text("# New\n\nThe pressure limit is 6 bar.\n\nValves are checked weekly.")
    result = ingest_file(conn, doc)

    assert result.status == "updated"
    docs, chunks, fts = counts(conn)
    assert (docs, chunks, fts) == (1, 1, 1)  # no orphaned chunk or index rows
    row = conn.execute("SELECT d.title, c.text FROM chunks c JOIN documents d").fetchone()
    assert row["title"] == "New"
    assert "6 bar" in row["text"] and "4 bar" not in row["text"]


def test_pdf_keeps_page_numbers(conn: sqlite3.Connection) -> None:
    ingest_file(conn, CORPUS / "pump-station-maintenance.pdf")
    pages = [r[0] for r in conn.execute("SELECT page FROM chunks ORDER BY ordinal")]
    assert pages == [1, 2, 3, 4]


def test_text_files_have_no_page(conn: sqlite3.Connection) -> None:
    ingest_file(conn, CORPUS / "concrete-curing-lab-report.txt")
    assert {r[0] for r in conn.execute("SELECT page FROM chunks")} == {None}


def test_markdown_title_comes_from_h1(conn: sqlite3.Connection) -> None:
    ingest_file(conn, CORPUS / "deploy-runbook.md")
    title = conn.execute("SELECT title FROM documents").fetchone()[0]
    assert title == "Runbook: Deploying the Checkout Service"


def test_unsupported_file_type(conn: sqlite3.Connection, tmp_path: Path) -> None:
    other = tmp_path / "sheet.xlsx"
    other.write_bytes(b"not really")
    with pytest.raises(ValueError, match="unsupported"):
        ingest_path(conn, other)
