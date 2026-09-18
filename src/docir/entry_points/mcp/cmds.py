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
from docir.platform.errors import DocirError
from docir.platform.transport.messages import Request, RequestExecutor, Response

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

    A store that will not open does not stop the server. Run in-process
    (`--no-daemon`), the tools all list and every call returns the reason — the
    schema error naming the key or the docir version — and the same sentence
    leads the server's instructions, so a client has it at the handshake.
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

    A store that will not open **does not stop the server** (issue-2f07f83e6b84).
    Every refusal docir writes for an unreadable schema is worded for a reader —
    which version to install, which key to fix — and letting the exception escape
    here throws all of it away: the process dies and the client sees
    ``Connection closed``. The CLI has never done that, because `runner.py` maps
    a ``DocirError`` onto an exit code and prints it; this is the same mapping,
    one transport later.

    So the surface comes up either way and carries the reason instead of the
    answers. There is nothing else it could carry: every tool here reads or
    writes the store.
    """
    from docir.entry_points.mcp.server import build_mcp_server

    store_error: DocirError | None = None
    try:
        executor = _executor_for(settings)
    except DocirError as exc:
        # Bound outside the ``except`` block on purpose: Python unbinds the name
        # at the end of it, so a closure built here would raise NameError at the
        # first call instead of the store error it was made to carry.
        store_error = exc
    if store_error is not None:
        return build_mcp_server(
            _UnavailableExecutor(store_error),
            describe_schema=lambda: _raise(store_error),
            version=__version__,
            unavailable=str(store_error),
        )
    return build_mcp_server(
        executor,
        describe_schema=lambda: describe_schema(load_schema(settings.schema_path)),
        version=__version__,
    )


def _raise(error: DocirError) -> dict[str, object]:
    """Report the store error from the one tool that does not use the executor.

    A ``ToolError``, not the ``DocirError`` itself, so ``docir_schema`` fails the
    way every other tool here fails: ``_Gateway`` performs exactly this
    conversion for the ones that go through the executor, and a raw exception
    would reach the client wrapped in FastMCP's own "Error calling tool" prose.

    Imported inside the function, like every other fastmcp name here: importing
    the CLI must not drag fastmcp in, because interpreter startup is what a read
    costs (issue-9509f9fa3631), and a test holds that line.
    """
    from fastmcp.exceptions import ToolError

    raise ToolError(str(error))


class _UnavailableExecutor(RequestExecutor):
    """Answers every command with the reason the store would not open.

    A :class:`RequestExecutor` rather than a special case inside each tool, so
    the tools are registered exactly as they always are and the error travels
    the path a dispatcher error already travels — ``_Gateway`` turns a
    ``DocirError`` into a ``ToolError``, which is what an MCP client renders.
    One implementation, the rule adr-354a4270ecd8 exists to keep.
    """

    def __init__(self, error: DocirError) -> None:
        self._error = error

    def execute(self, request: Request) -> Response:
        raise self._error


def _executor_for(settings: Settings) -> RequestExecutor:
    """The daemon executor unless ``--no-daemon`` was passed, or it will not start.

    The in-process container is deliberately never closed: it lives as long as
    the server process, which is the point of holding one open — a per-call
    container would reload the embedding model on every tool call.

    The fallback goes through the same :func:`start_daemon_executor` the CLI
    uses, rather than a second `SocketExecutor(settings)` beside it. This server
    is the transport most likely to meet the failure it exists for — an MCP
    client spawns it into whatever environment the client runs in, which is
    where a read-only sandbox denies the socket — and it is exactly the seam
    where a CLI-only fix would have gone unnoticed (adr-354a4270ecd8).
    """
    from docir.entry_points.cli import rendering

    if settings.use_daemon:
        from docir.entry_points.daemon.socket_executor import start_daemon_executor

        daemon = start_daemon_executor(settings)
        if daemon is not None:
            return daemon
    from docir.entry_points.composition import build_in_process_executor

    # Before the transport is up, so a client spawning this sees nothing happen
    # for as long as the model takes to load — or to download.
    with rendering.progress("loading the embedding model"):
        executor, _container = build_in_process_executor(settings)
    return executor
