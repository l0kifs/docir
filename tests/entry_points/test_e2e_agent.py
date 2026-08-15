"""End-to-end tests for ``docir agent install/update`` through the real CLI.

These drive the Typer app in-process. The commands do not go through the
daemon/dispatcher (adr-3a2d5ee7bc84), so they need no index; they write instruction
files into the tmp project directory passed as the argument.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from docir.config.settings import Settings
from docir.entry_points.cli.app import app

runner = CliRunner()


def run(*args: str):
    return runner.invoke(app, list(args))


@pytest.fixture(autouse=True)
def _env(settings: Settings) -> Settings:
    return settings


def _skill(root: Path) -> Path:
    return root / ".claude" / "skills" / "docir" / "SKILL.md"


def _writing(root: Path) -> Path:
    return root / ".claude" / "skills" / "docir-writing" / "SKILL.md"


class TestAgentInstall:
    def test_install_writes_claude_skill(self, tmp_path: Path) -> None:
        result = run("agent", "install", str(tmp_path))
        assert result.exit_code == 0
        skill = _skill(tmp_path)
        assert skill.exists()
        text = skill.read_text(encoding="utf-8")
        assert text.startswith("---\nname: docir")
        assert "docir:v" in text

    def test_install_agents_preserves_existing_file(self, tmp_path: Path) -> None:
        agents = tmp_path / "AGENTS.md"
        agents.write_text("# House rules\n\nkeep me\n", encoding="utf-8")
        result = run("agent", "install", str(tmp_path), "--agent", "agents")
        assert result.exit_code == 0
        text = agents.read_text(encoding="utf-8")
        assert text.startswith("# House rules")
        assert text.count("<!-- docir:start -->") == 1

    def test_agents_block_links_a_skill_that_is_really_there(self, tmp_path: Path) -> None:
        # The end-to-end claim of adr-6ed847e02fe5: AGENTS.md is a short index,
        # and the path it prints resolves in the repo it was written into.
        assert run("agent", "install", str(tmp_path), "--agent", "agents").exit_code == 0
        text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
        assert f"({_skill(tmp_path).relative_to(tmp_path).as_posix()})" in text
        assert _skill(tmp_path).exists()
        assert len(text.splitlines()) < 15
        # The packaged guide's own headings are in the skill, not in the block.
        assert "## Core loop" in _skill(tmp_path).read_text(encoding="utf-8")
        assert "## Core loop" not in text

    def test_global_agents_errors(self, tmp_path: Path) -> None:
        # Errors before any write, so it never touches the real home directory.
        result = run("agent", "install", str(tmp_path), "--global", "--agent", "agents")
        assert result.exit_code == 2

    def test_install_is_idempotent(self, tmp_path: Path) -> None:
        assert run("agent", "install", str(tmp_path)).exit_code == 0
        assert run("agent", "install", str(tmp_path)).exit_code == 0
        # A second AGENTS.md install must not duplicate the block.
        run("agent", "install", str(tmp_path), "--agent", "agents")
        run("agent", "install", str(tmp_path), "--agent", "agents")
        text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
        assert text.count("<!-- docir:start -->") == 1

    def test_the_writing_skill_installs_only_when_asked(self, tmp_path: Path) -> None:
        assert run("agent", "install", str(tmp_path)).exit_code == 0
        assert not _writing(tmp_path).exists()
        assert run("agent", "install", str(tmp_path), "--agent", "claude-writing").exit_code == 0
        text = _writing(tmp_path).read_text(encoding="utf-8")
        assert text.startswith("---\nname: docir-writing")
        assert "docir:v" in text
        # Its own subject, and a separate skill directory from the CLI guide.
        assert "# docir — Writing Rules" in text
        assert "# docir — Writing Rules" not in _skill(tmp_path).read_text(encoding="utf-8")

    def test_the_writing_skill_alone_does_not_pull_in_the_cli_guide(self, tmp_path: Path) -> None:
        # They are independent skills; only the AGENTS.md index requires one.
        assert run("agent", "install", str(tmp_path), "--agent", "claude-writing").exit_code == 0
        assert _writing(tmp_path).exists()
        assert not _skill(tmp_path).exists()

    def test_update_refreshes_both_skills_once_both_are_installed(self, tmp_path: Path) -> None:
        run("agent", "install", str(tmp_path), "--agent", "claude", "--agent", "claude-writing")
        result = run("agent", "update", str(tmp_path))
        assert result.exit_code == 0
        assert _skill(tmp_path).exists() and _writing(tmp_path).exists()
        assert result.stdout.count("updated") == 2

    def test_json_output(self, tmp_path: Path) -> None:
        result = run("--json", "agent", "install", str(tmp_path))
        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload[0]["target"] == "claude"
        assert payload[0]["action"] == "created"

    def test_pretty_output(self, tmp_path: Path) -> None:
        # --pretty exercises the human render_setup path (not the JSON default).
        result = run("--pretty", "agent", "install", str(tmp_path))
        assert result.exit_code == 0
        assert "created" in result.stdout


class TestAgentUpdate:
    def test_update_refreshes_installed_files(self, tmp_path: Path) -> None:
        assert run("agent", "install", str(tmp_path)).exit_code == 0
        result = run("agent", "update", str(tmp_path))
        assert result.exit_code == 0
        assert "updated" in result.stdout

    def test_update_with_nothing_installed_is_ok(self, tmp_path: Path) -> None:
        result = run("agent", "update", str(tmp_path))
        assert result.exit_code == 0
