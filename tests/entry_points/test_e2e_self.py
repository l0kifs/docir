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
    result = runner.invoke(app, ["--no-daemon", "self", "upgrade", project_root, "--no-package"])
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def test_status_reports_the_installation_without_touching_the_network(
    settings: Settings, tmp_path
) -> None:
    # No cached answer and no --refresh: `latest` is absent, which means
    # *unknown*. If this ever fetched, the suite would need to be online.
    result = runner.invoke(app, ["--no-daemon", "self", "status"])
    assert result.exit_code == 0, result.output
    status = json.loads(result.stdout)
    assert status["installed"] == __version__
    assert "latest" not in status, "trimmed away: unknown, not up to date"
    # The suite runs from a checkout, so docir must refuse to upgrade itself.
    assert status["method"] == "project" and "upgrade_command" not in status


def test_status_reads_the_answer_the_daemon_left(settings: Settings) -> None:
    settings.ensure_directories()
    settings.release_cache_path.write_text(
        json.dumps({"latest": "99.0.0", "checked_on": "2026-07-07"}), encoding="utf-8"
    )
    status = json.loads(runner.invoke(app, ["--no-daemon", "self", "status"]).stdout)
    assert (status["latest"], status["update_available"]) == ("99.0.0", True)
    assert status["checked_on"] == "2026-07-07"


def test_upgrade_does_not_install_a_package_it_does_not_own(settings: Settings, tmp_path) -> None:
    """The safety net: in a checkout, the package step says why and does nothing."""
    result = runner.invoke(app, ["--no-daemon", "self", "upgrade", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "package not upgraded" in result.stderr
    assert "uv lock --upgrade-package docir" in result.stderr
    assert json.loads(result.stdout)["reindex"]["documents_indexed"] == 0


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


def test_a_second_upgrade_does_not_rebuild_what_the_first_one_built(
    settings: Settings, tmp_path
) -> None:
    """The command a user runs when it turns out there was nothing to upgrade.

    The rebuild re-embeds every document it re-saves — 96% of the command's
    runtime, ~58 s on a 315-document store — and running it against an index
    this same build produced recomputes vectors identical to the ones already
    stored. The first upgrade stamps the running version; the second one reads
    that stamp and re-saves nothing.
    """
    _add()
    assert _upgrade(str(tmp_path))["reindex"]["documents_indexed"] == 1

    again = _upgrade(str(tmp_path))["reindex"]
    assert again["documents_indexed"] == 0
    assert not again.get("embeddings_recomputed")
    # Cheap does not mean partial: the tag registry is still walked, and the two
    # stamps are still written — that combination is what `reindex --embeddings`
    # got wrong (adr-6a4718fa7a7d).
    assert "stale-index-build" not in {
        finding["kind"] for finding in _upgrade(str(tmp_path)).get("findings", [])
    }


def test_a_skipped_rebuild_says_so_rather_than_printing_a_bare_zero(
    settings: Settings, tmp_path
) -> None:
    # "reindex 0 documents" reads like the rebuild failed. The package line
    # already spells out "already the newest build" for the same reason.
    _add()
    _upgrade(str(tmp_path))
    result = runner.invoke(
        app, ["--no-daemon", "--pretty", "self", "upgrade", str(tmp_path), "--no-package"]
    )
    assert result.exit_code == 0, result.output
    assert "already built by this version" in result.stdout


def test_the_re_embed_count_and_the_vector_count_are_both_reported(
    settings: Settings, tmp_path
) -> None:
    """It reported the document count under the word "vectors".

    The queue is keyed by document and each one writes a vector per `##` section
    as well as its own (adr-927aa43d9635), so the two are ~4x apart on a real
    corpus: the 315-document rebuild this was noticed on wrote 1,326 vectors and
    said "315 vectors". Understating the work 4x is worse than not reporting it,
    which is the state issue-b24e14474820 already rejected — and the vector count
    is the one that explains the runtime, since embedding is ~96% of a rebuild
    and is linear in vectors.
    """
    result = runner.invoke(
        app,
        [
            "--no-daemon",
            "add",
            "--type",
            "decision",
            "--title",
            "Sectioned",
            "--description",
            "d",
            "--body",
            "## One\n\nalpha\n\n## Two\n\nbeta",
        ],
    )
    assert result.exit_code == 0, result.output

    result = runner.invoke(
        app, ["--no-daemon", "--pretty", "self", "upgrade", str(tmp_path), "--no-package"]
    )
    assert result.exit_code == 0, result.output
    assert "1 re-embedded (2 vectors)" in result.stdout


def test_a_vector_count_equal_to_the_document_count_is_not_printed(
    settings: Settings, tmp_path
) -> None:
    # A document with no `##` sections writes exactly one vector, and
    # "1 re-embedded (1 vectors)" is both redundant and ungrammatical.
    _add()
    result = runner.invoke(
        app, ["--no-daemon", "--pretty", "self", "upgrade", str(tmp_path), "--no-package"]
    )
    assert result.exit_code == 0, result.output
    assert "1 re-embedded" in result.stdout
    assert "vectors" not in result.stdout


def test_it_grows_a_single_file_skill_into_a_directory(settings: Settings, tmp_path) -> None:
    """The migration every existing adopter goes through, and it happens here.

    Before adr-e18250eb3081 a skill was one file. `self upgrade` is the command
    that carries those repos across, so it has to *add* the reference files
    rather than only restamp the entry point — and the reference files are the
    guide now, so an upgrade that skipped them would leave the adopter with a
    255-line SKILL.md whose every link is broken.
    """
    project = tmp_path / "project"
    skill = project / ".claude" / "skills" / "docir" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: docir\ndescription: an older guide\n---\n"
        "<!-- docir:v0.0.1 — generated file, do not edit by hand -->\n"
        "# docir — Agent Guide\n\nthe whole guide, in one file\n",
        encoding="utf-8",
    )

    agents = _upgrade(str(project))["agents"]
    assert [file["previous_version"] for file in agents] == ["0.0.1"]
    # Named, not counted: a run that wrote one reference file and dropped five
    # reports the same "it installed extras" as a correct one.
    assert agents[0]["extras"] == sorted(agents[0]["extras"])
    assert all(name.startswith("reference/") for name in agents[0]["extras"])
    written = {path.relative_to(skill.parent).as_posix() for path in skill.parent.rglob("*.md")}
    assert written == {"SKILL.md", *agents[0]["extras"]}


def test_upgrade_reports_an_install_the_same_way_agent_update_does(
    settings: Settings, tmp_path
) -> None:
    """Two serializers of one event is how `self upgrade` came to under-report.

    It listed the entry point and said nothing about the six reference files
    beside it, while `docir agent update` named them — the same install
    described two ways, one of them wrong.
    """
    project = tmp_path / "project"
    project.mkdir()
    assert runner.invoke(app, ["--no-daemon", "agent", "install", str(project)]).exit_code == 0

    from_update = json.loads(
        runner.invoke(app, ["--no-daemon", "--json", "agent", "update", str(project)]).stdout
    )
    from_upgrade = _upgrade(str(project))["agents"]
    assert [set(row) for row in from_upgrade] == [set(row) for row in from_update]
    assert from_upgrade[0]["extras"], "the skill's reference files are absent from both"


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
