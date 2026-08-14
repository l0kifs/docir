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
    _ENV["settings"] = settings
    return settings


#: The autouse fixture's settings, so module-level helpers can reach the store.
_ENV: dict[str, Settings] = {}


def _seed_tag() -> None:
    assert run("tag", "add", "auth", "--description", "Auth.").exit_code == 0


def _break_graph(doc_id: str) -> None:
    """Leave an edge pointing at a document no file provides, then reindex.

    Simulates the merge that actually produces a dangling reference: one branch
    deleted the document, another linked to it. These tests used `delete
    --force` to get here, which no longer works — that command now strips the
    edges it would break (issue-fd547a293d01), so the only route to a dangling edge is from
    outside the CLI.
    """
    removed = list(_ENV["settings"].docs_root.rglob(f"{doc_id}-*.md"))
    for path in removed:
        path.unlink()
    # Assert the removal actually happened. With no file to delete the reindex
    # is clean and `check` finds nothing, so the caller's assertion fails one
    # line later claiming the strict gate is broken — which is what a setup that
    # silently did nothing looks like from the outside.
    assert len(removed) == 1, f"expected one file for {doc_id}, removed {len(removed)}"
    assert run("reindex").exit_code == 0


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
        # asserted the opposite, which is the behaviour issue-9cb85759076d reported).
        run("add", "--type", "decision", "--title", "Orphan", "--description", "d")
        assert run("check").exit_code == 0
        assert run("check", "--strict").exit_code == 0
        # ...but --strict-all still treats every finding as fatal.
        assert run("check", "--strict-all").exit_code == 1

    def test_check_strict_fails_on_a_broken_graph(self) -> None:
        # `dangling` is real damage — an edge resolving to nothing — so it is
        # exactly what the merge gate exists to catch.
        #
        # Both writes are asserted, and the id this test hardcodes is asserted
        # with them: a silent failure in either leaves nothing to dangle, and
        # the test then fails on the last line as though `--strict` had stopped
        # gating. That is how one unexplained failure here read (2026-08-14),
        # and the setup gave nothing to distinguish the two.
        target = run("add", "--type", "decision", "--title", "Target", "--description", "d")
        assert target.exit_code == 0, target.stdout
        assert "adr-0001" in target.stdout
        source = run(
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
        assert source.exit_code == 0, source.stdout
        _break_graph("adr-0001")
        assert run("check", "--strict").exit_code == 1

    def test_check_fix_repairs_and_reports_in_both_output_modes(self) -> None:
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
        _break_graph("adr-0001")

        # The table path is asserted alongside the JSON one on purpose: `asdict`
        # keeps a dataclass's tuple fields as tuples, and a renderer that accepts
        # only `list` showed "nothing to repair" while --json printed the fix.
        pretty = run("--pretty", "check", "--fix")
        assert pretty.exit_code == 0
        assert "dangling" in pretty.stdout and "fixed" in pretty.stdout

        run(
            "add",
            "--type",
            "decision",
            "--title",
            "Second",
            "--description",
            "d",
            "--related",
            "adr-0002",
        )
        _break_graph("adr-0002")
        payload = json.loads(run("--json", "check", "--fix").stdout)
        assert [a["kind"] for a in payload["actions"]] == ["dangling"]

    def test_check_fix_then_strict_passes(self) -> None:
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
        _break_graph("adr-0001")
        assert run("check", "--strict").exit_code == 1
        assert run("check", "--fix", "--strict").exit_code == 0

    def test_findings_carry_a_severity(self) -> None:
        run("add", "--type", "decision", "--title", "Orphan", "--description", "d")
        findings = json.loads(run("check").stdout)
        assert {f["kind"]: f["severity"] for f in findings} == {"orphan": "warning"}


class TestIncludeInactiveFlag:
    """`--include-inactive` replaces `--include-resolved` (guards issue-efc29234eb57).

    The flag controlled the schema's `inactive_statuses` — `rejected`/
    `superseded` for a decision, `deprecated` for architecture, `retired` for a
    policy — but was named after `resolved`, a status only two of the fifteen
    shipped types have. Someone querying decisions had no reason to guess that
    a flag named --include-resolved surfaces superseded ones. The wire field was
    already `include_inactive`; only the CLI spelling was wrong.
    """

    @staticmethod
    def _superseded_decision() -> None:
        run("add", "--type", "decision", "--title", "Old", "--description", "d")
        run("update", "adr-0001", "--status", "accepted")
        run("update", "adr-0001", "--status", "superseded")

    def test_inactive_documents_are_hidden_by_default(self) -> None:
        self._superseded_decision()
        assert json.loads(run("query").stdout) == []

    def test_include_inactive_reveals_them(self) -> None:
        self._superseded_decision()
        assert [d["id"] for d in json.loads(run("query", "--include-inactive").stdout)] == [
            "adr-0001"
        ]

    def test_the_old_spelling_still_works(self) -> None:
        # It ships in scripts and in agent instructions installed before the
        # rename; breaking it would be a silent behaviour change for them.
        self._superseded_decision()
        result = run("query", "--include-resolved")
        assert [d["id"] for d in json.loads(result.stdout)] == ["adr-0001"]


class TestBrokenSchemaIsReportedNotRaised:
    """An invalid schema reaches the caller as a domain error, not a traceback.

    `execute` built the executor outside the error mapping, and building it
    loads the schema — so an invalid `docs-schema.yaml` escaped as an unhandled
    SchemaError: a raw Python traceback and exit 1, while `docir schema
    validate` reported the same error on the same file cleanly with exit 3.

    Latent before status names were validated (only malformed YAML could trip
    it); routine after, since any typo in a status name now raises here.
    """

    @staticmethod
    def _break_schema(settings: Settings) -> None:
        settings.schema_path.parent.mkdir(parents=True, exist_ok=True)
        settings.schema_path.write_text(
            "types:\n"
            "  ticket:\n"
            "    prefix: tkt\n"
            "    default_status: open\n"
            "    statuses:\n"
            "      open: [closd]\n"
            "      closed: []\n",
            encoding="utf-8",
        )

    @pytest.mark.parametrize("argv", [["query"], ["check"], ["search", "x"], ["context", "x"]])
    def test_domain_error_and_exit_code(self, settings: Settings, argv: list[str]) -> None:
        self._break_schema(settings)
        result = run(*argv)
        assert result.exit_code == 3  # SchemaError.exit_code, not 1
        assert result.exception is None or isinstance(result.exception, SystemExit)

    def test_schema_validate_agrees(self, settings: Settings) -> None:
        # The command that always reported this correctly — the others now match.
        self._break_schema(settings)
        assert run("schema", "validate").exit_code == 3

    def test_yaml_syntax_errors_are_domain_errors_too(self, settings: Settings) -> None:
        # A bad indent raises yaml.ParserError, which is NOT a DocirError, so it
        # slipped past the mapping that catches every semantic schema error —
        # on the one file the docs tell you to edit by hand.
        settings.schema_path.parent.mkdir(parents=True, exist_ok=True)
        settings.schema_path.write_text("profiles: [software]\n  bad indent\n", encoding="utf-8")
        assert run("query").exit_code == 3

    def test_a_malformed_tag_registry_is_a_domain_error(self, settings: Settings) -> None:
        settings.tags_path.parent.mkdir(parents=True, exist_ok=True)
        settings.tags_path.write_text("auth: Auth.\n- not a mapping\n", encoding="utf-8")
        assert run("reindex").exit_code == 3


class TestWriteOutputNamesTheStore:
    """Every write says which store it landed in (guards issue-34b4f0ca1e13).

    `path` is relative to the store, so it read as repo-relative regardless of
    where the store actually was. Naming the store removes the ambiguity for
    every write, warning or not.
    """

    def test_add_reports_the_store(self, settings: Settings) -> None:
        payload = json.loads(
            run("add", "--type", "decision", "--title", "T", "--description", "d").stdout
        )
        assert payload["store"] == str(settings.home)

    def test_update_reports_the_store(self, settings: Settings) -> None:
        run("add", "--type", "decision", "--title", "T", "--description", "d")
        payload = json.loads(run("update", "adr-0001", "--set-title", "U").stdout)
        assert payload["store"] == str(settings.home)


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

    def test_tag_list_json_carries_usage_including_a_zero(self) -> None:
        # The agent path: trimming drops empty fields, and a dead tag's `usage`
        # of 0 is the one number this feature exists to report.
        _seed_tag()
        run("tag", "add", "dead", "--description", "Nobody uses this.")
        run("add", "--type", "decision", "--title", "J", "--description", "d", "--tags", "auth")
        usage = {t["key"]: t["usage"] for t in json.loads(run("tag", "list").stdout)}
        assert usage == {"auth": 1, "dead": 0}

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


class TestTheOptionalSchemaDriftNotice:
    """`DOCIR_SCHEMA_NOTICE=1` prints drift on stderr after every command.

    Off by default: `docir check` already reports the same change as a finding,
    and a notice on every command repeats until someone reindexes, which is how
    a warning stops being read. It exists for the case the finding cannot cover
    — a change nobody will run `check` to discover.
    """

    @staticmethod
    def _drift(settings: Settings) -> None:
        assert run("add", "--type", "decision", "--title", "A", "--description", "d").exit_code == 0
        assert run("reindex").exit_code == 0
        settings.schema_path.write_text(
            "types:\n"
            "  decision:\n"
            "    prefix: dec\n"
            "    default_status: proposed\n"
            "    statuses:\n"
            "      proposed: [accepted]\n"
            "      accepted: []\n",
            encoding="utf-8",
        )

    def test_it_is_silent_by_default(self, settings: Settings) -> None:
        self._drift(settings)
        result = run("query")
        assert result.exit_code == 0
        assert "prefix" not in (result.stderr or "")

    def test_it_reports_on_an_unrelated_command_when_enabled(
        self, settings: Settings, monkeypatch
    ) -> None:
        self._drift(settings)
        monkeypatch.setenv("DOCIR_SCHEMA_NOTICE", "1")
        _ENV["settings"] = Settings.resolve()
        result = run("query")
        assert result.exit_code == 0
        assert "prefix 'adr' -> 'dec'" in result.stderr

    def test_the_command_still_succeeds_and_its_stdout_stays_clean(
        self, settings: Settings, monkeypatch
    ) -> None:
        # The notice is about something *else* being wrong; it must not corrupt
        # the JSON an agent parses, nor change the exit code.
        self._drift(settings)
        monkeypatch.setenv("DOCIR_SCHEMA_NOTICE", "1")
        _ENV["settings"] = Settings.resolve()
        result = run("query")
        assert result.exit_code == 0
        assert isinstance(json.loads(result.stdout), list)
