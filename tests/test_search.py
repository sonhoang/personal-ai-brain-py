import sqlite3
from pathlib import Path

import pytest

from personal_ai_brain.notes import save_note
from personal_ai_brain.search import (
    get_chunk,
    resolve_document,
    search_chunks,
    search_notes,
    to_fts_query,
)


def test_query_becomes_quoted_or_terms() -> None:
    assert to_fts_query("What is the vibration limit?") == '"vibration" OR "limit"'


def test_all_stopword_query_is_kept() -> None:
    assert to_fts_query("what is it") == '"what" OR "is" OR "it"'


@pytest.mark.parametrize(
    "query",
    [
        'unbalanced "quote',
        "NEAR(pump bearing, 3)",
        "AND OR NOT",
        "title:secret",
        "grease*",
        "(((",
        "'; DROP TABLE chunks; --",
        "^start",
        "",
        "   ",
        "naïve café 東京",
    ],
)
def test_arbitrary_input_never_raises(library: sqlite3.Connection, query: str) -> None:
    search_chunks(library, query)
    search_notes(library, query)


def test_punctuation_only_query_returns_nothing(library: sqlite3.Connection) -> None:
    assert search_chunks(library, "?!*()") == []


def test_ranks_the_right_pdf_page_first(library: sqlite3.Connection) -> None:
    hits = search_chunks(library, "bearing grease running hours")
    assert Path(hits[0].path).name == "pump-station-maintenance.pdf"
    assert hits[0].page == 3
    assert "[" in hits[0].snippet  # matches are highlighted


def test_ranks_the_right_document_first(library: sqlite3.Connection) -> None:
    hits = search_chunks(library, "Retry-After header for rejected requests")
    assert Path(hits[0].path).name == "api-rate-limiting-design.md"


def test_document_filter(library: sqlite3.Connection) -> None:
    doc_id = resolve_document(library, "q3-2024-reliability-review.md")
    hits = search_chunks(library, "failover drill", doc_id=doc_id)
    assert hits and all(h.doc_id == doc_id for h in hits)


def test_resolve_document_by_title_and_id(library: sqlite3.Connection) -> None:
    doc_id = resolve_document(library, "Q3 2024 Reliability Review")
    assert resolve_document(library, str(doc_id)) == doc_id
    with pytest.raises(LookupError):
        resolve_document(library, "no-such-file.pdf")


def test_get_chunk(library: sqlite3.Connection) -> None:
    hit = search_chunks(library, "token bucket")[0]
    full = get_chunk(library, hit.chunk_id)
    assert full is not None and full.text == hit.text
    assert get_chunk(library, 999_999) is None


def test_note_search_with_tag_filter(conn: sqlite3.Connection) -> None:
    save_note(conn, "Pump checks", "Vibration readings look stable.", ["ops"])
    save_note(conn, "Vibration theory", "Notes on vibration analysis.", ["reading"])
    assert [n.title for n in search_notes(conn, "vibration", tag="ops")] == ["Pump checks"]
    assert len(search_notes(conn, "vibration")) == 2
