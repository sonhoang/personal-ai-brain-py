from itertools import pairwise

import pytest

from personal_ai_brain.chunking import chunk_text


def paragraphs(n: int, words_each: int) -> str:
    """n paragraphs of unique words w0, w1, ... so every word is traceable."""
    words = iter(range(n * words_each))
    return "\n\n".join(" ".join(f"w{next(words)}" for _ in range(words_each)) for _ in range(n))


def test_short_text_is_one_chunk() -> None:
    assert chunk_text("Hello world.\n\nSecond paragraph.") == ["Hello world.\n\nSecond paragraph."]


def test_empty_text_gives_no_chunks() -> None:
    assert chunk_text("  \n\n \n") == []


def test_chunks_respect_size_cap() -> None:
    chunks = chunk_text(paragraphs(40, 30), max_chars=300, overlap=50)
    assert len(chunks) > 1
    assert all(len(c) <= 300 for c in chunks)


def test_never_splits_words() -> None:
    text = paragraphs(10, 200)  # paragraphs far longer than the cap
    vocabulary = set(text.split())
    for chunk in chunk_text(text, max_chars=250, overlap=40):
        assert set(chunk.split()) <= vocabulary


def test_consecutive_chunks_overlap() -> None:
    chunks = chunk_text(paragraphs(20, 25), max_chars=400, overlap=60)
    assert len(chunks) > 2
    for prev, nxt in pairwise(chunks):
        # the next chunk starts with whole trailing words of the previous one
        shared = [w for w in nxt.split() if w in set(prev.split())]
        assert shared and prev.split()[-len(shared) :] == shared
        assert len(" ".join(shared)) <= 60


def test_whitespace_inside_paragraph_is_collapsed() -> None:
    assert chunk_text("one\ntwo   three\tfour") == ["one two three four"]


def test_bad_arguments() -> None:
    with pytest.raises(ValueError):
        chunk_text("x", max_chars=100, overlap=100)
