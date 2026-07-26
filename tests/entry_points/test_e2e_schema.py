"""End-to-end tests for ``docir schema show/validate`` (ADR-0010)."""

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
    monkeypatch.setenv("DOCIR_NO_DAEMON", "1")
    monkeypatch.delenv("DOCIR_HOME", raising=False)
    monkeypatch.delenv("DOCIR_EMBEDDER", raising=False)


def _home(tmp_path: Path, body: str | None = None) -> str:
    """A store home, optionally seeded with a specific docs-schema.yaml."""
    home = tmp_path / ".docir"
    home.mkdir(parents=True, exist_ok=True)
    if body is not None:
        (home / "docs-schema.yaml").write_text(body, encoding="utf-8")
    return str(home)


class TestSchemaShow:
    def test_reports_the_merged_schema_as_json(self, tmp_path: Path) -> None:
        result = run("--home", _home(tmp_path, "profiles: [qa]\n"), "schema", "show")
        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        names = {entry["name"] for entry in payload["types"]}
        # `decision` comes from the frozen core, the rest from the qa profile —
        # the merged view is the point, the file only names one profile.
        assert {"decision", "test_plan", "test_case"} <= names
        assert "supersedes" in payload["relation_types"]

    def test_pretty_output_renders_a_table(self, tmp_path: Path) -> None:
        result = run("--home", _home(tmp_path), "--pretty", "schema", "show")
        assert result.exit_code == 0
        assert "relation kinds" in result.stdout
        # Short values only — Rich truncates wide cells at the test terminal width.
        assert "decision" in result.stdout
        assert "adr" in result.stdout

    def test_defaults_to_the_software_profile(self, tmp_path: Path) -> None:
        result = run("--home", _home(tmp_path), "schema", "show")
        assert result.exit_code == 0
        names = {entry["name"] for entry in json.loads(result.stdout)["types"]}
        assert names == {"decision", "issue", "architecture", "release_note"}


class TestSchemaValidate:
    def test_accepts_a_good_schema(self, tmp_path: Path) -> None:
        result = run(
            "--json", "--home", _home(tmp_path, "profiles: [software, qa]\n"), "schema", "validate"
        )
        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["valid"] is True
        assert payload["types"] == 6

    def test_json_path_keeps_the_store_path_intact(self, tmp_path: Path) -> None:
        # Regression: this rendered Rich text on the agent path, and Rich hard-wraps
        # at 80 columns — which broke the store path mid-token, so a captured path
        # was unusable.
        home = _home(tmp_path, "profiles: [software]\n")
        result = run("--json", "--home", home, "schema", "validate")
        assert result.exit_code == 0
        assert json.loads(result.stdout)["path"] == str(Path(home) / "docs-schema.yaml")

    def test_pretty_still_renders_for_humans(self, tmp_path: Path) -> None:
        result = run("--pretty", "--home", _home(tmp_path), "schema", "validate")
        assert result.exit_code == 0
        assert "schema valid" in result.stdout

    @pytest.mark.parametrize(
        ("body", "reason"),
        [
            ("profiles: [nonsense]\n", "unknown profile"),
            ("profiles: software\n", "profiles not a list"),
            # `statuses` as a list rather than a mapping — the single most likely
            # mistake when authoring a type without reading the grammar.
            (
                "types:\n  tp:\n    prefix: tp\n    statuses: [draft]\n    default_status: draft\n",
                "statuses not a mapping",
            ),
            # A prefix already taken by the core `decision` type.
            (
                "profiles: [software]\ntypes:\n  tp:\n    prefix: adr\n"
                "    statuses:\n      draft: []\n    default_status: draft\n",
                "duplicate prefix",
            ),
        ],
    )
    def test_rejects_a_broken_schema(self, tmp_path: Path, body: str, reason: str) -> None:
        result = run("--home", _home(tmp_path, body), "schema", "validate")
        assert result.exit_code != 0, f"expected failure: {reason}"

    def test_diagnoses_a_schema_too_broken_to_start_the_store(self, tmp_path: Path) -> None:
        # The reason both commands run in-process (ADR-0010): build_container
        # loads the schema, so routing them through the dispatcher would make
        # them unreachable in exactly the situation they exist for. A normal
        # command must fail here, while `schema validate` still reports why.
        home = _home(tmp_path, "profiles: [nonsense]\n")
        assert run("--home", home, "query").exit_code != 0

        result = run("--home", home, "schema", "validate")
        assert result.exit_code == 3
        assert "nonsense" in result.stderr
