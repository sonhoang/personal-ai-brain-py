"""Read files into the library: extract text, chunk it, index it.

A document is identified by its absolute path. Its SHA-256 decides what
happens on re-ingest: same hash -> nothing to do; different hash -> the old
chunks are replaced in one transaction.
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pypdf import PdfReader

from .chunking import chunk_text

SUPPORTED_SUFFIXES = {".pdf", ".md", ".markdown", ".txt"}

Status = Literal["added", "updated", "unchanged", "empty"]


@dataclass(frozen=True)
class Page:
    number: int | None  # 1-based for PDFs, None for text files
    text: str


@dataclass(frozen=True)
class IngestResult:
    path: Path
    status: Status
    chunks: int


def ingest_path(conn: sqlite3.Connection, path: Path) -> list[IngestResult]:
    """Ingest a single file, or every supported file under a folder."""
    if path.is_dir():
        files = sorted(
            p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
        )
        return [ingest_file(conn, f) for f in files]
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError(f"unsupported file type: {path.suffix} (use .pdf, .md or .txt)")
    return [ingest_file(conn, path)]


def ingest_file(conn: sqlite3.Connection, path: Path) -> IngestResult:
    path = path.resolve()
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()

    existing = conn.execute(
        "SELECT id, sha256 FROM documents WHERE path = ?", (str(path),)
    ).fetchone()
    if existing and existing["sha256"] == digest:
        return IngestResult(path, "unchanged", 0)

    pages = list(extract_pages(path, data))
    title = _title_for(path, pages)
    now = datetime.now(UTC).isoformat(timespec="seconds")

    with conn:  # one transaction: a failed ingest leaves the old version intact
        if existing:
            doc_id = existing["id"]
            _delete_chunks(conn, doc_id)
            conn.execute(
                "UPDATE documents SET title = ?, sha256 = ?, added_at = ? WHERE id = ?",
                (title, digest, now, doc_id),
            )
        else:
            cur = conn.execute(
                "INSERT INTO documents (path, title, sha256, added_at) VALUES (?, ?, ?, ?)",
                (str(path), title, digest, now),
            )
            doc_id = cur.lastrowid

        ordinal = 0
        for page in pages:
            for text in chunk_text(page.text):
                cur = conn.execute(
                    "INSERT INTO chunks (doc_id, page, ordinal, text) VALUES (?, ?, ?, ?)",
                    (doc_id, page.number, ordinal, text),
                )
                conn.execute(
                    "INSERT INTO chunks_fts (rowid, title, text) VALUES (?, ?, ?)",
                    (cur.lastrowid, title, text),
                )
                ordinal += 1

    if ordinal == 0:
        status: Status = "empty"  # e.g. a scanned PDF with no text layer
    else:
        status = "updated" if existing else "added"
    return IngestResult(path, status, ordinal)


def extract_pages(path: Path, data: bytes | None = None) -> Iterator[Page]:
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(path)
        for number, page in enumerate(reader.pages, start=1):
            yield Page(number, page.extract_text() or "")
    else:
        raw = data if data is not None else path.read_bytes()
        yield Page(None, raw.decode("utf-8", errors="replace"))


def _title_for(path: Path, pages: list[Page]) -> str:
    """First Markdown H1 if there is one, otherwise the file name."""
    if path.suffix.lower() in {".md", ".markdown"} and pages:
        for line in pages[0].text.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    return path.stem.replace("-", " ").replace("_", " ")


def _delete_chunks(conn: sqlite3.Connection, doc_id: int) -> None:
    conn.execute(
        "DELETE FROM chunks_fts WHERE rowid IN (SELECT id FROM chunks WHERE doc_id = ?)",
        (doc_id,),
    )
    conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
