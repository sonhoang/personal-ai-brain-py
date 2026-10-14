from pathlib import Path

import pytest
from typer.testing import CliRunner

from personal_ai_brain.cli import app

from .conftest import CORPUS, QUESTIONS

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRAIN_DB", str(tmp_path / "cli.db"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def run(*args: str) -> str:
    result = runner.invoke(app, list(args))
    assert result.exit_code == 0, result.output
    return result.output


def test_ingest_search_and_docs() -> None:
    assert "6 added" in run("ingest", str(CORPUS))
    assert "6 unchanged" in run("ingest", str(CORPUS))
    out = run("search", "replication lag failover")
    assert out.splitlines()[0].startswith("Incident Report INC-2024-017")
    assert "pump station maintenance" in run("docs")


def test_search_with_unknown_doc_is_a_usage_error() -> None:
    run("ingest", str(CORPUS))
    result = runner.invoke(app, ["search", "pump", "--doc", "missing.pdf"])
    assert result.exit_code == 2


def test_notes_and_backlinks() -> None:
    run("note", "add", "Pump Manual", "--body", "Reference.", "--tag", "ops")
    run("note", "add", "Shift log", "--body", "Followed [[Pump Manual]].", "-t", "ops")
    assert "Shift log" in run("note", "list", "--tag", "ops")
    assert run("backlinks", "Pump Manual").strip() == "Shift log"
    assert "Shift log" in run("search", "followed", "--notes")


def test_ask_without_api_key_fails_cleanly() -> None:
    result = runner.invoke(app, ["ask", "What is the canary percentage?"])
    assert result.exit_code == 1
    assert "ANTHROPIC_API_KEY" in result.output


def test_eval_prints_metrics() -> None:
    out = run("eval", "--corpus", str(CORPUS), "--questions", str(QUESTIONS))
    assert "hit@1" in out and "hit@5" in out and "MRR" in out
