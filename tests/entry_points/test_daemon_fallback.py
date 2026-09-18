"""A daemon that will not start is a slower command, not a failed one.

Guards issue-c4c6349e06d4. The client spawned the daemon on first dispatch and
had nowhere to fall back to, so inside a read-only agent sandbox every read
ended in a Python traceback — `spawn` cannot open the daemon log there, and
`socket_path` cannot even ask for a temporary directory, and neither failure is
a `DocirError` that `run_local` would have rendered. The same reads answered
normally under `--no-daemon`, which is the whole argument: the daemon keeps the
model warm and serializes writes, and decides nothing.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from docir.config.settings import Settings
from docir.entry_points.cli.app import app
from docir.entry_points.daemon import lifecycle, socket_executor
from docir.entry_points.daemon.socket_executor import start_daemon_executor
from docir.entry_points.mcp.cmds import _executor_for
from docir.platform.errors import DaemonError, SchemaError
from docir.platform.transport.messages import Request

runner = CliRunner()

WARNING = "the daemon could not be started"


@pytest.fixture
def daemon_wanted(monkeypatch, settings: Settings) -> Settings:
    """The default transport. The suite pins `--no-daemon`; this unpins it."""
    monkeypatch.delenv("DOCIR_NO_DAEMON", raising=False)
    return settings


def _spawn_cannot_touch_the_filesystem(monkeypatch) -> None:
    """The reported shape: the log file cannot be opened, so `spawn` raises."""

    def refuse(_settings: Settings) -> int:
        raise IsADirectoryError(21, "Is a directory", "daemon.log")

    monkeypatch.setattr(lifecycle, "spawn", refuse)


def _add() -> object:
    return runner.invoke(
        app,
        ["add", "--type", "decision", "--title", "Written in process", "--description", "d"],
    )


def test_a_spawn_that_cannot_touch_the_filesystem_still_runs_the_command(
    monkeypatch, daemon_wanted: Settings
) -> None:
    _spawn_cannot_touch_the_filesystem(monkeypatch)

    result = _add()

    assert result.exit_code == 0, result.output
    written = json.loads(result.stdout)
    # Exit 0 is not the property; the write is. A fallback that returned an
    # empty response would pass on the exit code alone.
    assert written["title"] == "Written in process"
    read_back = runner.invoke(app, ["--no-daemon", "get", written["id"]])
    assert json.loads(read_back.stdout)["title"] == "Written in process"


def test_it_says_why_on_stderr_and_leaves_stdout_parseable(
    monkeypatch, daemon_wanted: Settings
) -> None:
    _spawn_cannot_touch_the_filesystem(monkeypatch)

    result = _add()

    # Stderr specifically: stdout carries the JSON an agent parses, and this is
    # the one notice that fires on a command the agent still expects to read.
    assert WARNING in result.stderr
    assert "Is a directory" in result.stderr, "the reason is what makes it actionable"
    assert "DOCIR_NO_DAEMON" in result.stderr, "and the way out of paying for it again"
    assert WARNING not in result.stdout
    json.loads(result.stdout)


def test_a_daemon_that_never_becomes_ready_falls_back_too(
    monkeypatch, daemon_wanted: Settings
) -> None:
    # The other half of "cannot be started": the process launches and never
    # answers. `ensure_running` raises `DaemonError` here rather than `OSError`,
    # and it used to be rendered as a clean message and a non-zero exit — better
    # than a traceback, and still a command the store could have served.
    monkeypatch.setattr(lifecycle, "spawn", lambda _settings: 4242)
    monkeypatch.setattr(lifecycle, "wait_until_ready", lambda *_a, **_k: False)

    result = runner.invoke(app, ["query", "--limit", "1"])

    assert result.exit_code == 0, result.output
    assert WARNING in result.stderr
    json.loads(result.stdout)


def test_a_daemon_that_starts_is_the_one_that_answers(
    monkeypatch, daemon_wanted: Settings, capsys
) -> None:
    """The fallback must not fire on the ordinary path, or nothing is warm."""
    monkeypatch.setattr(socket_executor, "ensure_running", lambda _settings: None)

    executor = start_daemon_executor(daemon_wanted)

    assert type(executor).__name__ == "SocketExecutor"
    assert WARNING not in capsys.readouterr().err


def test_it_catches_a_transport_failure_and_not_a_broken_store(
    monkeypatch, daemon_wanted: Settings
) -> None:
    """`DaemonError` and `OSError`, and nothing wider.

    A schema that will not load is raised while the container is built, and
    in-process would raise it again — so swallowing it here would dress a
    broken store up as a broken daemon and report the wrong one.
    """

    def broken_schema(_settings: Settings) -> None:
        raise SchemaError("docs-schema.yaml: unknown status 'whatever'")

    monkeypatch.setattr(socket_executor, "ensure_running", broken_schema)

    with pytest.raises(SchemaError):
        start_daemon_executor(daemon_wanted)


def test_a_daemon_error_is_caught(monkeypatch, daemon_wanted: Settings) -> None:
    """The typed half of the pair, at the seam rather than through the CLI."""

    def not_ready(_settings: Settings) -> None:
        raise DaemonError("the daemon did not come up in 10.0s")

    monkeypatch.setattr(socket_executor, "ensure_running", not_ready)

    assert start_daemon_executor(daemon_wanted) is None


def test_the_mcp_server_falls_back_the_same_way(monkeypatch, daemon_wanted: Settings) -> None:
    """The second transport, which is the one most likely to meet this.

    An MCP client spawns the server into its own environment, so the read-only
    sandbox that denies the socket is that environment. It built its own
    `SocketExecutor` beside the CLI's, and a CLI-only fix would have left the
    crash exactly where an adopter meets it (adr-354a4270ecd8).
    """
    _spawn_cannot_touch_the_filesystem(monkeypatch)
    wanting_a_daemon = Settings.resolve(home=daemon_wanted.home, use_daemon=True)

    executor = _executor_for(wanting_a_daemon)

    assert type(executor).__name__ != "SocketExecutor"
    # And it answers, which is the property — an in-process executor that could
    # not dispatch would satisfy the type assertion above.
    response = executor.execute(Request(command="query", payload={"limit": 1}))
    assert response.ok, response.error
