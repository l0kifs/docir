"""The ``docir mcp`` subcommands — serving the tool surface to an MCP client.

Everything here is import-order discipline. ``fastmcp`` costs ~0.3s to import
on top of what the CLI already loads, and exactly one command needs it — so
:mod:`docir.entry_points.mcp.server` (which imports it at module scope) is
imported *inside* the command rather than beside this docstring. Hoisting it
would put that 0.3s on every ``docir get``, which is the read path the whole
project is shaped around being cheap.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

import typer

from docir import __version__
from docir.config.settings import Settings
from docir.entry_points.cli.runner import get_state
from docir.modules.documents.api import describe_schema, load_schema
from docir.platform.transport.messages import RequestExecutor

if TYPE_CHECKING:  # the annotation only — the real import stays inside the command
    from fastmcp import FastMCP

mcp_app = typer.Typer(help="Serve docir over the Model Context Protocol.", no_args_is_help=True)

#: The transports ``serve`` accepts. stdio is what an MCP client spawns; http is
#: for a client that connects to a URL instead.
TRANSPORTS = ("stdio", "http")


@mcp_app.command("serve")
def serve(
    transport: Annotated[
        str,
        typer.Option(
            "--transport",
            help=f"How the client reaches the server ({', '.join(TRANSPORTS)}).",
        ),
    ] = "stdio",
    host: Annotated[str, typer.Option("--host", help="Bind address for --transport http.")] = (
        "127.0.0.1"
    ),
    port: Annotated[int, typer.Option("--port", help="Port for --transport http.")] = 8000,
) -> None:
    """Expose this store's documents to an MCP client (Claude, Cursor, Codex, ...).

    Serves the same command vocabulary the CLI does, through the same
    dispatcher — the tools are a second transport, not a second implementation.
    Requests go through the daemon by default, so the embedding model stays warm
    across calls and writes stay serialized; --no-daemon runs them in-process.

    Register it with a client by pointing at this command, e.g. for Claude Code:

        claude mcp add docir -- docir mcp serve

    stdio is the transport an MCP client spawns and speaks over the child's
    stdin/stdout. --transport http serves it over HTTP instead.
    """
    if transport not in TRANSPORTS:
        raise typer.BadParameter(
            f"expected one of {', '.join(TRANSPORTS)}", param_hint="--transport"
        )
    server = build_server(get_state().settings)
    if transport == "http":
        server.run(transport="http", host=host, port=port)
    else:
        server.run()


def build_server(settings: Settings) -> FastMCP:
    """Resolve the executor and the schema reader, then wire the tool surface.

    Separate from :func:`serve` so a test can build the server and drive it with
    an in-memory client, which is the whole of what ``serve`` does before it
    blocks on a transport.
    """
    from docir.entry_points.mcp.server import build_mcp_server

    return build_mcp_server(
        _executor_for(settings),
        describe_schema=lambda: describe_schema(load_schema(settings.schema_path)),
        version=__version__,
    )


def _executor_for(settings: Settings) -> RequestExecutor:
    """The daemon executor unless ``--no-daemon`` was passed.

    The in-process container is deliberately never closed: it lives as long as
    the server process, which is the point of holding one open — a per-call
    container would reload the embedding model on every tool call.
    """
    if settings.use_daemon:
        from docir.entry_points.daemon.socket_executor import SocketExecutor

        return SocketExecutor(settings)
    from docir.entry_points.cli import rendering
    from docir.entry_points.composition import build_in_process_executor

    # Before the transport is up, so a client spawning this sees nothing happen
    # for as long as the model takes to load — or to download.
    with rendering.progress("loading the embedding model"):
        executor, _container = build_in_process_executor(settings)
    return executor
