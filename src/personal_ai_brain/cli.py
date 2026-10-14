"""Command line: brain ingest | search | ask | docs | note | backlinks | mcp | eval."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import Annotated

import typer

from . import answer, evaluation, ingest, notes, search
from .config import Settings, make_client
from .db import connect

app = typer.Typer(no_args_is_help=True, add_completion=False, rich_markup_mode=None, help=__doc__)
note_app = typer.Typer(no_args_is_help=True, help="Create and list notes.")
app.add_typer(note_app, name="note")

DocOption = Annotated[
    str | None, typer.Option("--doc", "-d", help="Limit to one document (id, title or file name).")
]


def _settings() -> Settings:
    return Settings.from_env()


def _doc_id(conn: sqlite3.Connection, ref: str | None) -> int | None:
    if ref is None:
        return None
    try:
        return search.resolve_document(conn, ref)
    except LookupError as exc:
        raise typer.BadParameter(str(exc), param_hint="--doc") from exc


def _where(page: int | None) -> str:
    return f", p. {page}" if page is not None else ""


@app.command("ingest")
def ingest_cmd(
    path: Annotated[Path, typer.Argument(exists=True, help="A file or a folder.")],
) -> None:
    """Add or refresh .pdf, .md and .txt files. Unchanged files are skipped."""
    conn = connect(_settings().db_path)
    try:
        results = ingest.ingest_path(conn, path)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="PATH") from exc
    for r in results:
        typer.echo(f"{r.status:9} {r.chunks:4} chunks  {r.path.name}")
    counts = {s: sum(r.status == s for r in results) for s in ("added", "updated", "unchanged")}
    typer.echo(", ".join(f"{n} {s}" for s, n in counts.items()))


@app.command("search")
def search_cmd(
    query: str,
    doc: DocOption = None,
    tag: Annotated[str | None, typer.Option(help="Search notes with this tag.")] = None,
    in_notes: Annotated[bool, typer.Option("--notes", help="Search notes, not documents.")] = False,
    limit: Annotated[int, typer.Option("--limit", "-n")] = 8,
) -> None:
    """Keyword search with BM25 ranking. Matched words are shown in [brackets]."""
    conn = connect(_settings().db_path)
    if in_notes or tag:
        for n in search.search_notes(conn, query, limit=limit, tag=tag):
            tags = " ".join(f"#{t}" for t in n.tags)
            typer.echo(f"{n.title}  {tags}\n    {n.snippet}\n")
        return
    hits = search.search_chunks(conn, query, limit=limit, doc_id=_doc_id(conn, doc))
    if not hits:
        typer.echo("No matches.")
    for h in hits:
        typer.echo(f"{h.title}{_where(h.page)}  (chunk {h.chunk_id}, bm25 {h.score:.2f})")
        typer.echo(f"    {h.snippet}\n")


@app.command("ask")
def ask_cmd(
    question: str,
    doc: DocOption = None,
    top_k: Annotated[int | None, typer.Option("--top-k", "-k")] = None,
) -> None:
    """Answer from the library with Claude, with numbered citations."""
    settings = _settings()
    conn = connect(settings.db_path)
    doc_id = _doc_id(conn, doc)
    try:
        client = make_client()
    except RuntimeError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    result = answer.ask(
        conn,
        question,
        client=client,
        model=settings.model,
        top_k=top_k or settings.top_k,
        doc_id=doc_id,
    )
    typer.echo(result.text)
    if result.citations:
        typer.echo("\nSources:")
        for c in result.citations:
            typer.echo(f"  [{c.number}] {c.title}{_where(c.page)}  (chunk {c.chunk_id})")
    elif not result.insufficient:
        typer.echo("\nwarning: the answer cites no source; treat it as unverified.", err=True)
    if result.dropped:
        dropped = ", ".join(f"[{n}]" for n in result.dropped)
        typer.echo(f"warning: removed citations to sources that were not provided: {dropped}")


@app.command("docs")
def docs_cmd() -> None:
    """List documents in the library."""
    conn = connect(_settings().db_path)
    for d in search.list_documents(conn):
        pages = f", {d['pages']} pages" if d["pages"] else ""
        typer.echo(f"{d['id']:4}  {d['title']}  ({d['chunks']} chunks{pages})")


@note_app.command("add")
def note_add(
    title: str,
    body: Annotated[str, typer.Option("--body", "-b", help="Text; [[Title]] links.")] = "",
    tag: Annotated[list[str] | None, typer.Option("--tag", "-t", help="Repeatable.")] = None,
) -> None:
    """Create a note, or replace the note with the same title."""
    note = notes.save_note(connect(_settings().db_path), title, body, tag or [])
    typer.echo(f"saved note {note.id}: {note.title}")


@note_app.command("list")
def note_list(tag: Annotated[str | None, typer.Option("--tag", "-t")] = None) -> None:
    """List notes, newest first."""
    for n in notes.list_notes(connect(_settings().db_path), tag=tag):
        tags = " ".join(f"#{t}" for t in n.tags)
        typer.echo(f"{n.updated_at}  {n.title}  {tags}".rstrip())


@app.command("backlinks")
def backlinks_cmd(title: str) -> None:
    """Notes that link to TITLE with [[TITLE]]."""
    found = notes.backlinks(connect(_settings().db_path), title)
    if not found:
        typer.echo(f"No notes link to [[{title}]].")
    for n in found:
        typer.echo(n.title)


@app.command("mcp")
def mcp_cmd(
    allow_writes: Annotated[
        bool, typer.Option("--allow-writes", help="Also expose add_note.")
    ] = False,
) -> None:
    """Run the MCP server on stdio (read-only unless --allow-writes)."""
    from .mcp_server import run

    run(_settings(), allow_writes=allow_writes)


@app.command("eval")
def eval_cmd(
    corpus: Annotated[Path, typer.Option(exists=True)] = Path("evals/corpus"),
    questions: Annotated[Path, typer.Option(exists=True)] = Path("evals/questions.jsonl"),
    answers: Annotated[
        bool, typer.Option("--answers", help="Also ask Claude (needs ANTHROPIC_API_KEY).")
    ] = False,
) -> None:
    """Measure retrieval (hit@1, hit@5, MRR) on the sample corpus, in a throwaway database."""
    qs = evaluation.load_questions(questions)
    with tempfile.TemporaryDirectory() as tmp:
        conn = connect(Path(tmp) / "eval.db")
        ingest.ingest_path(conn, corpus)
        report = evaluation.evaluate_retrieval(conn, qs)
        typer.echo(f"Retrieval over {report.total} answerable questions (top 10 chunks):")
        typer.echo(f"  hit@1 {report.hit_at_1 / report.total:.2f} ({report.hit_at_1})")
        typer.echo(f"  hit@5 {report.hit_at_5 / report.total:.2f} ({report.hit_at_5})")
        typer.echo(f"  MRR   {report.mrr:.2f}")
        for q, rank in report.misses:
            where = f"rank {rank}" if rank else "not in top 10"
            typer.echo(f"  miss {q.id}: {where}  ({q.question})")

        if not answers:
            return
        settings = _settings()
        client = make_client()
        a = evaluation.evaluate_answers(
            qs,
            lambda text: answer.ask(
                conn, text, client=client, model=settings.model, top_k=settings.top_k
            ),
        )
        typer.echo(f"\nAnswers ({settings.model}):")
        typer.echo(f"  cited the expected source   {a.cited_expected}/{a.answerable}")
        typer.echo(f"  abstained when unanswerable {a.abstained_correctly}/{a.unanswerable}")
        typer.echo(f"  resisted planted instruction {a.injection_resisted}/{a.injection_checks}")
        for q, reason in a.failures:
            typer.echo(f"  fail {q.id}: {reason}")
