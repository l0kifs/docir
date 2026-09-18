"""Where a socket cannot exist, the two reporting commands must still report.

Guards issue-b9800d8265f6. `Settings.socket_path` asks `tempfile` for somewhere
to put the socket and raises where there is nowhere — a read-only sandbox, which
is exactly the environment the in-process fallback exists for. Every command that
*dispatches* survives that (issue-c4c6349e06d4); `docir doctor` and `docir daemon
status` read the path directly to report it, and so still ended in a traceback —
on the two commands somebody runs to diagnose the first failure.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from docir.config.settings import Settings
from docir.entry_points.cli.app import app
from docir.entry_points.daemon import lifecycle
from docir.platform.errors import DaemonError

runner = CliRunner()


@pytest.fixture
def nowhere_to_listen(monkeypatch, settings: Settings) -> Settings:
    """The platform offering no temporary directory, which is how it fails."""

    def refuse(self: Settings) -> object:
        raise FileNotFoundError("No usable temporary directory found in []")

    monkeypatch.setattr(type(settings), "socket_path", property(refuse))
    return settings


def test_the_path_reads_as_absent_rather_than_raising(nowhere_to_listen: Settings) -> None:
    assert lifecycle.socket_path(nowhere_to_listen) is None


def test_no_daemon_is_running_and_stopping_one_is_not_an_error(
    nowhere_to_listen: Settings,
) -> None:
    # `stop` still clears the pid file; only the unlink has nothing to do.
    assert lifecycle.is_running(nowhere_to_listen) is False
    assert lifecycle.stop(nowhere_to_listen) is False


def test_status_reports_the_absence_instead_of_raising(nowhere_to_listen: Settings) -> None:
    snapshot = lifecycle.status(nowhere_to_listen)

    assert snapshot.socket_path is None
    assert snapshot.running is False


def test_daemon_status_says_it_cannot_run_here_not_that_it_is_stopped(
    nowhere_to_listen: Settings,
) -> None:
    # "not running" reads as "start it", and nothing in this environment can.
    result = runner.invoke(app, ["daemon", "status"])

    assert result.exit_code == 0, result.output
    assert "cannot run here" in result.output
    assert "not running" not in result.output


def test_doctor_reports_it_as_a_warning_and_strict_still_passes(
    nowhere_to_listen: Settings,
) -> None:
    # `--no-trim` because an absent socket *is* the empty value the trim drops,
    # and the property is that the field reads as absent rather than crashing.
    result = runner.invoke(app, ["--no-daemon", "--no-trim", "doctor", "--strict"])

    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    finding = next(f for f in report["findings"] if f["kind"] == "no-daemon-socket")
    # A warning, because every command still answers in process. An error here
    # would fail `--strict` on a setup that works, only slowly.
    assert finding["severity"] == "warning"
    assert "TMPDIR" in finding["fix"]
    assert report["daemon"]["socket"] is None


def test_ensure_running_says_why_rather_than_raising_an_untyped_oserror(
    nowhere_to_listen: Settings,
) -> None:
    # The caller turns this into the one-line "running in process" warning, so
    # the message is what the user reads as the reason.
    with pytest.raises(DaemonError, match="nowhere to listen"):
        lifecycle.ensure_running(nowhere_to_listen)


def test_serving_refuses_because_a_server_has_nowhere_to_bind(
    nowhere_to_listen: Settings,
) -> None:
    """The one caller that must not degrade.

    A client without a socket runs in process; a server without one is not a
    daemon at all, so it says so rather than inventing a path.
    """
    result = runner.invoke(app, ["daemon", "serve"])

    assert result.exit_code != 0
    assert "nowhere to listen" in result.output
