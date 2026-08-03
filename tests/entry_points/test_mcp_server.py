"""The MCP tool surface, driven by a real FastMCP client over the in-memory transport.

These are contract tests, not unit tests: the client speaks actual MCP against
an actual server, so a tool whose signature the protocol cannot express, or a
result the protocol cannot serialize, fails here rather than in someone's
editor. The transport is in-memory (``Client(server)``), which is FastMCP's own
testing seam — no subprocess, no sockets. ``test_e2e_mcp.py`` covers the
subprocess path.

The thing most worth guarding is drift: the MCP server exists precisely so the
tools and the CLI cannot answer differently, and they only cannot while every
dispatcher command has a tool.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from docir.config.settings import Settings
from docir.entry_points.composition import Container, InProcessExecutor
from docir.entry_points.dispatch import Dispatcher
from docir.entry_points.mcp.server import build_mcp_server
from docir.modules.documents.api import describe_schema, load_schema
from docir.platform.errors import DaemonError
from docir.platform.transport.messages import Request, RequestExecutor, Response

#: ``ping`` is the daemon's liveness probe, not a document operation, so it is
#: the one command deliberately absent from the tool surface.
UNEXPOSED_COMMANDS = frozenset({"ping"})

#: command name -> tool name. Spelled out rather than derived, so renaming a
#: tool has to be a decision: an agent's saved prompts break when it changes.
COMMAND_TOOLS = {
    "add": "docir_add",
    "update": "docir_update",
    "get": "docir_get",
    "query": "docir_query",
    "search": "docir_search",
    "context": "docir_context",
    "archive": "docir_archive",
    "unarchive": "docir_unarchive",
    "delete": "docir_delete",
    "tag_add": "docir_tag_add",
    "tag_list": "docir_tag_list",
    "tag_rename": "docir_tag_rename",
    "tag_remove": "docir_tag_remove",
    "reindex": "docir_reindex",
    "check": "docir_check",
    "repair": "docir_check_fix",
    "lint": "docir_lint",
    "embed_flush": "docir_embed_flush",
}


@pytest.fixture
def server(container: Container, settings: Settings):
    """The tool surface wired onto the in-process executor the CLI uses."""
    return build_mcp_server(
        InProcessExecutor(container.dispatcher),
        describe_schema=lambda: describe_schema(load_schema(settings.schema_path)),
        version="0.0.0-test",
    )


def call(server, name: str, arguments: dict[str, Any] | None = None) -> Any:
    """Call one tool through a real client session and return its parsed data."""

    async def _session():
        async with Client(server) as client:
            result = await client.call_tool(name, arguments or {})
            return result.data

    return asyncio.run(_session())


def call_raw(server, name: str, arguments: dict[str, Any] | None = None):
    """Call one tool without raising, so a test can inspect the error result."""

    async def _session():
        async with Client(server) as client:
            return await client.call_tool(name, arguments or {}, raise_on_error=False)

    return asyncio.run(_session())


def list_tools(server) -> dict[str, Any]:
    async def _session():
        async with Client(server) as client:
            return {tool.name: tool for tool in await client.list_tools()}

    return asyncio.run(_session())


# -- the drift guard --------------------------------------------------------


def test_every_dispatcher_command_has_a_tool(server, dispatcher: Dispatcher) -> None:
    """A new command must reach MCP clients, not just the CLI.

    Asserts the *names*, not a count: a count cannot tell "every command is
    exposed" from "the mapping and the dispatcher drifted in the same
    direction". `ping` is excluded explicitly so removing it from the surface
    stays a decision rather than an omission.
    """
    commands = set(dispatcher._handlers) - UNEXPOSED_COMMANDS
    assert commands == set(COMMAND_TOOLS), "dispatcher vocabulary and COMMAND_TOOLS disagree"

    exposed = set(list_tools(server))
    missing = set(COMMAND_TOOLS.values()) - exposed
    assert not missing, f"dispatcher commands with no MCP tool: {sorted(missing)}"


def test_read_tools_are_annotated_read_only(server) -> None:
    """A client that gates writes on `readOnlyHint` must be able to trust it."""
    tools = list_tools(server)

    def hinted(hint: str) -> set[str]:
        return {
            name for name, tool in tools.items() if getattr(tool.annotations, hint, None) is True
        }

    assert hinted("readOnlyHint") == {
        "docir_context",
        "docir_search",
        "docir_query",
        "docir_get",
        "docir_schema",
        "docir_tag_list",
        "docir_check",
        "docir_lint",
    }
    assert hinted("destructiveHint") == {"docir_delete", "docir_tag_remove"}


def test_server_instructions_state_the_two_rules(server) -> None:
    """The rules an agent cannot infer from a tool list have to be carried."""
    instructions = server.instructions or ""
    assert "Never edit the markdown files directly" in instructions
    assert "skeletons" in instructions


# -- the round trip ---------------------------------------------------------


def test_add_then_get_round_trip(server) -> None:
    created = call(
        server,
        "docir_add",
        {
            "type": "decision",
            "title": "Adopt MCP",
            "description": "Expose docir to MCP clients.",
            "body": "## Context\nAgents reach tools over MCP.\n",
        },
    )
    doc_id = created["id"]
    assert doc_id.startswith("adr-")

    fetched = call(server, "docir_get", {"doc_id": doc_id})
    assert fetched["title"] == "Adopt MCP"
    assert "Agents reach tools over MCP." in fetched["body"]


def test_read_paths_return_skeletons(server) -> None:
    """The token contract: only `docir_get` carries a body."""
    call(
        server,
        "docir_add",
        {
            "type": "decision",
            "title": "Adopt MCP",
            "description": "Expose docir to MCP clients.",
            "body": "A body long enough to notice if it leaked into a list path.",
        },
    )
    for tool, args in (
        ("docir_query", {}),
        ("docir_search", {"text": "MCP"}),
        ("docir_context", {"task": "expose docir over MCP"}),
    ):
        results = call(server, tool, args)
        assert results, f"{tool} returned nothing to check"
        assert all("body" not in view for view in results), f"{tool} leaked a body"


def test_update_edits_through_the_same_path(server) -> None:
    created = call(
        server,
        "docir_add",
        {"type": "decision", "title": "Adopt MCP", "description": "Expose docir."},
    )
    doc_id = created["id"]
    call(
        server,
        "docir_update",
        {"doc_id": doc_id, "append_section": "Consequences", "body": "Two transports, one gate."},
    )
    updated = call(server, "docir_update", {"doc_id": doc_id, "status": "accepted"})
    assert updated["status"] == "accepted"

    fetched = call(server, "docir_get", {"doc_id": doc_id})
    assert "## Consequences" in fetched["body"]
    assert "Two transports, one gate." in fetched["body"]

    call(
        server,
        "docir_update",
        {"doc_id": doc_id, "replace_section": "Consequences", "body": "One gate, two transports."},
    )
    rewritten = call(server, "docir_get", {"doc_id": doc_id})
    assert "One gate, two transports." in rewritten["body"]
    assert "Two transports, one gate." not in rewritten["body"]


def test_verified_stamps_a_date_and_replace_body_discards_the_old_one(server) -> None:
    """The two update modes that mean something the others do not.

    `verified` is the product's one trust signal — a human asserting they
    re-read the document — and `replace_body` is the only edit that throws away
    what is on disk rather than composing with it.
    """
    created = call(
        server,
        "docir_add",
        {
            "type": "decision",
            "title": "Adopt MCP",
            "description": "Expose docir.",
            "body": "The original body.",
        },
    )
    doc_id = created["id"]

    verified = call(server, "docir_update", {"doc_id": doc_id, "verified": True})
    assert verified["verified"], "the verified date was not stamped"

    # `replace_body` needs `force` every time, not only on a diverged file.
    with pytest.raises(ToolError, match="requires --force"):
        call(server, "docir_update", {"doc_id": doc_id, "replace_body": "No confirmation."})

    call(
        server,
        "docir_update",
        {"doc_id": doc_id, "replace_body": "A wholly new body.", "force": True},
    )
    fetched = call(server, "docir_get", {"doc_id": doc_id})
    assert fetched["body"].strip() == "A wholly new body."
    assert "The original body." not in fetched["body"]


def test_query_filters_reach_the_dispatcher(server) -> None:
    call(server, "docir_tag_add", {"key": "mcp", "description": "Model Context Protocol."})
    tagged = call(
        server,
        "docir_add",
        {
            "type": "decision",
            "title": "Adopt MCP",
            "description": "Expose docir.",
            "tags": ["mcp"],
        },
    )
    call(
        server,
        "docir_add",
        {"type": "decision", "title": "Something else", "description": "Unrelated."},
    )
    hits = call(server, "docir_query", {"tags": ["mcp"]})
    assert [hit["id"] for hit in hits] == [tagged["id"]]


def test_typed_relations_survive_the_wire(server) -> None:
    first = call(
        server,
        "docir_add",
        {"type": "decision", "title": "Old way", "description": "The previous decision."},
    )
    second = call(
        server,
        "docir_add",
        {
            "type": "decision",
            "title": "New way",
            "description": "The replacement.",
            "related": [f"{first['id']}:supersedes"],
        },
    )
    fetched = call(server, "docir_get", {"doc_id": second["id"]})
    assert fetched["related"] == [{"target": first["id"], "kind": "supersedes"}]


# -- shaping and errors -----------------------------------------------------


def test_results_are_trimmed_like_the_piped_cli(server) -> None:
    """Empty fields are dropped, so a tool result costs what piped JSON costs."""
    call(
        server,
        "docir_add",
        {"type": "decision", "title": "Adopt MCP", "description": "Expose docir."},
    )
    (view,) = call(server, "docir_query", {})
    assert "tags" not in view, "an empty list survived trimming"
    assert "owner" not in view, "a null field survived trimming"
    # False and 0 are information, not emptiness — they must survive.
    assert view["archived"] is False
    assert view["stale"] is False


def test_domain_errors_surface_as_tool_errors(server) -> None:
    """A refused write must reach the client as an error carrying its message."""
    with pytest.raises(ToolError, match="nope-0001"):
        call(server, "docir_get", {"doc_id": "nope-0001"})

    result = call_raw(
        server,
        "docir_add",
        {"type": "no-such-type", "title": "T", "description": "D"},
    )
    assert result.is_error
    assert "no-such-type" in str(result.content[0].text)


def test_a_transport_failure_is_a_tool_error_too(settings: Settings) -> None:
    """A dead daemon reaches the client as an error, not as a broken session.

    The dispatcher returns its failures as a `Response`; the transport *raises*
    them. Only the first path was wrapped at first, so an unreachable daemon
    would have propagated a DocirError out of the tool and been reported by
    FastMCP as an unhandled server fault rather than a docir error.
    """

    class DeadExecutor(RequestExecutor):
        def execute(self, request: Request) -> Response:
            raise DaemonError("daemon is not running and would not start")

    dead = build_mcp_server(
        DeadExecutor(),
        describe_schema=lambda: describe_schema(load_schema(settings.schema_path)),
        version="0.0.0-test",
    )
    with pytest.raises(ToolError, match="would not start"):
        call(dead, "docir_query", {})


def test_validation_is_not_bypassed_by_the_transport(server) -> None:
    """Tier 0 still refuses: the MCP path is a client, not a second write path."""
    with pytest.raises(ToolError, match="unregistered-tag"):
        call(
            server,
            "docir_add",
            {
                "type": "decision",
                "title": "Adopt MCP",
                "description": "Expose docir.",
                "tags": ["unregistered-tag"],
            },
        )


# -- the tools that are not dispatcher commands -----------------------------


def test_schema_tool_reports_the_merged_schema(server) -> None:
    """What an agent must read before its first write."""
    schema = call(server, "docir_schema", {})
    names = {entry["name"] for entry in schema["types"]}
    assert {"decision", "issue", "architecture"} <= names
    assert "supersedes" in schema["relation_types"]


def test_check_reports_findings_with_severity(server) -> None:
    call(
        server,
        "docir_add",
        {"type": "decision", "title": "Adopt MCP", "description": "Expose docir."},
    )
    findings = call(server, "docir_check", {})
    kinds = {finding["kind"] for finding in findings}
    assert "orphan" in kinds, "a document with no edges should be reported as an orphan"
    assert all(finding["severity"] == "warning" for finding in findings)


# -- the rest of the surface, exercised once each ----------------------------


def test_lifecycle_and_maintenance_tools_reach_their_commands(server) -> None:
    """One pass over the tools the round-trip tests do not touch.

    Not a smoke test for its own sake: every one of these is a hand-written
    payload, and a mistyped key would be silently swallowed by the dispatcher's
    coercion helpers (`_bool`/`_str` default rather than raise). Calling each
    one is what proves the payload it builds is the one the command expects.
    """
    call(server, "docir_tag_add", {"key": "mcp", "description": "Model Context Protocol."})
    doomed = call(
        server,
        "docir_add",
        {
            "type": "decision",
            "title": "To be removed",
            "description": "Exists to be deleted.",
            "tags": ["mcp"],
        },
    )
    keeper = call(
        server,
        "docir_add",
        {
            "type": "decision",
            "title": "Stays",
            "description": "Links to the doomed one.",
            "related": [f"{doomed['id']}:relates_to"],
        },
    )

    assert call(server, "docir_archive", {"doc_id": keeper["id"]})["archived"] is True
    assert call(server, "docir_unarchive", {"doc_id": keeper["id"]})["archived"] is False

    # An inbound edge blocks the delete; `force` strips it and says whose.
    with pytest.raises(ToolError):
        call(server, "docir_delete", {"doc_id": doomed["id"]})
    deleted = call(server, "docir_delete", {"doc_id": doomed["id"], "force": True})
    assert deleted["unlinked"] == [keeper["id"]]

    renamed = call(server, "docir_tag_rename", {"old": "mcp", "new": "protocol"})
    assert renamed["renamed"] == ["mcp", "protocol"]
    assert [tag["key"] for tag in call(server, "docir_tag_list", {})] == ["protocol"]
    assert call(server, "docir_tag_remove", {"key": "protocol", "force": True})["removed"] == (
        "protocol"
    )

    # One document survives the delete, so a full reindex sees exactly it;
    # `changed_only` sees nothing, because the write already indexed it.
    assert call(server, "docir_reindex", {})["documents_indexed"] == 1
    assert call(server, "docir_reindex", {"changed_only": True})["documents_indexed"] == 0
    assert call(server, "docir_embed_flush", {}) == {"embedded": 0}
    # Nothing to repair: the orphan is a warning `repair` deliberately leaves.
    # `actions` is absent rather than empty — trimming drops it, and an absent
    # field means its default.
    repaired = call(server, "docir_check_fix", {})
    assert "actions" not in repaired
    assert [issue["kind"] for issue in repaired["remaining"]] == ["orphan"]
    assert call(server, "docir_lint", {}) == []
