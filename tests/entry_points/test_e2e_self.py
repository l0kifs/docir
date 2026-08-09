"""`docir self upgrade` end to end — the three post-upgrade steps as one command.

The steps themselves are covered where they live (reindex and check in the
maintenance integration tests, the stamp in the agent tests). What is only true
here is the *sequence*: one invocation rebuilds the index, refreshes the
generated instruction files, and reports what is left — in that order, so the
findings describe the state the user is left in rather than the one they
started from.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from typer.testing import CliRunner

from docir import __version__
from docir.config.settings import Settings
from docir.entry_points.cli.app import app
from docir.platform.persistence.unit_of_work import UnitOfWork

runner = CliRunner()


def _add() -> None:
    result = runner.invoke(
        app, ["--no-daemon", "add", "--type", "decision", "--title", "A", "--description", "d"]
    )
    assert result.exit_code == 0, result.output


def _upgrade(project_root: str):
    result = runner.invoke(app, ["--no-daemon", "self", "upgrade", project_root])
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def test_it_reindexes_checks_and_refreshes_in_one_command(settings: Settings, tmp_path) -> None:
    _add()
    report = _upgrade(str(tmp_path))

    assert report["version"] == __version__
    assert report["reindex"]["documents_indexed"] == 1
    # A single unlinked document, so `check` has something to say: the report
    # carries the findings rather than the command exiting on them.
    assert any(finding["kind"] == "orphan" for finding in report["findings"])


def test_it_clears_the_stale_build_finding(
    settings: Settings, tmp_path, uow_factory: Callable[[], UnitOfWork]
) -> None:
    """The point of the command: one invocation and `check` is quiet again."""
    _add()
    with uow_factory() as uow:
        uow.index_build.set("0.0.1")
        uow.commit()

    before = runner.invoke(app, ["--no-daemon", "check"])
    assert "stale-index-build" in before.stdout

    kinds = {finding["kind"] for finding in _upgrade(str(tmp_path)).get("findings", [])}
    assert "stale-index-build" not in kinds


def test_it_refreshes_an_installed_skill_and_leaves_an_absent_one_alone(
    settings: Settings, tmp_path
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    # Trimmed JSON drops empty fields, so "no files touched" is an absent key.
    assert not _upgrade(str(project)).get("agents"), "nothing installed, nothing to refresh"

    assert runner.invoke(app, ["--no-daemon", "agent", "install", str(project)]).exit_code == 0
    skill = project / ".claude" / "skills" / "docir" / "SKILL.md"
    skill.write_text(
        skill.read_text(encoding="utf-8").replace(f"docir:v{__version__}", "docir:v0.0.1"),
        encoding="utf-8",
    )

    agents = _upgrade(str(project))["agents"]
    assert [file["previous_version"] for file in agents] == ["0.0.1"]
    assert f"docir:v{__version__}" in skill.read_text(encoding="utf-8")
