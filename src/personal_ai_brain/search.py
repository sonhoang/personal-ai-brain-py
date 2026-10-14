"""Keyword retrieval over chunks and notes with SQLite FTS5 and BM25."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass

# Very common words add little to BM25 and make every chunk a match.
STOPWORDS = frozenset(
    "a an and are as at be by can do does for from has have how i in is it its of on or "
    "our should that the their this to was we were what when where which who why will "
    "with you your".split()
)
MAX_TERMS = 32
_TOKEN = re.compile(r"\w+", re.UNICODE)

# Markers placed around matched terms in snippets.
HIGHLIGHT = ("[", "]")


@dataclass(frozen=True)
class ChunkHit:
    chunk_id: int
    doc_id: int
    title: str
    path: str
    page: int | None
    ordinal: int
    text: str
    snippet: str
    score: float  # bm25(): lower is better


@dataclass(frozen=True)
class NoteHit:
    note_id: int
    title: str
    tags: list[str]
    snippet: str
    score: float


def to_fts_query(user_query: str) -> str:
    """Turn arbitrary text into a safe FTS5 query.

    Every word becomes a quoted term, so FTS5 operators and punctuation in the
    input (AND, NEAR, *, :, ", parentheses) are treated as plain text. Terms are
    OR-ed and BM25 does the ranking. Returns "" if nothing searchable is left.
    """
    words = [w.lower() for w in _TOKEN.findall(user_query)]
    terms = [w for w in words if w not in STOPWORDS] or words  # all-stopword query: keep them
    unique = list(dict.fromkeys(terms))[:MAX_TERMS]
    return " OR ".join(f'"{t}"' for t in unique)


def search_chunks(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 8,
    doc_id: int | None = None,
) -> list[ChunkHit]:
    fts = to_fts_query(query)
    if not fts:
        return []
    open_, close = HIGHLIGHT
    sql = """
        SELECT c.id, c.doc_id, d.title, d.path, c.page, c.ordinal, c.text,
               snippet(chunks_fts, 1, ?, ?, ' ... ', 16) AS snip,
               bm25(chunks_fts, 2.0, 1.0) AS score
        FROM chunks_fts
        JOIN chunks c ON c.id = chunks_fts.rowid
        JOIN documents d ON d.id = c.doc_id
        WHERE chunks_fts MATCH ?
    """
    params: list[object] = [open_, close, fts]
    if doc_id is not None:
        sql += " AND c.doc_id = ?"
        params.append(doc_id)
    sql += " ORDER BY score LIMIT ?"
    params.append(limit)
    return [
        ChunkHit(
            chunk_id=r["id"],
            doc_id=r["doc_id"],
            title=r["title"],
            path=r["path"],
            page=r["page"],
            ordinal=r["ordinal"],
            text=r["text"],
            snippet=r["snip"].strip(),
            score=r["score"],
        )
        for r in conn.execute(sql, params)
    ]


def search_notes(
    conn: sqlite3.Connection, query: str, limit: int = 8, tag: str | None = None
) -> list[NoteHit]:
    fts = to_fts_query(query)
    if not fts:
        return []
    open_, close = HIGHLIGHT
    sql = """
        SELECT n.id, n.title, n.tags,
               snippet(notes_fts, 1, ?, ?, ' ... ', 16) AS snip,
               bm25(notes_fts, 3.0, 1.0, 2.0) AS score
        FROM notes_fts
        JOIN notes n ON n.id = notes_fts.rowid
        WHERE notes_fts MATCH ?
    """
    params: list[object] = [open_, close, fts]
    if tag:
        sql += " AND EXISTS (SELECT 1 FROM json_each(n.tags) WHERE value = ?)"
        params.append(tag.lower().lstrip("#"))
    sql += " ORDER BY score LIMIT ?"
    params.append(limit)
    return [
        NoteHit(r["id"], r["title"], json.loads(r["tags"]), r["snip"].strip(), r["score"])
        for r in conn.execute(sql, params)
    ]


def get_chunk(conn: sqlite3.Connection, chunk_id: int) -> ChunkHit | None:
    r = conn.execute(
        """
        SELECT c.id, c.doc_id, d.title, d.path, c.page, c.ordinal, c.text
        FROM chunks c JOIN documents d ON d.id = c.doc_id
        WHERE c.id = ?
        """,
        (chunk_id,),
    ).fetchone()
    if r is None:
        return None
    return ChunkHit(
        r["id"], r["doc_id"], r["title"], r["path"], r["page"], r["ordinal"], r["text"], "", 0.0
    )


def list_documents(conn: sqlite3.Connection) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT d.id, d.title, d.path, d.added_at, COUNT(c.id) AS chunks,
               MAX(c.page) AS pages
        FROM documents d LEFT JOIN chunks c ON c.doc_id = d.id
        GROUP BY d.id ORDER BY d.title
        """
    )
    return [dict(r) for r in rows]


def resolve_document(conn: sqlite3.Connection, ref: str) -> int:
    """Find a document by id, exact title, or file name. Raises LookupError."""
    if ref.isdigit():
        row = conn.execute("SELECT id FROM documents WHERE id = ?", (int(ref),)).fetchone()
        if row:
            return int(row["id"])
    rows = conn.execute(
        "SELECT id FROM documents WHERE title = ? COLLATE NOCASE OR path LIKE ? ESCAPE '\\'",
        (ref, "%/" + ref.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")),
    ).fetchall()
    if len(rows) == 1:
        return int(rows[0]["id"])
    if not rows:
        raise LookupError(f"no document matches {ref!r}")
    raise LookupError(f"{ref!r} matches {len(rows)} documents; use the id instead")
