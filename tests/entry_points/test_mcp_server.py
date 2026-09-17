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
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from conftest import FixedClock
from docir.config.settings import Settings
from docir.entry_points.composition import Container, InProcessExecutor
from docir.entry_points.dispatch import Dispatcher
from docir.entry_points.federation import FEDERATED_COMMANDS
from docir.entry_points.mcp.cmds import build_server
from docir.entry_points.mcp.server import build_mcp_server
from docir.modules.documents.api import describe_schema, load_schema
from docir.modules.release.api import describe_deprecations
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
    "schema_drift": "docir_schema_drift",
    "store_status": "docir_store_status",
    "deprecations": "docir_deprecations",
    "repair": "docir_check_fix",
    "lint": "docir_lint",
    "bench": "docir_bench",
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
    commands = set(dispatcher.commands) - UNEXPOSED_COMMANDS
    assert commands == set(COMMAND_TOOLS), "dispatcher vocabulary and COMMAND_TOOLS disagree"

    exposed = set(list_tools(server))
    missing = set(COMMAND_TOOLS.values()) - exposed
    assert not missing, f"dispatcher commands with no MCP tool: {sorted(missing)}"


def test_every_federated_command_takes_stores(server) -> None:
    """An MCP-only agent must be able to name a peer store per call.

    The CLI has `--store`; without the matching parameter here, the two
    transports answer different questions — which is the drift the whole MCP
    module exists to prevent. Asserted from the published schema, so a parameter
    the protocol cannot express fails here too.
    """
    tools = list_tools(server)
    missing = sorted(
        COMMAND_TOOLS[command]
        for command in FEDERATED_COMMANDS
        if "stores" not in tools[COMMAND_TOOLS[command]].inputSchema.get("properties", {})
    )
    assert not missing, f"federated commands whose tool cannot name a peer store: {missing}"


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
        "docir_bench",
        "docir_tag_list",
        "docir_check",
        "docir_schema_drift",
        "docir_store_status",
        "docir_deprecations",
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
    assert call(server, "docir_embed_flush", {}) == {"embedded": 0, "vectors": 0}
    # Nothing to repair: the orphan is a warning `repair` deliberately leaves.
    # `actions` is absent rather than empty — trimming drops it, and an absent
    # field means its default.
    repaired = call(server, "docir_check_fix", {})
    assert "actions" not in repaired
    assert [issue["kind"] for issue in repaired["remaining"]] == ["orphan"]
    assert call(server, "docir_lint", {}) == []


def _cli_tree() -> dict[str, Any]:
    """The Typer command tree as plain data, the same source the prose test reads."""
    import typer.main

    from docir.entry_points.cli import app as cli_app

    def node(command: Any) -> dict[str, Any]:
        return {
            "options": [
                {"flags": list(param.opts)}
                for param in getattr(command, "params", ())
                if getattr(param, "opts", None)
            ],
            "commands": {name: node(sub) for name, sub in getattr(command, "commands", {}).items()},
        }

    return node(typer.main.get_command(cli_app.app))


TREE = _cli_tree()


# --- argument parity: a CLI flag must reach the tool that mirrors it ---------
#
# The vocabulary test above pins tool *names* against the dispatcher, which is
# what stops a new command reaching only the CLI. It says nothing about
# arguments, and that is where the surface actually drifted: `--also`,
# `--explain` on `context` and `--explain` on `search` all shipped to the CLI
# and reached no tool, so an MCP client could not ask for them at all. That is
# exactly the "a tool and its command cannot answer differently" property
# adr-354a4270ecd8 exists for.

