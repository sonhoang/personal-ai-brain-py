"""Split text into retrieval-sized chunks.

Paragraphs are packed together up to ``max_chars``. A paragraph longer than
that is split on word boundaries. Each new chunk starts with the last few words
of the previous one (``overlap`` characters, rounded down to whole words) so a
sentence that straddles a boundary is still findable from either side.
Words are never cut.
"""

from __future__ import annotations

import re

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


def chunk_text(text: str, max_chars: int = 1200, overlap: int = 150) -> list[str]:
    if max_chars <= 0 or overlap < 0 or overlap >= max_chars:
        raise ValueError("need max_chars > 0 and 0 <= overlap < max_chars")

    pieces: list[str] = []
    for para in _PARAGRAPH_BREAK.split(text.replace("\r\n", "\n")):
        para = " ".join(para.split())  # collapse whitespace inside a paragraph
        if para:
            pieces.extend(_split_long(para, max_chars))

    chunks: list[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current}\n\n{piece}" if current else piece
        if len(candidate) <= max_chars:
            current = candidate
            continue
        chunks.append(current)
        tail = _tail_words(current, overlap)
        current = f"{tail} {piece}" if tail and len(tail) + 1 + len(piece) <= max_chars else piece
    if current:
        chunks.append(current)
    return chunks


def _split_long(paragraph: str, max_chars: int) -> list[str]:
    """Split one paragraph into pieces of at most max_chars, on spaces."""
    if len(paragraph) <= max_chars:
        return [paragraph]
    out: list[str] = []
    current = ""
    for word in paragraph.split(" "):
        if len(word) > max_chars:  # a single absurd token (e.g. base64); hard-cut it
            if current:
                out.append(current)
                current = ""
            out.extend(word[i : i + max_chars] for i in range(0, len(word), max_chars))
            continue
        candidate = f"{current} {word}" if current else word
        if len(candidate) <= max_chars:
            current = candidate
        else:
            out.append(current)
            current = word
    if current:
        out.append(current)
    return out


def _tail_words(text: str, limit: int) -> str:
    """The longest run of whole trailing words that fits in ``limit`` characters."""
    if limit == 0:
        return ""
    words = text.split()
    tail: list[str] = []
    size = 0
    for word in reversed(words):
        size += len(word) + (1 if tail else 0)
        if size > limit:
            break
        tail.append(word)
    return " ".join(reversed(tail))
