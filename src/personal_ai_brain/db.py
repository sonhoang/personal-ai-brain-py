"""SQLite storage: one file, plain tables plus FTS5 indexes.

The FTS tables are regular (not external-content) FTS5 tables keyed by the
same rowid as the row they index. Ingest and note code write both in one
transaction, which keeps the sync logic visible instead of hidden in triggers.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id       INTEGER PRIMARY KEY,
    path     TEXT NOT NULL UNIQUE,
    title    TEXT NOT NULL,
    sha256   TEXT NOT NULL,
    added_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id      INTEGER PRIMARY KEY,
    doc_id  INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page    INTEGER,
    ordinal INTEGER NOT NULL,
    text    TEXT NOT NULL,
    UNIQUE (doc_id, ordinal)
);

-- rowid = chunks.id. The document title is indexed with every chunk so a
-- query that names the document can find it.
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    title, text, tokenize = 'porter unicode61'
);

CREATE TABLE IF NOT EXISTS notes (
    id         INTEGER PRIMARY KEY,
    title      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    body       TEXT NOT NULL,
    tags       TEXT NOT NULL DEFAULT '[]',  -- JSON array of lower-case strings
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- rowid = notes.id
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    title, body, tags, tokenize = 'porter unicode61'
);

-- [[wiki links]] from a note to any title (a note or a document; it may not exist yet).
CREATE TABLE IF NOT EXISTS links (
    src_note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    target      TEXT NOT NULL COLLATE NOCASE,
    PRIMARY KEY (src_note_id, target)
);
CREATE INDEX IF NOT EXISTS links_target ON links(target);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    """Open (and if needed create) the library database."""
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    return conn
