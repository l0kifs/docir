"""`docir build` end to end — a real store, a real directory of HTML.

The module tests cover the model and the markup. This covers the wiring the
command owns: which documents it enumerates, that bodies actually arrive (they
are absent from every list path, so a build that only ran `query` would produce
a site of empty pages), and that the output is a directory a person can open.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from docir.config.settings import Settings
from docir.entry_points.cli.app import app

runner = CliRunner()


@pytest.fixture
def store(settings: Settings) -> Settings:
    for args in (
        [
            "add",
            "--type",
            "decision",
            "--title",
            "Old way",
            "--description",
            "Previous.",
            "--body",
            "## Context\n\nThe old approach.",
        ],
        [
            "add",
            "--type",
            "issue",
            "--title",
            "A problem",
            "--description",
            "It broke.",
            "--body",
            "Details.",
        ],
    ):
        assert runner.invoke(app, ["--no-daemon", *args]).exit_code == 0
    return settings


def _build(tmp_path, *extra: str):
    return runner.invoke(app, ["--no-daemon", "build", "--out", str(tmp_path / "site"), *extra])


def test_it_builds_a_page_per_document_plus_index_and_graph(store, tmp_path) -> None:
    result = _build(tmp_path)
    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert report["documents"] == 2
    site = tmp_path / "site"
    assert (site / "index.html").exists()
    assert (site / "graph.html").exists()
    assert len(list(site.glob("*.html"))) == 4


def test_the_graph_page_carries_the_real_corpus(store, tmp_path) -> None:
    """The graph embeds its data at build time; a page with an empty payload
    renders a plausible blank map, which looks exactly like success."""
    _build(tmp_path)
    graph = (tmp_path / "site" / "graph.html").read_text(encoding="utf-8")
    assert '"t":"Old way"' in graph
    assert '"t":"A problem"' in graph


def test_bodies_reach_the_pages(store, tmp_path) -> None:
    """The build must `get` each document, not just `query` for skeletons.

    Every list path returns body-less skeletons by contract, so a build that
    stopped at `query` would succeed, report the right count, and publish empty
    pages — a failure that looks exactly like success from the outside.
    """
    _build(tmp_path)
    pages = " ".join(p.read_text(encoding="utf-8") for p in (tmp_path / "site").glob("adr-*.html"))
    assert "The old approach." in pages


def test_inactive_documents_are_published(store, tmp_path) -> None:
    """A reader must be able to follow a decision to the one that replaced it.

    Hiding closed documents is right for `context` — it is a working set — and
    wrong for a browsable corpus, where the superseded decision is exactly what
    someone arrives at from an old link.
    """
    created = json.loads(runner.invoke(app, ["--no-daemon", "query", "--type", "decision"]).stdout)
    doc_id = created[0]["id"]
    runner.invoke(app, ["--no-daemon", "update", doc_id, "--status", "accepted"])
    runner.invoke(app, ["--no-daemon", "update", doc_id, "--status", "superseded"])

    _build(tmp_path)
    assert (tmp_path / "site" / f"{doc_id}.html").exists()


def test_archived_documents_are_not_published_by_default(store, tmp_path) -> None:
    created = json.loads(runner.invoke(app, ["--no-daemon", "query", "--type", "issue"]).stdout)
    doc_id = created[0]["id"]
    runner.invoke(app, ["--no-daemon", "archive", doc_id])

    assert json.loads(_build(tmp_path).stdout)["documents"] == 1
    assert not (tmp_path / "site" / f"{doc_id}.html").exists()

    result = runner.invoke(
        app,
        ["--no-daemon", "build", "--out", str(tmp_path / "site2"), "--include-archived"],
    )
    assert json.loads(result.stdout)["documents"] == 2


def test_it_refuses_to_overwrite_someone_elses_directory(store, tmp_path) -> None:
    target = tmp_path / "site"
    target.mkdir()
    (target / "important.py").write_text("# not a site", encoding="utf-8")

    result = _build(tmp_path)
    assert result.exit_code != 0
    assert (target / "important.py").exists()


def test_a_second_build_into_its_own_output_is_fine(store, tmp_path) -> None:
    """The marker file is what makes "regenerate" safe to repeat."""
    assert _build(tmp_path).exit_code == 0
    assert _build(tmp_path).exit_code == 0


def test_an_empty_store_says_so(settings: Settings, tmp_path) -> None:
    """A fresh clone has no index, and a silent empty site looks like success.

    `.docir/docs/` is committed and the index is gitignored, so the first thing
    CI does is clone a store with no index at all. Without this, `build` writes
    an index page listing nothing, reports `"documents":0`, and exits 0 —
    indistinguishable from a store that is genuinely empty.
    """
    result = _build(tmp_path)
    assert result.exit_code == 0, "an empty store is legitimate, not an error"
    assert json.loads(result.stdout)["documents"] == 0
    assert "docir reindex" in str(result.stderr), "the fix was not named"
