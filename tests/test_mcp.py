import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from personal_ai_brain.config import Settings
from personal_ai_brain.mcp_server import build_server


def settings_for(conn: sqlite3.Connection) -> Settings:
    db_file = conn.execute("PRAGMA database_list").fetchone()["file"]
    return Settings(db_path=Path(db_file), model="test-model", top_k=6)


def tool_names(server) -> dict[str, object]:
    return {t.name: t for t in asyncio.run(server.list_tools())}


def test_read_only_by_default(library: sqlite3.Connection) -> None:
    tools = tool_names(build_server(settings_for(library)))
    assert set(tools) == {"search_library", "get_chunk", "ask_library", "list_documents"}
    for name in ("search_library", "get_chunk", "list_documents"):
        assert tools[name].annotations.read_only_hint is True


def test_add_note_only_with_allow_writes(library: sqlite3.Connection) -> None:
    tools = tool_names(build_server(settings_for(library), allow_writes=True))
    assert "add_note" in tools
    assert tools["add_note"].annotations.read_only_hint is False


def test_search_then_get_chunk(library: sqlite3.Connection) -> None:
    server = build_server(settings_for(library))
    found = asyncio.run(server.call_tool("search_library", {"query": "bearing grease", "limit": 2}))
    first = found.structured_content["result"][0]
    assert first["document"] == "pump station maintenance" and first["page"] == 3

    chunk = asyncio.run(server.call_tool("get_chunk", {"chunk_id": first["chunk_id"]}))
    assert "NLGI grade 2" in json.loads(chunk.content[0].text)["text"]


def test_add_note_writes_to_the_library(library: sqlite3.Connection) -> None:
    server = build_server(settings_for(library), allow_writes=True)
    args = {"title": "From MCP", "body": "See [[Pump Manual]].", "tags": ["mcp"]}
    asyncio.run(server.call_tool("add_note", args))
    assert library.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 1


def test_server_starts_over_stdio(library: sqlite3.Connection) -> None:
    """End to end: spawn `brain mcp` as a subprocess and talk MCP to it over stdio."""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", "from personal_ai_brain.cli import app; app()", "mcp"],
        env={**os.environ, "BRAIN_DB": str(settings_for(library).db_path)},
    )

    async def session() -> tuple[list[str], str]:
        async with stdio_client(params) as (read, write), ClientSession(read, write) as s:
            await s.initialize()
            tools = await s.list_tools()
            found = await s.call_tool("search_library", {"query": "canary", "limit": 1})
            return sorted(t.name for t in tools.tools), found.content[0].text

    names, text = asyncio.run(session())
    assert names == ["ask_library", "get_chunk", "list_documents", "search_library"]
    assert "Runbook: Deploying the Checkout Service" in text
