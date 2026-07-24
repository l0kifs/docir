"""End-to-end tests for ``docir init`` and project-store discovery via the CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from docir.entry_points.cli.app import app

runner = CliRunner()


def run(*args: str):
    return runner.invoke(app, list(args))


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch) -> None:
    # Hermetic: in-process, no ambient home; init commands pass explicit dirs.
    monkeypatch.setenv("DOCIR_NO_DAEMON", "1")
    monkeypatch.delenv("DOCIR_HOME", raising=False)
    monkeypatch.delenv("DOCIR_EMBEDDER", raising=False)


class TestInit:
    def test_init_creates_project_store(self, tmp_path: Path) -> None:
        result = run("init", str(tmp_path))
        assert result.exit_code == 0
        assert (tmp_path / ".docir" / "docs-schema.yaml").exists()
        assert (tmp_path / ".docir" / ".gitignore").exists()

    def test_unknown_profile_exits_3(self, tmp_path: Path) -> None:
        assert run("init", str(tmp_path), "--profiles", "bogus").exit_code == 3

    def test_json_output(self, tmp_path: Path) -> None:
        result = run("--json", "init", str(tmp_path))
        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["schema_written"] is True
        assert payload["profiles"] == ["software"]

    def test_pretty_output(self, tmp_path: Path) -> None:
        # --pretty exercises the human render_init path (not the JSON default).
        result = run("--pretty", "init", str(tmp_path))
        assert result.exit_code == 0
        assert "initialized" in result.stdout.lower()


class TestDiscoveryThroughCli:
    def test_add_lands_in_the_discovered_store(self, tmp_path: Path, monkeypatch) -> None:
        proj = tmp_path / "proj"
        proj.mkdir()
        assert run("init", str(proj)).exit_code == 0

        # From a subdirectory of the project, commands must resolve to proj/.docir.
        src = proj / "src"
        src.mkdir()
        monkeypatch.chdir(src)
        assert run("tag", "add", "auth", "--description", "Auth.").exit_code == 0
        added = run(
            "add",
            "--type",
            "decision",
            "--title",
            "T",
            "--description",
            "d",
            "--tags",
            "auth",
            "--body",
            "x",
        )
        assert added.exit_code == 0
        assert "adr-0001" in added.stdout
        assert list((proj / ".docir" / "docs" / "decisions").glob("adr-0001-*.md"))
