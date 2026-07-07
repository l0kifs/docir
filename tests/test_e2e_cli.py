"""End-to-end tests driving the real Typer CLI in-process.

Uses Typer's synchronous CliRunner. The ``settings`` fixture points DOCIR_HOME
at a temp dir and forces in-process execution, so these exercise the full
presentation -> application -> infrastructure stack via the command line.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from docir.infrastructure.config.settings import Settings
from docir.presentation.cli.app import app

runner = CliRunner()


def run(*args: str, **kwargs: object):
    return runner.invoke(app, list(args), **kwargs)


@pytest.fixture(autouse=True)
def _env(settings: Settings) -> Settings:
    return settings


def _seed_tag() -> None:
    assert run("tag", "add", "auth", "--description", "Auth.").exit_code == 0


class TestBasicWorkflow:
    def test_version(self) -> None:
        result = run("version")
        assert result.exit_code == 0
        assert "0.1.0" in result.stdout

    def test_add_get_query(self) -> None:
        _seed_tag()
        added = run(
            "add",
            "--type",
            "decision",
            "--title",
            "Auth strategy",
            "--description",
            "How auth works",
            "--tags",
            "auth",
            "--body",
            "JWT tokens",
        )
        assert added.exit_code == 0
        assert "adr-0001" in added.stdout

        got = run("get", "adr-0001")
        assert got.exit_code == 0
        assert "Auth strategy" in got.stdout

        listed = run("query", "--type", "decision")
        assert listed.exit_code == 0
        assert "adr-0001" in listed.stdout

    def test_search_and_context(self) -> None:
        _seed_tag()
        run(
            "add",
            "--type",
            "decision",
            "--title",
            "Auth",
            "--description",
            "authentication and tokens",
            "--body",
            "refresh tokens",
        )
        assert "adr-0001" in run("search", "auth").stdout
        assert run("context", "auth work", "--limit", "3").exit_code == 0

    def test_update_append_section(self) -> None:
        run("add", "--type", "issue", "--title", "Bug", "--description", "a bug")
        result = run("update", "issue-0001", "--append-section", "Resolution", "--body", "Fixed")
        assert result.exit_code == 0
        assert "Resolution" in run("get", "issue-0001").stdout

    def test_archive_unarchive_delete(self) -> None:
        run("add", "--type", "decision", "--title", "Temp", "--description", "d")
        assert run("archive", "adr-0001").exit_code == 0
        assert run("unarchive", "adr-0001").exit_code == 0
        assert run("delete", "adr-0001").exit_code == 0


class TestBodyInput:
    def test_body_file(self, tmp_path) -> None:
        body = tmp_path / "b.md"
        body.write_text("from file", encoding="utf-8")
        result = run(
            "add",
            "--type",
            "decision",
            "--title",
            "F",
            "--description",
            "d",
            "--body-file",
            str(body),
        )
        assert result.exit_code == 0
        assert "from file" in run("get", "adr-0001").stdout

    def test_stdin(self) -> None:
        result = run(
            "add",
            "--type",
            "decision",
            "--title",
            "S",
            "--description",
            "d",
            "--stdin",
            input="from stdin\n",
        )
        assert result.exit_code == 0
        assert "from stdin" in run("get", "adr-0001").stdout

    def test_conflicting_body_sources(self) -> None:
        result = run(
            "add",
            "--type",
            "decision",
            "--title",
            "X",
            "--description",
            "d",
            "--body",
            "a",
            "--stdin",
        )
        assert result.exit_code != 0


class TestJsonOutput:
    def test_json_document(self) -> None:
        run("add", "--type", "decision", "--title", "J", "--description", "d")
        result = run("--json", "get", "adr-0001")
        assert result.exit_code == 0
        assert '"id"' in result.stdout and "adr-0001" in result.stdout

    def test_json_list_and_tags(self) -> None:
        _seed_tag()
        assert '"key"' in run("--json", "tag", "list").stdout
        assert run("--json", "query").exit_code == 0


class TestMaintenanceCommands:
    def test_check_and_lint(self) -> None:
        run("add", "--type", "decision", "--title", "Orphan", "--description", "d")
        assert "orphan" in run("check").stdout.lower()
        assert run("lint").exit_code == 0  # no --deep: hint
        assert run("lint", "--deep").exit_code == 0
        assert run("--json", "check").exit_code == 0

    def test_embed_and_reindex(self) -> None:
        run("add", "--type", "decision", "--title", "A", "--description", "d")
        assert run("embed").exit_code == 0  # no --flush: hint
        assert run("embed", "--flush").exit_code == 0
        assert run("reindex").exit_code == 0

    def test_tag_rename_and_rm(self) -> None:
        _seed_tag()
        assert run("tag", "rename", "auth", "authn").exit_code == 0
        assert run("tag", "rm", "authn").exit_code == 0

    def test_check_strict_gates_ci(self) -> None:
        # Clean repo: --strict passes.
        assert run("check", "--strict").exit_code == 0
        # An orphan doc is a Tier 1 issue: --strict now fails (blocks a merge).
        run("add", "--type", "decision", "--title", "Orphan", "--description", "d")
        assert run("check").exit_code == 0
        assert run("check", "--strict").exit_code == 1


class TestErrorHandling:
    def test_missing_document_exit_code(self) -> None:
        result = run("get", "adr-9999")
        assert result.exit_code == 4

    def test_daemon_status_not_running(self) -> None:
        result = run("daemon", "status")
        assert result.exit_code == 0
        assert "not running" in result.stdout.lower()
