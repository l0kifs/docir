"""End-to-end tests for ``docir init`` and project-store discovery via the CLI."""

from __future__ import annotations

import json
import re
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
    # Pin the hashing embedder: the real default downloads a model, which would
    # make the suite slow and network-dependent.
    monkeypatch.setenv("DOCIR_EMBEDDER", "deterministic")


class TestInit:
    def test_init_creates_project_store(self, tmp_path: Path) -> None:
        result = run("init", str(tmp_path))
        assert result.exit_code == 0
        assert (tmp_path / ".docir" / "docs-schema.yaml").exists()
        assert (tmp_path / ".docir" / ".gitignore").exists()

    def test_unknown_profile_exits_3(self, tmp_path: Path) -> None:
        assert run("init", str(tmp_path), "--profiles", "bogus").exit_code == 3

    def test_defaults_to_random_ids(self, tmp_path: Path) -> None:
        # A repo store is shared, and two branches minting `sequential` ids each
        # produce adr-0007 without noticing until the merge. init opts out of
        # that class of collision by default.
        assert run("init", str(tmp_path)).exit_code == 0
        schema = (tmp_path / ".docir" / "docs-schema.yaml").read_text(encoding="utf-8")
        assert "id_style: random" in schema

        added = run(
            "--home",
            str(tmp_path / ".docir"),
            "add",
            "--type",
            "decision",
            "--title",
            "T",
            "--description",
            "d",
        )
        assert re.fullmatch(r"adr-[0-9a-f]{12}", json.loads(added.stdout)["id"])

    def test_id_style_sequential_opts_back_in(self, tmp_path: Path) -> None:
        assert run("init", str(tmp_path), "--id-style", "sequential").exit_code == 0
        assert "id_style: sequential" in (tmp_path / ".docir" / "docs-schema.yaml").read_text(
            encoding="utf-8"
        )

        added = run(
            "--home",
            str(tmp_path / ".docir"),
            "add",
            "--type",
            "decision",
            "--title",
            "T",
            "--description",
            "d",
        )
        assert json.loads(added.stdout)["id"] == "adr-0001"

    def test_unknown_id_style_exits_3(self, tmp_path: Path) -> None:
        assert run("init", str(tmp_path), "--id-style", "uuid").exit_code == 3

    def test_id_style_applies_to_profile_types_too(self, tmp_path: Path) -> None:
        # The schema-wide setting must reach the types the core and the profiles
        # contribute, not just inline ones — `issue` comes from the software profile.
        assert run("init", str(tmp_path), "--id-style", "random").exit_code == 0
        added = run(
            "--home",
            str(tmp_path / ".docir"),
            "add",
            "--type",
            "issue",
            "--title",
            "T",
            "--description",
            "d",
        )
        assert re.fullmatch(r"issue-[0-9a-f]{12}", json.loads(added.stdout)["id"])

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
        # What matters here is *where* the document landed, not what it is called:
        # `init` picks the id style, so assert on the returned id rather than a
        # literal (this pinned "adr-0001" until init started defaulting to random).
        doc_id = json.loads(added.stdout)["id"]
        assert list((proj / ".docir" / "docs" / "decisions").glob(f"{doc_id}-*.md"))


class TestInitHonoursHome:
    """`docir init` used to ignore `--home` (guards issue-638068ed09a6).

    Every other command honours it; `init` computed its store from the
    positional directory alone, so `docir --home /srv/docs init` silently
    created `<cwd>/.docir` — the store landed in whatever directory the shell
    happened to be in, and in a repository that meant an unrequested `.docir/`.
    Found when a probe did exactly that to docir's own checkout.
    """

    def test_home_names_the_store_directly(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.delenv("DOCIR_HOME", raising=False)
        store = tmp_path / "srv" / "docs"
        assert run("--home", str(store), "init").exit_code == 0
        assert (store / "docs-schema.yaml").exists()

    def test_positional_directory_still_gets_a_dot_docir(self, tmp_path: Path) -> None:
        project = tmp_path / "project"
        assert run("init", str(project)).exit_code == 0
        assert (project / ".docir" / "docs-schema.yaml").exists()

    def test_both_is_refused_rather_than_silently_preferred(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        # They disagree about where the store goes; picking one quietly is how
        # the original defect behaved.
        monkeypatch.delenv("DOCIR_HOME", raising=False)
        result = run("--home", str(tmp_path / "store"), "init", str(tmp_path / "project"))
        assert result.exit_code == 2  # ValidationError, not a traceback
        assert not (tmp_path / "store").exists()
        assert not (tmp_path / "project").exists()


def test_force_schema_stands_alone(tmp_path: Path, settings) -> None:
    """Guards issue-9417ffd5306d: `--force-schema` without `--force` was a silent no-op."""
    assert run("init", str(tmp_path)).exit_code == 0
    schema = tmp_path / ".docir" / "docs-schema.yaml"
    schema.write_text(schema.read_text(encoding="utf-8") + "\n# customised\n", encoding="utf-8")

    assert run("init", str(tmp_path), "--force-schema").exit_code == 0

    assert "# customised" not in schema.read_text(encoding="utf-8")


class TestNestedStoreWarning:
    def test_init_beneath_an_existing_store_warns_on_stderr(self, tmp_path: Path) -> None:
        # issue-e10cde8c5085: the warning is the whole fix — the store is still created,
        # because a monorepo subproject with its own store is legitimate.
        assert run("init", str(tmp_path)).exit_code == 0
        nested = tmp_path / "team"
        nested.mkdir()
        result = run("init", str(nested))
        assert result.exit_code == 0
        assert (nested / ".docir").is_dir()
        # Rich wraps stderr at the console width, and wraps *inside* a long
        # path, so the path is matched with whitespace removed entirely.
        assert "already a docir store" in " ".join(result.stderr.split())
        assert str(tmp_path / ".docir") in "".join(result.stderr.split())

    def test_a_top_level_init_says_nothing(self, tmp_path: Path) -> None:
        # A count of warnings cannot tell "nothing to warn about" from "the
        # warning never fires", so pin the quiet case too.
        assert "already a docir store" not in run("init", str(tmp_path)).stderr

    def test_the_json_carries_the_enclosing_store(self, tmp_path: Path) -> None:
        run("init", str(tmp_path))
        nested = tmp_path / "team"
        nested.mkdir()
        payload = json.loads(run("--json", "init", str(nested)).stdout)
        assert payload["enclosing_home"] == str((tmp_path / ".docir").resolve())