#: `tool -> CLI command` for the tools that mirror one directly.
#:
#: The **write** path was absent from this map until it was noticed that the two
#: largest surfaces in the CLI — `add` (14 flags) and `update` (21) — were the
#: two nothing checked. Read tools drifted once and were pinned; the same drift
#: on `update` would cost an MCP agent a way to edit a document at all, which is
#: worse than a missing `--explain`.
_MIRRORED = {
    "docir_context": "context",
    "docir_search": "search",
    "docir_query": "query",
    "docir_get": "get",
    "docir_bench": "bench",
    "docir_add": "add",
    "docir_update": "update",
    "docir_delete": "delete",
    "docir_reindex": "reindex",
    "docir_check": "check",
    "docir_lint": "lint",
}

#: command -> {CLI flag: tool property}, where the two deliberately differ.
#: Renaming a tool argument breaks an agent's saved prompts, so a difference is
#: kept and declared rather than reconciled.
#:
#: Keyed by command because one flag spells two different properties: `--type`
#: is `types` on `query` (the tool takes a list and says so in the plural, where
#: the CLI repeats a singular flag) and `set_type` on `update` (the tool names
#: every write field `set_*`, and `type` there would read as the type to create).
#: A flat map cannot hold both, and the one it holds silently excuses the other.
_FLAG_ALIASES = {
    "query": {"type": "types", "status": "statuses", "tag": "tags"},
    "update": {"type": "set_type"},
    "reindex": {"changed": "changed_only"},
}

#: command -> {CLI flag: why it reaches no tool}. A difference has to be stated
#: here to pass, so "the tool is missing this" and "the tool is not meant to
#: have this" stop looking identical to a reader — and a reason nobody can write
#: is the signal that the flag is drift rather than design.
_CLI_ONLY = {
    "add": {
        "id": (
            "ids are never chosen by the caller — `docir_add` says so in its own "
            "docstring. `--id` exists to adopt an id while migrating a numbered "
            "corpus, which is a human's one-off, not an agent's write."
        ),
        "body-file": "a shell-side way to produce `body`; the tool takes the string directly",
        "stdin": "a shell-side way to produce `body`; the tool takes the string directly",
    },
    "update": {
        "body-file": "a shell-side way to produce `body`; the tool takes the string directly",
        "stdin": "a shell-side way to produce `body`; the tool takes the string directly",
    },
    "check": {
        "fix": "a different command (`repair`), exposed under its own name as `docir_check_fix`",
        "strict": "shapes the process exit code for CI; a tool result has no exit code",
        "strict-all": "shapes the process exit code for CI; a tool result has no exit code",
    },
    "lint": {
        "deep": (
            "a confirmation guard on the CLI, documented as 'without it lint does "
            "nothing'. `docir_lint` is the deep run, so a tool flag would have "
            "exactly one legal value."
        ),
    },
}

#: Flags that shape *rendering*, not the request. They never reach a tool
#: because a tool result is JSON by construction.
#:
#: `--store` is absent from this map on purpose: it is a *global* flag rather
#: than one of these commands', and which tools may name a peer is already
#: pinned by the federation case above — a tool that federates must take
#: `stores`, and `docir_bench`, which does not federate, must not.
_PRESENTATION_FLAGS = frozenset({"pretty", "json", "no-trim", "include-resolved"})


def _cli_flags(command: str) -> set[str]:
    node = TREE
    for part in command.split():
        node = node["commands"][part]
    return {
        flag.lstrip("-")
        for option in node["options"]
        for flag in option["flags"]
        if flag.startswith("--")
    } - _PRESENTATION_FLAGS


@pytest.mark.parametrize("tool", sorted(_MIRRORED))
def test_every_cli_flag_reaches_its_tool(server, tool: str) -> None:
    command = _MIRRORED[tool]
    flags = _cli_flags(command)
    # Without this the test passes loudest when it is checking nothing: a broken
    # TREE lookup, or a command whose options moved behind a subcommand, yields
    # an empty set and so an empty `missing`. Every mirrored command has at
    # least one flag — that is why it is worth mirroring.
    assert flags, f"`docir {command}` reports no flags — _cli_flags is not reading the CLI"
    properties = set(list_tools(server)[tool].inputSchema.get("properties", {}))
    aliases = _FLAG_ALIASES.get(command, {})
    missing = {
        flag
        for flag in flags - set(_CLI_ONLY.get(command, {}))
        if aliases.get(flag, flag).replace("-", "_") not in properties
    }
    assert not missing, (
        f"{tool} cannot be asked for {sorted(missing)} — `docir {command}` can. "
        f"Add the argument, alias it in _FLAG_ALIASES, or say why it is CLI-only in _CLI_ONLY."
    )


