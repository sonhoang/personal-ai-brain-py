"""Notes with tags and [[wiki links]], and the backlinks those links create."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

# [[Target]] or [[Target|label]]
_WIKI_LINK = re.compile(r"\[\[([^\[\]|]+)(?:\|[^\[\]]*)?\]\]")


@dataclass(frozen=True)
class Note:
    id: int
    title: str
    body: str
    tags: list[str]
    created_at: str
    updated_at: str


def parse_links(body: str) -> list[str]:
    """Distinct link targets in order of appearance (case-insensitive)."""
    seen: dict[str, str] = {}
    for match in _WIKI_LINK.finditer(body):
        target = " ".join(match.group(1).split())
        if target:
            seen.setdefault(target.lower(), target)
    return list(seen.values())


def normalise_tags(tags: list[str]) -> list[str]:
    cleaned = (t.strip().lstrip("#").lower() for t in tags)
    return sorted({t for t in cleaned if t})


def save_note(conn: sqlite3.Connection, title: str, body: str, tags: list[str]) -> Note:
    """Create a note, or replace the body and tags of the note with this title."""
    title = title.strip()
    if not title:
        raise ValueError("a note needs a title")
    tag_list = normalise_tags(tags)
    tags_json = json.dumps(tag_list)
    now = datetime.now(UTC).isoformat(timespec="seconds")

    with conn:
        row = conn.execute("SELECT id FROM notes WHERE title = ?", (title,)).fetchone()
        if row:
            note_id = row["id"]
            conn.execute(
                "UPDATE notes SET body = ?, tags = ?, updated_at = ? WHERE id = ?",
                (body, tags_json, now, note_id),
            )
            conn.execute("DELETE FROM notes_fts WHERE rowid = ?", (note_id,))
            conn.execute("DELETE FROM links WHERE src_note_id = ?", (note_id,))
        else:
            cur = conn.execute(
                "INSERT INTO notes (title, body, tags, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (title, body, tags_json, now, now),
            )
            note_id = cur.lastrowid
        conn.execute(
            "INSERT INTO notes_fts (rowid, title, body, tags) VALUES (?, ?, ?, ?)",
            (note_id, title, body, " ".join(tag_list)),
        )
        conn.executemany(
            "INSERT INTO links (src_note_id, target) VALUES (?, ?)",
            [(note_id, target) for target in parse_links(body)],
        )
    note = get_note(conn, title)
    assert note is not None
    return note


def get_note(conn: sqlite3.Connection, title: str) -> Note | None:
    row = conn.execute("SELECT * FROM notes WHERE title = ?", (title.strip(),)).fetchone()
    return _to_note(row) if row else None


def list_notes(conn: sqlite3.Connection, tag: str | None = None) -> list[Note]:
    if tag:
        rows = conn.execute(
            "SELECT * FROM notes WHERE EXISTS"
            " (SELECT 1 FROM json_each(notes.tags) WHERE value = ?) ORDER BY updated_at DESC",
            (tag.strip().lstrip("#").lower(),),
        )
    else:
        rows = conn.execute("SELECT * FROM notes ORDER BY updated_at DESC")
    return [_to_note(r) for r in rows]


def backlinks(conn: sqlite3.Connection, title: str) -> list[Note]:
    """Notes that contain [[title]]. The target does not have to exist."""
    rows = conn.execute(
        "SELECT n.* FROM links l JOIN notes n ON n.id = l.src_note_id"
        " WHERE l.target = ? ORDER BY n.updated_at DESC",
        (" ".join(title.split()),),
    )
    return [_to_note(r) for r in rows]


def _to_note(row: sqlite3.Row) -> Note:
    return Note(
        id=row["id"],
        title=row["title"],
        body=row["body"],
        tags=json.loads(row["tags"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
