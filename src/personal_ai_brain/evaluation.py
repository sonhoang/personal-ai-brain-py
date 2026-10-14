"""Retrieval and answer evaluation against a fixed question set.

Each question names the document (and, for PDFs, the page) that holds the
answer. A retrieved chunk is a match when it comes from that document and,
if a page is given, from that page. Questions with no expected document are
"unanswerable": they are skipped by the retrieval metrics and, in the answer
eval, the model is expected to report insufficient evidence.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .answer import Answer
from .search import ChunkHit, search_chunks


@dataclass(frozen=True)
class Question:
    id: str
    question: str
    expected_doc: str | None  # file name, e.g. "pump-station-maintenance.pdf"
    expected_page: int | None = None
    must_not_contain: str | None = None  # e.g. text planted by a prompt injection


@dataclass
class RetrievalReport:
    total: int = 0
    hit_at_1: int = 0
    hit_at_5: int = 0
    reciprocal_ranks: list[float] = field(default_factory=list)
    misses: list[tuple[Question, int | None]] = field(default_factory=list)  # (q, rank)

    @property
    def mrr(self) -> float:
        return sum(self.reciprocal_ranks) / len(self.reciprocal_ranks) if self.total else 0.0


@dataclass
class AnswerReport:
    answerable: int = 0
    cited_expected: int = 0
    unanswerable: int = 0
    abstained_correctly: int = 0
    injection_checks: int = 0
    injection_resisted: int = 0
    failures: list[tuple[Question, str]] = field(default_factory=list)


def load_questions(path: Path) -> list[Question]:
    questions = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            questions.append(Question(**json.loads(line)))
    return questions


def is_match(hit: ChunkHit, q: Question) -> bool:
    if q.expected_doc is None or Path(hit.path).name != q.expected_doc:
        return False
    return q.expected_page is None or hit.page == q.expected_page


def evaluate_retrieval(
    conn: sqlite3.Connection, questions: list[Question], depth: int = 10
) -> RetrievalReport:
    """hit@1, hit@5 and MRR over the top ``depth`` chunks (rank > depth counts as 0)."""
    report = RetrievalReport()
    for q in questions:
        if q.expected_doc is None:
            continue
        hits = search_chunks(conn, q.question, limit=depth)
        rank = next((i for i, h in enumerate(hits, start=1) if is_match(h, q)), None)
        report.total += 1
        report.hit_at_1 += rank == 1
        report.hit_at_5 += rank is not None and rank <= 5
        report.reciprocal_ranks.append(1 / rank if rank else 0.0)
        if rank != 1:
            report.misses.append((q, rank))
    return report


def evaluate_answers(questions: list[Question], ask: Callable[[str], Answer]) -> AnswerReport:
    """Run ``ask`` on every question and check citations, abstention and injection."""
    report = AnswerReport()
    for q in questions:
        result = ask(q.question)
        if q.must_not_contain is not None:
            report.injection_checks += 1
            if q.must_not_contain.lower() in result.text.lower():
                report.failures.append((q, "followed an instruction planted in a document"))
            else:
                report.injection_resisted += 1
        if q.expected_doc is None:
            report.unanswerable += 1
            if result.insufficient:
                report.abstained_correctly += 1
            else:
                report.failures.append((q, "answered a question the library cannot answer"))
            continue
        report.answerable += 1
        if any(
            Path(c.path).name == q.expected_doc
            and (q.expected_page is None or c.page == q.expected_page)
            for c in result.citations
        ):
            report.cited_expected += 1
        else:
            reason = "said evidence was insufficient" if result.insufficient else "wrong citations"
            report.failures.append((q, reason))
    return report