@pytest.mark.parametrize(
    ("command", "flag"),
    sorted((command, flag) for command, flags in _FLAG_ALIASES.items() for flag in flags),
)
def test_every_alias_is_still_needed(command: str, flag: str) -> None:
    """A stale alias would silently excuse a genuinely missing argument."""
    assert command in _MIRRORED.values(), (
        f"{command!r} is aliased and no longer mirrored — drop it from _FLAG_ALIASES"
    )
    assert flag in _cli_flags(command), (
        f"`docir {command}` has no --{flag} — drop it from _FLAG_ALIASES"
    )


@pytest.mark.parametrize(
    ("command", "flag"),
    sorted((command, flag) for command, flags in _CLI_ONLY.items() for flag in flags),
)
def test_every_cli_only_flag_is_still_cli_only(server, command: str, flag: str) -> None:
    """A stale exemption excuses a missing argument exactly as a stale alias does.

    Both halves matter. A flag dropped from the CLI leaves a reason standing for
    nothing; a flag that later *gained* a tool argument leaves this map claiming
    a difference that no longer exists, which is how the next reader concludes
    the omission was meant.
    """
    assert flag in _cli_flags(command), (
        f"`docir {command}` has no --{flag} — drop it from _CLI_ONLY"
    )
    tool = next(name for name, mirrored in _MIRRORED.items() if mirrored == command)
    properties = set(list_tools(server)[tool].inputSchema.get("properties", {}))
    assert flag.replace("-", "_") not in properties, (
        f"{tool} now takes {flag!r} — drop it from _CLI_ONLY, it is no longer CLI-only"
    )


