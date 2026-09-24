"""`docir self upgrade` when the installer exits 0 and nothing moves.

This is the path that shipped broken and had no test, for a reason worth
recording: it ends in `os.execv`, so a test that let it run would replace the
pytest process. The seam is `_restart_as_the_new_build`, stubbed here — which
also lets each case assert *whether the hand-off happened at all*, and that is
half the behaviour.

The defect: `uv tool install docir==0.28.0` records an exact pin, `uv tool
upgrade docir` then resolves within it, prints `Nothing to upgrade` plus a hint
naming the command that clears it, and exits 0. docir read the exit code as
success, re-executed into the same build, and reported `already the newest
build` — while `docir self status` on the same install said a newer release was
available. The installer's hint was captured and thrown away.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
from typer.testing import CliRunner

from docir import __version__
from docir.config.settings import Settings
from docir.entry_points.cli.app import app
from docir.modules.release.application.ports import ProcessRunner, VersionProbe
from docir.modules.release.domain.installation import Evidence

runner = CliRunner()

#: What `uv tool upgrade docir` really prints on a receipt pinned to an exact
#: version, measured against uv on 2026-09-24. Quoted rather than paraphrased:
#: the whole repair is that docir relays this instead of swallowing it.
UV_PINNED_OUTPUT = (
    "Nothing to upgrade\n"
    "\n"
    "hint: `docir` is pinned to `0.28.0` (installed with an exact version pin); "
    "reinstall with `uv tool install docir@latest` to upgrade to a new version."
)


class _Installer(ProcessRunner):
    """An installer that exits 0 and says what uv says."""

    def __init__(self, status: int = 0, output: str = UV_PINNED_OUTPUT) -> None:
        self.commands: list[tuple[str, ...]] = []
        self._status, self._output = status, output

    def run(self, command: Sequence[str]) -> tuple[int, str]:
        self.commands.append(tuple(command))
        return self._status, self._output


class _Holds(VersionProbe):
    def __init__(self, version: str | None) -> None:
        self._version = version

    def installed_version(self) -> str | None:
        return self._version


@pytest.fixture
def upgrade(monkeypatch, settings: Settings):
    """Drive `self upgrade`'s package step with the installer and probe pinned."""

    def _run(*, installer: _Installer, holds: str | None, latest: str | None = "99.0.0"):
        evidence = Evidence(
            prefix=Path("/nonexistent/env"),
            executable=Path("/nonexistent/env/bin/python"),
            has_uv_receipt=True,
            has_pipx_metadata=False,
            direct_url=None,
            editable=False,
            ephemeral=False,
        )
        monkeypatch.setattr("docir.modules.release.api.gather_evidence", lambda: evidence)
        monkeypatch.setattr(
            "docir.modules.release.api.SubprocessRunner", lambda: installer, raising=True
        )
        monkeypatch.setattr(
            "docir.modules.release.api.SubprocessVersionProbe",
            lambda: _Holds(holds),
            raising=True,
        )

        class _Index:
            def latest_version(self, package: str) -> str | None:
                return latest

        monkeypatch.setattr("docir.modules.release.api.PyPIReleaseIndex", lambda: _Index())

        restarted: list[bool] = []
        monkeypatch.setattr(
            "docir.entry_points.cli.self_cmds._restart_as_the_new_build",
            lambda: restarted.append(True),
        )
        result = runner.invoke(app, ["--no-daemon", "self", "upgrade"])
        return result, restarted

    return _run


class TestAnInstallerThatChangedNothing:
    def test_it_says_the_version_did_not_move(self, upgrade) -> None:
        result, _ = upgrade(installer=_Installer(), holds=__version__)
        assert result.exit_code == 0, result.output
        assert f"the installer ran and docir is still {__version__}" in result.stderr

    def test_it_names_the_release_being_missed(self, upgrade) -> None:
        result, _ = upgrade(installer=_Installer(), holds=__version__, latest="99.0.0")
        assert "99.0.0 is published" in result.stderr

    def test_it_relays_what_the_installer_said(self, upgrade) -> None:
        # The whole repair. uv names the cause *and* the command that clears it;
        # docir used to capture both and print neither.
        result, _ = upgrade(installer=_Installer(), holds=__version__)
        assert "Nothing to upgrade" in result.stderr
        assert "uv tool install docir@latest" in result.stderr

    def test_it_gives_an_instruction_that_holds_when_the_installer_said_nothing(
        self, upgrade
    ) -> None:
        # A pip held back by a constraint file exits 0 and explains nothing —
        # measured. Without this line that reader is left with a fact and no move.
        result, _ = upgrade(installer=_Installer(output=""), holds=__version__)
        assert "docir self status" in result.stderr
        assert "self upgrade --no-package" in result.stderr

    def test_it_does_not_hand_off_to_a_build_that_is_the_same_build(self, upgrade) -> None:
        _result, restarted = upgrade(installer=_Installer(), holds=__version__)
        assert restarted == []

    def test_the_store_is_still_resynced(self, upgrade) -> None:
        # Not a failure: the package half did nothing, and the half that always
        # applies is the one that brings this store to the running build.
        result, _ = upgrade(installer=_Installer(), holds=__version__)
        assert result.exit_code == 0
        assert "check" in result.output or "no structural issues" in result.output


class TestAnInstallerThatWorked:
    def test_it_hands_off_to_the_new_build(self, upgrade) -> None:
        _result, restarted = upgrade(installer=_Installer(), holds="99.0.0")
        assert restarted == [True]

    def test_it_says_nothing_about_a_stall(self, upgrade) -> None:
        result, _ = upgrade(installer=_Installer(), holds="99.0.0")
        assert "did not move" not in result.stderr
        # And it does not dump the installer's output on the happy path: a
        # working `pip install --upgrade` prints dozens of lines.
        assert "Nothing to upgrade" not in result.stderr


class TestWhenTheProbeCannotTell:
    def test_it_falls_through_to_the_behaviour_it_had_before(self, upgrade) -> None:
        # `None` is *unknown*, never "it moved" and never "it stalled". The
        # conservative branch is the old one: hand off, as every release before
        # this one did.
        _result, restarted = upgrade(installer=_Installer(), holds=None)
        assert restarted == [True]
