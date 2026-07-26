"""End-to-end tests driving the real Typer CLI in-process.

Uses Typer's synchronous CliRunner. The ``settings`` fixture points DOCIR_HOME
at a temp dir and forces in-process execution, so these exercise the full
presentation -> application -> infrastructure stack via the command line.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from docir import __version__
from docir.config.settings import Settings
from docir.entry_points.cli.app import app

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
        # Assert against the package's own version, not a literal: a hardcoded
        # one silently passed while __version__ drifted from pyproject (0.1.1
        # shipped reporting 0.1.0).
        result = run("version")
        assert result.exit_code == 0
        assert __version__ in result.stdout

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

        # A document with no relations is an `orphan` — the default state of a
        # newly created one. It must NOT fail the build: gating on it made the
        # advertised CI gate red on a healthy corpus (this test previously
        # asserted the opposite, which is the behaviour GAP-006 reported).
        run("add", "--type", "decision", "--title", "Orphan", "--description", "d")
        assert run("check").exit_code == 0
        assert run("check", "--strict").exit_code == 0
        # ...but --strict-all still treats every finding as fatal.
        assert run("check", "--strict-all").exit_code == 1

    def test_check_strict_fails_on_a_broken_graph(self) -> None:
        # `dangling` is real damage — an edge resolving to nothing — so it is
        # exactly what the merge gate exists to catch.
        run("add", "--type", "decision", "--title", "Target", "--description", "d")
        run(
            "add",
            "--type",
            "decision",
            "--title",
            "Source",
            "--description",
            "d",
            "--related",
            "adr-0001",
        )
        assert run("delete", "adr-0001", "--force").exit_code == 0
        assert run("check", "--strict").exit_code == 1

    def test_findings_carry_a_severity(self) -> None:
        run("add", "--type", "decision", "--title", "Orphan", "--description", "d")
        findings = json.loads(run("check").stdout)
        assert {f["kind"]: f["severity"] for f in findings} == {"orphan": "warning"}


class TestOutputModes:
    """Token-aware output: JSON when captured (non-TTY), tables under --pretty."""

    def test_captured_output_defaults_to_compact_json(self) -> None:
        # CliRunner captures stdout (not a TTY) — an agent gets compact JSON free.
        _seed_tag()
        run("add", "--type", "decision", "--title", "J", "--description", "d", "--tags", "auth")
        out = run("query", "--type", "decision").stdout.strip()
        assert out.startswith("[")  # JSON array, not a Rich table
        assert "\n" not in out  # single line = compact
        assert "┏" not in out and "─" not in out
        assert json.loads(out)[0]["id"] == "adr-0001"

    def test_pretty_forces_tables_even_when_piped(self) -> None:
        _seed_tag()
        run("add", "--type", "decision", "--title", "J", "--description", "d", "--tags", "auth")
        assert "adr-0001" in run("--pretty", "get", "adr-0001").stdout  # render_document
        listed = run("--pretty", "query", "--type", "decision").stdout  # render_document_list
        assert "adr-0001" in listed and ("─" in listed or "┃" in listed)
        assert "auth" in run("--pretty", "tag", "list").stdout  # render_tags
        assert run("--pretty", "check").exit_code == 0  # render_findings
        assert run("--pretty", "lint", "--deep").exit_code == 0  # render_findings (advisory)
        assert run("--pretty", "reindex").exit_code == 0  # render_message path

    def test_trim_drops_empty_fields_by_default(self) -> None:
        run("add", "--type", "decision", "--title", "J", "--description", "d")
        assert '"owner"' not in run("get", "adr-0001").stdout  # empty owner omitted
        assert '"related"' not in run("get", "adr-0001").stdout  # empty list omitted

    def test_no_trim_keeps_empty_fields(self) -> None:
        run("add", "--type", "decision", "--title", "J", "--description", "d")
        full = run("--no-trim", "get", "adr-0001").stdout
        assert '"owner"' in full and '"related"' in full


class TestErrorHandling:
    def test_missing_document_exit_code(self) -> None:
        result = run("get", "adr-9999")
        assert result.exit_code == 4

    def test_daemon_status_not_running(self) -> None:
        result = run("daemon", "status")
        assert result.exit_code == 0
        assert "not running" in result.stdout.lower()
