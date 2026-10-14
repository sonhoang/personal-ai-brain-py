import sqlite3

import pytest

from personal_ai_brain.notes import backlinks, list_notes, parse_links, save_note


def test_parse_links() -> None:
    body = "See [[Pump  Manual]], [[pump manual|the manual]] and [[Incident 17]]. [[ ]] [not]"
    assert parse_links(body) == ["Pump Manual", "Incident 17"]


def test_backlinks(conn: sqlite3.Connection) -> None:
    save_note(conn, "Pump Manual", "Main reference.", [])
    save_note(conn, "Q3 review", "Bearing wear, see [[Pump Manual]].", [])
    save_note(conn, "Shift log", "Checked vibration per [[pump manual]].", [])
    save_note(conn, "Unrelated", "Nothing here.", [])
    assert sorted(n.title for n in backlinks(conn, "Pump Manual")) == ["Q3 review", "Shift log"]


def test_links_to_titles_that_do_not_exist_yet(conn: sqlite3.Connection) -> None:
    save_note(conn, "Idea", "Write up [[Future Note]].", [])
    assert [n.title for n in backlinks(conn, "Future Note")] == ["Idea"]


def test_saving_again_updates_body_and_links(conn: sqlite3.Connection) -> None:
    first = save_note(conn, "Log", "Links to [[A]].", ["x"])
    second = save_note(conn, "log", "Now links to [[B]].", ["y"])
    assert second.id == first.id and second.body == "Now links to [[B]]."
    assert backlinks(conn, "A") == []
    assert [n.title for n in backlinks(conn, "B")] == ["Log"]


def test_tags_are_normalised_and_filterable(conn: sqlite3.Connection) -> None:
    note = save_note(conn, "T", "body", ["#Ops", "ops", " Reliability ", ""])
    assert note.tags == ["ops", "reliability"]
    save_note(conn, "Other", "body", ["misc"])
    assert [n.title for n in list_notes(conn, tag="#OPS")] == ["T"]
    assert len(list_notes(conn)) == 2


def test_note_needs_title(conn: sqlite3.Connection) -> None:
    with pytest.raises(ValueError):
        save_note(conn, "  ", "body", [])
