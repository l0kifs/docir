"""The ``docir mcp serve`` command — what it resolves before it blocks.

Everything interesting about ``serve`` happens before ``server.run()``: which
executor it picks, which store the schema comes from, and whether it refuses a
transport it cannot serve. ``run`` itself is FastMCP's and blocks forever, so it
is stubbed here and driven for real in ``test_e2e_mcp.py``.
"""

from __future__ import annotations

import subprocess
import sys

import pytest
from typer.testing import CliRunner

from docir.config.settings import Settings
from docir.entry_points.cli.app import app
from docir.entry_points.composition import InProcessExecutor
from docir.entry_points.daemon.socket_executor import SocketExecutor
from docir.entry_points.mcp import cmds

runner = CliRunner()


@pytest.fixture
def served(monkeypatch):
    """Capture the `run` call instead of blocking on a transport."""
    calls: list[dict[str, object]] = []

    def fake_run(self, **kwargs: object) -> None:
        calls.append({"server": self, **kwargs})

    monkeypatch.setattr("fastmcp.FastMCP.run", fake_run)
    return calls


def test_serve_defaults_to_stdio(settings: Settings, served) -> None:
    result = runner.invoke(app, ["mcp", "serve"])
    assert result.exit_code == 0, result.output
    assert len(served) == 1
    # No transport kwarg at all: FastMCP's own default is stdio, and naming it
    # here would be a second place to keep in sync.
    assert "transport" not in served[0]
    assert served[0]["server"].name == "docir"


def test_serve_http_passes_the_bind_address_through(settings: Settings, served) -> None:
    result = runner.invoke(
        app, ["mcp", "serve", "--transport", "http", "--host", "0.0.0.0", "--port", "9123"]
    )
    assert result.exit_code == 0, result.output
    assert served[0]["transport"] == "http"
    assert served[0]["host"] == "0.0.0.0"
    assert served[0]["port"] == 9123


def test_an_unknown_transport_is_refused_before_anything_starts(settings: Settings, served) -> None:
    """Refused at the flag, not after the store is opened and the model loaded."""
    result = runner.invoke(app, ["mcp", "serve", "--transport", "carrier-pigeon"])
    assert result.exit_code != 0
    assert not served, "the server was built before the transport was validated"


def test_no_daemon_serves_in_process(settings: Settings) -> None:
    """`--no-daemon` holds one container open rather than talking to a daemon."""
    assert isinstance(cmds._executor_for(settings), InProcessExecutor)


def test_the_default_executor_is_the_daemon(settings: Settings) -> None:
    """The daemon is the point: one warm embedding model across every tool call.

    Constructing the executor does not spawn anything — `SocketExecutor` only
    reaches for the daemon when a request is actually executed.
    """
    daemonized = settings.model_copy(update={"use_daemon": True})
    assert isinstance(cmds._executor_for(daemonized), SocketExecutor)


def test_the_server_reads_the_schema_from_the_resolved_store(settings: Settings) -> None:
    """The schema tool must follow the same store every other command follows."""
    server = cmds.build_server(settings)
    assert server.instructions and "docir_context" in server.instructions


@pytest.mark.slow
def test_importing_the_cli_does_not_import_fastmcp() -> None:
    """`fastmcp` must stay off the read path's import graph.

    It is a default dependency now, so nothing but the deferred import inside
    `build_server` keeps its ~0.3s out of every `docir get`. Hoisting that
    import to the top of `cmds.py` would break nothing any other test checks,
    and would slow every command in the project.

    Checked in a subprocess because this test session has already imported
    fastmcp — in-process, `sys.modules` cannot answer the question.
    """
    probe = (
        "import sys; import docir.entry_points.cli.app; "
        "sys.exit(1 if 'fastmcp' in sys.modules else 0)"
    )
    assert subprocess.run([sys.executable, "-c", probe], check=False).returncode == 0, (
        "importing the CLI pulled in fastmcp — the import in mcp/cmds.py must stay lazy"
    )
