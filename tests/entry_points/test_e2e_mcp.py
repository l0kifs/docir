"""End-to-end: a real `docir mcp serve` subprocess, driven over real stdio.

The in-memory tests in ``test_mcp_server.py`` prove the tool surface; this
proves the thing they cannot — that the packaged entry point actually starts,
speaks MCP over its stdin/stdout, and reaches the store the environment points
it at. That is the exact path an MCP client takes, and every failure mode it
has (a stray print corrupting the stream, an import that only resolves in the
test process, a store resolved from the wrong CWD) is invisible in-process.

Marked ``slow``: it spawns a Python interpreter.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from fastmcp.exceptions import ToolError

from docir.config.settings import Settings

pytestmark = pytest.mark.slow


def _client(settings: Settings) -> Client:
    """A client that spawns `python -m docir mcp serve` against the temp store.

    ``DOCIR_HOME`` scopes the store, ``DOCIR_NO_DAEMON`` keeps the run
    in-process (a spawned daemon would outlive the test), and
    ``DOCIR_EMBEDDER`` keeps it off the real model. The parent environment is
    merged in rather than replaced — the child still needs PATH and the
    interpreter's own variables.
    """
    transport = StdioTransport(
        command=sys.executable,
        args=["-m", "docir", "mcp", "serve"],
        env={
            **os.environ,
            "DOCIR_HOME": str(settings.home),
            "DOCIR_NO_DAEMON": "1",
            "DOCIR_EMBEDDER": "deterministic",
        },
    )
    return Client(transport)


def _session(settings: Settings, work) -> Any:
    async def _run():
        async with _client(settings) as client:
            return await work(client)

    return asyncio.run(_run())


def test_the_packaged_entry_point_serves_mcp_over_stdio(settings: Settings) -> None:
    """One session: list the tools, write a document, read it back, fail a read."""

    async def work(client: Client) -> dict[str, Any]:
        tools = {tool.name for tool in await client.list_tools()}
        created = await client.call_tool(
            "docir_add",
            {
                "type": "decision",
                "title": "Serve MCP over stdio",
                "description": "The transport an MCP client spawns.",
                "body": "## Context\nThe client owns the process.\n",
            },
        )
        doc_id = created.data["id"]
        fetched = await client.call_tool("docir_get", {"doc_id": doc_id})
        ranked = await client.call_tool("docir_context", {"task": "serving over stdio"})
        missing = await client.call_tool(
            "docir_get", {"doc_id": "adr-000000000000"}, raise_on_error=False
        )
        return {
            "tools": tools,
            "id": doc_id,
            "fetched": fetched.data,
            "ranked": ranked.data,
            "missing": missing,
        }

    result = _session(settings, work)

    assert "docir_context" in result["tools"]
    assert result["id"].startswith("adr-")
    assert "The client owns the process." in result["fetched"]["body"]
    # The store the child resolved is the one the environment named, not a
    # global fallback — the document it wrote is on disk under it.
    assert list(settings.docs_root.rglob(f"{result['id']}-*.md"))
    assert [hit["id"] for hit in result["ranked"]] == [result["id"]]
    assert all("body" not in hit for hit in result["ranked"]), "a body crossed the wire"
    assert result["missing"].is_error


def test_a_domain_error_reaches_the_client_as_a_tool_error(settings: Settings) -> None:
    """An exit code cannot cross stdio — the message has to arrive as MCP does it."""

    async def work(client: Client) -> str:
        with pytest.raises(ToolError) as caught:
            await client.call_tool("docir_add", {"type": "nope", "title": "T", "description": "D"})
        return str(caught.value)

    assert "nope" in _session(settings, work)
