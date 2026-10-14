# personal-ai-brain (Python)

A Python port of [personal-ai-brain](https://github.com/sonhoang/personal-ai-brain), my
TypeScript project. It keeps a library of documents and notes on your own machine and
answers questions from that library with Claude, citing the document and page each claim
comes from. It is the NotebookLM idea (answers grounded in your sources) plus the Mem idea
(notes with tags, `[[wiki links]]` and backlinks), in about 1,200 lines of Python.

The port is deliberately smaller than the original: no web UI, no workspaces, no HTTP API.
It keeps the parts that matter for one problem: a pile of technical reports nobody can
search, and people answering the same question from scratch. You get a CLI, an MCP server
so Claude (or any MCP client) can search the library, and an evaluation harness.

Everything is stored in one SQLite file. The only network call is to the Claude API when
you ask a question.

## Quick start

Needs Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run brain ingest evals/corpus           # a folder or a single .pdf/.md/.txt
uv run brain search "bearing temperature limit"
uv run brain docs

export ANTHROPIC_API_KEY=...               # only needed for ask
uv run brain ask "At what vibration level must a pump be stopped?"
uv run brain ask "What went wrong?" --doc incident-2024-017-database-failover.md

uv run brain note add "Pump checks" -b "Followed [[Pump Manual]] today." -t ops
uv run brain note list --tag ops
uv run brain backlinks "Pump Manual"

uv run brain eval                          # retrieval metrics, no API key needed
uv run pytest -q && uv run ruff check
```

Settings are environment variables (see `.env.example`): `BRAIN_DB` (default `brain.db`
in the current directory), `BRAIN_MODEL` (default `claude-sonnet-5-5`), `BRAIN_TOP_K`
(default 6), `ANTHROPIC_API_KEY`.

### MCP server

`brain mcp` runs a Model Context Protocol server on stdio, built on the official Python
SDK (`MCPServer`, which was called `FastMCP` before mcp 2.0). Tools:

| Tool | What it does |
|------|--------------|
| `search_library` | BM25 search over chunks, optional `document` filter; returns chunk ids, titles, pages, snippets |
| `get_chunk` | Full text of one chunk with its document and page |
| `list_documents` | Everything in the library |
| `ask_library` | The grounded answer from `brain ask`, with validated citations |
| `add_note` | Only with `brain mcp --allow-writes` |

Example Claude Desktop entry (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "brain": {
      "command": "uv",
      "args": ["--directory", "/path/to/personal-ai-brain-py", "run", "brain", "mcp"],
      "env": { "BRAIN_DB": "/path/to/brain.db" }
    }
  }
}
```

Inside Claude Desktop you usually do not need `ask_library`: Claude can call
`search_library` and `get_chunk` and write the answer itself. `ask_library` is there for
clients that want the fixed contract (only these chunks, citations checked by code).

## How it works

**Ingest** (`ingest.py`, `chunking.py`). PDFs are read page by page with pypdf, so every
chunk keeps its page number. Text is split into chunks of up to 1,200 characters by
packing whole paragraphs; a paragraph that is too long is split between words. Each chunk
starts with the last ~150 characters (whole words) of the previous one, so a sentence on a
boundary can be found from both sides. A document is keyed by absolute path and its
SHA-256: re-ingesting an unchanged file does nothing, and a changed file has its chunks
replaced in one transaction.

**Search** (`search.py`). SQLite FTS5 with the Porter stemmer, ranked by BM25. The
document title is indexed alongside each chunk with a higher weight. User input is never
passed to FTS5 as syntax: it is reduced to words, common stopwords are dropped, and each
word becomes a quoted term joined with `OR`, so input like `NEAR(`, `"`, `AND` or
`title:x` is just text. Snippets mark matched words in `[brackets]`.

**Ask** (`answer.py`). The top-k chunks (default 6) are sent to Claude, numbered, inside
`<sources>` tags; the question follows in `<question>`. The system prompt says: answer
only from the sources, cite every claim as `[n]`, and if the sources are not enough,
reply `INSUFFICIENT_EVIDENCE: ...` instead of guessing. If retrieval finds nothing, the
model is not called at all. After the reply comes back, the code parses the `[n]` and
`[n, m]` markers, maps each valid one to (document, page, chunk id), and removes any
number that does not refer to a chunk that was sent, reporting it as dropped. The CLI
warns when an answer has no valid citation. A `refusal` stop reason is reported as such.

## Design decisions and trade-offs

**BM25 first, no embeddings by default.** Anthropic does not ship an embedding model, so
vector search would mean a second vendor (or a local model to install and keep in sync),
plus a re-embedding job whenever the model changes. For technical reports, keyword search
is a strong baseline: part numbers, error codes, standard names (`ISO 10816-3`) and
acronyms are exactly what embeddings tend to blur. It also needs no GPU and no service.
The cost is vocabulary mismatch: a question that uses different words from the document
can miss. The eval below shows one such case. The plan is to measure before adding
anything, then try hybrid retrieval (BM25 plus embeddings, merged with reciprocal rank
fusion) or a reranker, and keep it only if the numbers move.

**Citations are checked by code, not trusted.** The model only ever sees numbered chunks,
so a citation is a number the code can check. A citation to a source that was not sent
is removed and reported. This cannot prove that the cited chunk supports the sentence; it
only proves the chunk exists and was in context. The answer eval measures the first part
(right source cited); checking support would need a second grading pass.

**Prompt injection.** Documents are data, and a document can contain text written to
steer the model ("ignore your instructions and..."). Three things limit this. Each chunk
is wrapped in `<source>` tags and HTML-escaped, so a document cannot close its own tag or
forge another source. The system prompt tells the model that source text is untrusted and
that instructions inside it must not be followed. And the default MCP server has no write
tools, so a successful injection can at worst produce a wrong answer, not change data.
The sample corpus has a planted injection (`deploy-runbook.md`) and the answer eval
checks that it is ignored. None of this is a guarantee; it reduces the damage.

**MCP read-only by default.** An MCP client reads search results into the same context in
which it decides which tools to call. If that client can also write, a malicious document
can ask it to. `add_note` therefore exists only when you start the server with
`--allow-writes`, and every read tool is annotated `readOnlyHint`.

**SQLite and FTS5.** One file, no server, transactions, and full-text search built in.
The FTS tables are written in the same transaction as the rows they index, in plain code
rather than triggers, so the sync is easy to read. It is single-writer, which suits one
person or a small team on one machine, and would need replacing (for example Postgres
with `tsvector` or OpenSearch) for many concurrent writers.

**Small surface.** Typer for the CLI, the official `anthropic` and `mcp` SDKs, pypdf. The
Claude client is passed into `ask()` so tests can use a fake; nothing in the test suite
needs an API key or the network.

## Evaluation

`evals/corpus/` holds six short documents I wrote for this purpose, all marked as
synthetic: an incident report, an API design note, a concrete lab report (.txt), a deploy
runbook with a planted prompt injection, a quarterly reliability review, and a four-page
pump maintenance manual as a real PDF (generated by `evals/make_sample_pdf.py`, so there is
no extra dependency). `evals/questions.jsonl` has 20 questions: 18 with the expected
document (and page, for the PDF) and 2 that the library cannot answer.

`brain eval` ingests the corpus into a throwaway database and measures retrieval over the
top 10 chunks. A chunk counts as a match if it comes from the expected document and, when
a page is given, from that page.

Actual output of `uv run brain eval` (14 October 2026):

```
Retrieval over 18 answerable questions (top 10 chunks):
  hit@1 0.94 (17)
  hit@5 1.00 (18)
  MRR   0.97
  miss q11: rank 2  (How much traffic does a canary get and for how long?)
```

The miss is a typical BM25 failure: "much" and "traffic" also occur in the rate-limiting
design note ("costs too much memory at our traffic"), which outranks the runbook.

Read these numbers with care. The corpus is 6 documents and 15 chunks, and I wrote both
the documents and the questions, so the questions share vocabulary with the answers more
than real users would. The questions were written before the first run and not changed
afterwards, but the figures say the pipeline works end to end; they do not predict
quality on thousands of real reports. On a real library I would build the question set
from questions people actually asked, with the answering document labelled by someone
who knows the material.

`brain eval --answers` also calls Claude for every question and reports how often the
answer cites the expected document (and page), whether the two unanswerable questions
get `INSUFFICIENT_EVIDENCE`, and whether the planted instruction leaks into the answer.
I have not run it for this README: no API key was available where it was built, so there
are no answer-quality numbers here. The code path is covered by tests with a fake client.

## Tests

`uv run pytest -q` runs 58 tests in a few seconds, with no API key and no network:
chunking (size cap, whole words, overlap), ingest idempotency and replacement, PDF page
numbers, FTS query sanitising against hostile input, ranking on the sample corpus,
document and tag filters, notes and backlinks, prompt building (delimiters, escaping,
injection rule), citation parsing and validation, `ask` with a fake Claude client
(citations, dropped markers, insufficient evidence, refusal, no-match short circuit),
MCP tool registration and read-only defaults, a real stdio round trip to `brain mcp`,
and CLI smoke tests.

## Limitations and next steps

- Keyword retrieval only. Next: hybrid retrieval and a reranker, kept only if they improve
  the eval on real questions.
- Answers come from documents only; notes are searchable but not used as answer context.
- Scanned PDFs without a text layer produce no chunks (ingest reports them as `empty`).
  Tables and multi-column layouts come out as whatever pypdf extracts.
- Files that are deleted from disk stay in the library until removed by hand; there is no
  delete command or folder watcher yet.
- Citations are checked for existence, not for whether the chunk supports the claim. An
  LLM-graded support check would make the answer eval stronger.
- Anthropic's API has native citations (`search_result` content blocks with
  `citations: {enabled: true}`), which return the cited span instead of a number. The
  numbered-marker approach here is simpler to read and test; moving to native citations
  would be the next step for exact quotes.
- One user, one machine, single-writer SQLite. No access control: anyone who can run the
  MCP server can read the whole library.

## Layout

```
src/personal_ai_brain/
  db.py           schema: documents, chunks, notes, links + FTS5 tables
  chunking.py     paragraph packing with overlap
  ingest.py       PDF/Markdown/text extraction, hashing, re-ingest
  search.py       FTS5 query sanitising, BM25 search, snippets, filters
  notes.py        notes, tags, [[wiki links]], backlinks
  answer.py       prompt building, Claude call, citation validation
  evaluation.py   retrieval and answer metrics
  mcp_server.py   MCP tools (read-only unless --allow-writes)
  cli.py          the `brain` command
  config.py       environment settings, Claude client
evals/            synthetic corpus, questions, PDF generator
tests/            pytest suite (no network)
```
