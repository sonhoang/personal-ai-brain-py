from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from personal_ai_brain.db import connect
from personal_ai_brain.ingest import ingest_path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "evals" / "corpus"
QUESTIONS = ROOT / "evals" / "questions.jsonl"


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    return connect(tmp_path / "brain.db")


@pytest.fixture
def library(conn: sqlite3.Connection) -> sqlite3.Connection:
    """A database with the sample corpus ingested."""
    ingest_path(conn, CORPUS)
    return conn


class FakeClaude:
    """Stands in for anthropic.Anthropic: records requests, returns a canned reply."""

    def __init__(self, reply: str, stop_reason: str = "end_turn") -> None:
        self.reply = reply
        self.stop_reason = stop_reason
        self.requests: list[dict] = []
        self.messages = self  # so client.messages.create(...) works

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.requests.append(kwargs)
        return SimpleNamespace(
            stop_reason=self.stop_reason,
            content=[SimpleNamespace(type="text", text=self.reply)],
        )