class TestAStoreThatWillNotOpen:
    """The server comes up and says why (issue-2f07f83e6b84).

    Every refusal docir writes for an unreadable schema is worded for a reader —
    which version to install, which key to fix. Letting the exception escape
    `build_server` threw all of it away: the process died and the client saw
    `Connection closed`, on the one transport whose caller is definitely an
    agent. Each test here starts from a store that genuinely will not open.
    """

    def _broken_store(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
        """A store whose schema will not load, served in-process.

        ``DOCIR_NO_DAEMON`` because that is where the defect lives: with the
        daemon, ``build_server`` hands back a socket executor without ever
        reading the schema, and the failure happens in the daemon on the first
        call. In-process it happens while the server is being built, which is
        the path that used to take the process down with it.
        """
        monkeypatch.setenv("DOCIR_NO_DAEMON", "1")
        home = tmp_path / ".docir"
        (home / "docs").mkdir(parents=True)
        # Valid YAML, invalid schema: a partial block with no profile to overlay.
        (home / "docs-schema.yaml").write_text(
            "types:\n  decision:\n    level: 4\n", encoding="utf-8"
        )
        return Settings.resolve(home=home)

    def test_the_server_starts_and_every_tool_returns_the_reason(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        server = build_server(self._broken_store(tmp_path, monkeypatch))

        async def scenario() -> tuple[list[str], str, str]:
            async with Client(server) as client:
                tools = sorted(tool.name for tool in await client.list_tools())
                with pytest.raises(ToolError) as query_error:
                    await client.call_tool("docir_query", {"limit": 1})
                with pytest.raises(ToolError) as write_error:
                    await client.call_tool(
                        "docir_add", {"type": "decision", "title": "T", "description": "d"}
                    )
                return tools, str(query_error.value), str(write_error.value)

        listed, reading, writing = asyncio.run(scenario())
        # The surface is unchanged — every tool, by name, not a count. The
        # reader has to be able to tell "this store cannot be opened" from
        # "docir does not do that here", and a missing tool says the second.
        assert listed == sorted({*COMMAND_TOOLS.values(), "docir_schema"})
        for message in (reading, writing):
            assert "must define a string 'prefix'" in message

    def test_the_schema_tool_fails_the_same_way(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # It is the one tool that does not go through the executor, so it is the
        # one that would have kept raising a raw exception — and a closure over
        # the handler's variable raised NameError instead of the store error.
        server = build_server(self._broken_store(tmp_path, monkeypatch))

        async def scenario() -> str:
            async with Client(server) as client:
                with pytest.raises(ToolError) as error:
                    await client.call_tool("docir_schema", {})
                return str(error.value)

        message = asyncio.run(scenario())
        assert "must define a string 'prefix'" in message
        assert "NameError" not in message

    def test_the_handshake_already_carries_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Instructions are read at connect. An agent that has to call a tool to
        # find out has already written its plan around tools that cannot work.
        server = build_server(self._broken_store(tmp_path, monkeypatch))

        async def scenario() -> str:
            async with Client(server) as client:
                return client.initialize_result.instructions or ""

        instructions = asyncio.run(scenario())
        assert instructions.startswith("THIS STORE CANNOT BE OPENED:")
        assert "must define a string 'prefix'" in instructions
        # In front of the usual instructions, not instead of them.
        assert "docir stores this project" in instructions

    def test_a_store_that_opens_is_untouched(self, settings: Settings) -> None:
        settings.ensure_directories()
        server = build_server(settings)

        async def scenario() -> str:
            async with Client(server) as client:
                return client.initialize_result.instructions or ""

        instructions = asyncio.run(scenario())
        assert not instructions.startswith("THIS STORE CANNOT BE OPENED")


class TestTheRegisterIsAskableOverTheWire:
    """`deprecations` — the one command about the build, not about a store.

    The dates in it were written for an agent, and an agent driving docir over
    MCP had no way to ask: `docir doctor` carries them and has no tool
    (issue-8b227c299e63). Every test here drives the real tool surface, because
    the defect was never in the register — it was in what could reach it.
    """

    def test_the_tool_returns_the_shipped_register(self, server) -> None:
        payload = call(server, "docir_deprecations")
        entries = {entry["subject"]: entry for entry in payload["deprecations"]}
        # The entry the register was built around: it warns at the moment of use
        # today, which reaches whoever ran it, once, with no date.
        assert "--include-resolved" in entries
        flag = entries["--include-resolved"]
        assert flag["replacement"] == "--include-inactive"
        assert flag["sunset"] == "2027-03-01"
        assert flag["overdue"] is False

    def test_the_verdict_is_read_from_the_clock_it_was_given(self) -> None:
        # The clock is injected rather than reached for, so a test can stand on
        # the far side of a sunset instead of waiting for it. Without that the
        # `overdue` half of the register is untestable until 2027.
        stub = Dispatcher.__new__(Dispatcher)
        stub._clock = FixedClock(date(2099, 1, 1))
        overdue = Dispatcher._deprecations(stub, {})["deprecations"]
        assert overdue, "the register is empty — nothing exercises this"
        assert all(entry["overdue"] for entry in overdue)
        # And the same register, read today, is not.
        assert not any(entry["overdue"] for entry in describe_deprecations(date.today()))

    def test_the_cli_and_the_tool_report_the_same_shape(self, container: Container) -> None:
        # One payload builder, so the two transports cannot disagree about a
        # field name — the drift adr-354a4270ecd8 exists to prevent, one layer
        # down from the commands themselves.
        over_the_wire = container.dispatcher.dispatch("deprecations", {})["deprecations"]
        assert over_the_wire == describe_deprecations(date.today())
