"""End-to-end tests for the `max_body_chars` write ceiling.

The domain tests cover the rule; these cover the three things only the whole
stack can show — that a refusal reaches the process exit code as 9 and writes no
file, that `lint --deep` still reads the same key at Tier 2, and that the
mechanical rewrites (a tag rename, a forced delete's edge-strip, `check --fix`)
never reach the check at all.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from docir.config.settings import Settings
from docir.entry_points.cli.app import app

runner = CliRunner()

#: A ceiling small enough to cross with one sentence. `memo` declines to enforce
#: its own, so the two types differ in nothing else.
SCHEMA = """
profiles: [software]
types:
  note:
    prefix: nt
    default_status: active
    statuses:
      active: []
    max_body_chars: 50
  memo:
    prefix: mm
    default_status: active
    statuses:
      active: []
    max_body_chars: 50
    max_body_chars_enforce: false
"""


def run(*args: str):
    return runner.invoke(app, list(args))


@pytest.fixture(autouse=True)
def _store(settings: Settings) -> Settings:
    settings.ensure_directories()
    settings.schema_path.write_text(SCHEMA, encoding="utf-8")
    return settings


def _add(doc_type: str, title: str, body: str):
    return run("add", "--type", doc_type, "--title", title, "--description", "D", "--body", body)


def _add_ok(doc_type: str, title: str, body: str) -> str:
    result = _add(doc_type, title, body)
    assert result.exit_code == 0, result.stdout
    return json.loads(result.stdout)["id"]


class TestTheCeilingRefuses:
    def test_a_create_over_the_ceiling_exits_9(self, settings: Settings) -> None:
        result = _add("note", "Too long", "x" * 80)
        assert result.exit_code == 9
        assert "80 chars" in result.stderr
        assert "50-char" in result.stderr
        # Refused before anything is written: a half-created document would
        # leave the id allocated against a file that does not exist.
        assert list(settings.docs_root.rglob("nt-*.md")) == []

    def test_a_body_at_the_ceiling_is_accepted(self) -> None:
        assert _add("note", "Exactly", "x" * 50) is not None

    def test_an_edit_that_crosses_the_ceiling_exits_9(self) -> None:
        doc_id = _add_ok("note", "Small", "short")
        result = run("update", doc_id, "--replace-body", "--force", "--body", "x" * 80)
        assert result.exit_code == 9
        assert "50-char" in result.stderr

    def test_the_other_types_are_untouched(self) -> None:
        # No shipped type declares a ceiling, so the `software` profile's types
        # take a body of any size beside a capped one in the same store.
        assert _add_ok("decision", "Long", "x" * 5000)


class TestGrowthIsTheTrigger:
    """A document already over its ceiling must not be locked out of the fix."""

    @pytest.fixture
    def oversized(self, settings: Settings) -> str:
        """A `note` over its ceiling, made the way a real one gets there: the
        ceiling was lowered under a document that was legal when it was written.
        """
        settings.schema_path.write_text(
            SCHEMA.replace("max_body_chars: 50\n  memo", "max_body_chars: 500\n  memo"),
            encoding="utf-8",
        )
        doc_id = _add_ok("note", "Big", "x" * 200)
        settings.schema_path.write_text(SCHEMA, encoding="utf-8")
        return doc_id

    def test_a_metadata_edit_still_passes(self, oversized: str) -> None:
        assert run("update", oversized, "--set-owner", "sk").exit_code == 0

    def test_a_shorter_body_still_passes(self, oversized: str) -> None:
        # Still over the ceiling at 100 chars, and still allowed: this is the
        # edit that walks the document back, and refusing it would leave
        # hand-editing markdown as the only repair.
        result = run("update", oversized, "--replace-body", "--force", "--body", "x" * 100)
        assert result.exit_code == 0
        assert len(json.loads(result.stdout)["body"]) == 100

    def test_growing_an_already_oversized_body_is_refused(self, oversized: str) -> None:
        result = run("update", oversized, "--append-section", "More", "--body", "y" * 10)
        assert result.exit_code == 9

    def test_a_retype_carrying_the_body_unchanged_passes(self, oversized: str) -> None:
        # A retype is not a content change, and the body did not grow — so the
        # ceiling of the type being entered does not strand the document.
        assert run("update", oversized, "--type", "memo").exit_code == 0


class TestEnforceFalseReports:
    def test_the_write_succeeds_and_warns(self) -> None:
        result = _add("memo", "Long memo", "x" * 80)
        assert result.exit_code == 0
        assert "80 chars" in result.stderr

    def test_the_notice_travels_in_the_payload(self) -> None:
        # Not only on stderr: over MCP there is no stderr to read, so the
        # machine-readable half is what an agent actually sees.
        payload = json.loads(_add("memo", "Long memo", "x" * 80).stdout)
        assert "50-char" in payload["body_limit_notice"]

    def test_nothing_is_said_under_the_ceiling(self) -> None:
        payload = json.loads(_add("memo", "Short memo", "x" * 10).stdout)
        assert "body_limit_notice" not in payload


class TestMechanicalRewritesAreExempt:
    """The writes nobody asked for never reach the ceiling.

    One refusing halfway through a corpus-wide rewrite leaves it half-applied,
    and `check --fix` is the only sanctioned recovery path — a repair that
    refuses to run is not a repair.
    """

    @pytest.fixture
    def oversized_tagged(self, settings: Settings) -> str:
        assert run("tag", "add", "old", "--description", "T.").exit_code == 0
        settings.schema_path.write_text(
            SCHEMA.replace("max_body_chars: 50\n  memo", "max_body_chars: 500\n  memo"),
            encoding="utf-8",
        )
        result = run(
            "add",
            "--type",
            "note",
            "--title",
            "Big",
            "--description",
            "D",
            "--tags",
            "old",
            "--body",
            "x" * 200,
        )
        assert result.exit_code == 0, result.stdout
        settings.schema_path.write_text(SCHEMA, encoding="utf-8")
        return json.loads(result.stdout)["id"]

    def test_a_tag_rename_rewrites_an_oversized_document(self, oversized_tagged: str) -> None:
        assert run("tag", "rename", "old", "new").exit_code == 0
        payload = json.loads(run("get", oversized_tagged).stdout)
        assert payload["tags"] == ["new"]
        assert len(payload["body"]) == 200

    def test_check_fix_runs_over_an_oversized_document(self, oversized_tagged: str) -> None:
        result = run("check", "--fix")
        assert result.exit_code == 0, result.stderr
        assert len(json.loads(run("get", oversized_tagged).stdout)["body"]) == 200

    def test_a_forced_delete_strips_the_edge_from_an_oversized_document(
        self, oversized_tagged: str, settings: Settings
    ) -> None:
        target = _add_ok("decision", "Target", "body")
        assert run("update", oversized_tagged, "--set-related", target).exit_code == 0
        assert run("delete", target, "--force").exit_code == 0
        payload = json.loads(run("get", oversized_tagged).stdout)
        assert payload.get("related", []) == []
        assert len(payload["body"]) == 200
        assert list(settings.docs_root.rglob(f"{target}*.md")) == []


class TestBothTiersReadTheOneKey:
    """One number, and `max_body_chars_enforce` picks the tier it acts at."""

    def test_the_lint_names_a_document_over_the_limit(self) -> None:
        # `memo` does not enforce, so this is the whole of what the key used to
        # do — and it still does it, with no second key to rename.
        doc_id = _add_ok("memo", "Long memo", "x" * 80)
        findings = json.loads(run("lint", "--deep").stdout)
        assert [f["doc_ids"] for f in findings if f["kind"] == "scope-creep"] == [[doc_id]]

    def test_an_enforcing_type_is_linted_too(self, settings: Settings) -> None:
        # The ceiling stops growth; it does not retroactively shrink what was
        # already there, so the lint is the half that reports the backlog.
        settings.schema_path.write_text(
            SCHEMA.replace("max_body_chars: 50\n  memo", "max_body_chars: 500\n  memo"),
            encoding="utf-8",
        )
        doc_id = _add_ok("note", "Big", "x" * 200)
        settings.schema_path.write_text(SCHEMA, encoding="utf-8")
        findings = json.loads(run("lint", "--deep").stdout)
        assert [f["doc_ids"] for f in findings if f["kind"] == "scope-creep"] == [[doc_id]]

    def test_zero_turns_off_both_halves(self, settings: Settings) -> None:
        settings.schema_path.write_text(
            SCHEMA.replace("max_body_chars: 50\n  memo", "max_body_chars: 0\n  memo").replace(
                "    max_body_chars: 50\n    max_body_chars_enforce: false\n", ""
            ),
            encoding="utf-8",
        )
        assert _add_ok("note", "Register", "x" * 20_000)
        findings = json.loads(run("lint", "--deep").stdout)
        assert [f for f in findings if f["kind"] == "scope-creep"] == []


class TestSchemaShowNamesTheCeiling:
    def test_it_is_discoverable_without_reading_the_file(self) -> None:
        # The one surface an agent can parse: the file merges core -> profiles
        # -> inline, so what it says and what is enforced are not the same text.
        types = {t["name"]: t for t in json.loads(run("schema", "show").stdout)["types"]}
        assert types["note"]["max_body_chars"] == 50
        assert types["memo"]["max_body_chars_enforce"] is False


class TestTheLoaderRefusesADeadRelaxation:
    def test_it_fails_the_next_command_not_a_later_write(self, settings: Settings) -> None:
        # `enforce: false` with no ceiling to relax reads as configuration and
        # configures nothing. Naming it at load time means the store stops on
        # the next command rather than quietly taking writes it looks capped.
        settings.schema_path.write_text(
            "types:\n  note:\n    prefix: nt\n    default_status: active\n"
            "    statuses:\n      active: []\n    max_body_chars_enforce: false\n",
            encoding="utf-8",
        )
        result = run("schema", "validate")
        assert result.exit_code != 0
        assert "max_body_chars_enforce" in result.stderr
