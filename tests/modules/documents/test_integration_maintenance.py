"""Integration tests for reindex, check (Tier 1), lint (Tier 2), embed flush."""

from __future__ import annotations

from docir.config.settings import Settings
from docir.entry_points.dispatch import Dispatcher

# Valid YAML, but `created`/`updated` are not ISO dates — a hand-edit/foreign file.
_MALFORMED_FILE = (
    "---\nid: adr-9999\ntitle: Broken\ndescription: d\ntype: decision\n"
    "status: proposed\ncreated: not-a-date\nupdated: not-a-date\n"
    "tags: []\nrelated: []\n---\n\nbody\n"
)


def test_check_reports_orphans(dispatcher: Dispatcher) -> None:
    dispatcher.dispatch("add", {"type": "decision", "title": "Lonely", "description": "d"})
    issues = dispatcher.dispatch("check", {})
    assert any(i["kind"] == "orphan" for i in issues)


def test_check_clean_when_connected(seeded: Dispatcher) -> None:
    issues = seeded.dispatch("check", {})
    assert all(i["kind"] != "orphan" for i in issues)


def test_lint_flags_near_duplicates(dispatcher: Dispatcher) -> None:
    for title in ("Auth tokens one", "Auth tokens two"):
        dispatcher.dispatch(
            "add",
            {
                "type": "decision",
                "title": title,
                "description": "identical text about authentication tokens and refresh",
                "body": "the same body about authentication tokens and refresh sessions",
            },
        )
    findings = dispatcher.dispatch("lint", {})
    assert any(f["kind"] == "duplicate" for f in findings)


def test_embed_flush_returns_count(dispatcher: Dispatcher) -> None:
    dispatcher.dispatch("add", {"type": "decision", "title": "A", "description": "d"})
    # Inline scheduler already embedded on add, so nothing remains dirty.
    assert dispatcher.dispatch("embed_flush", {})["embedded"] == 0


def test_reindex_indexes_external_files(dispatcher: Dispatcher, settings: Settings) -> None:
    # A markdown file created out-of-band (e.g. a fresh clone or hand edit) is
    # picked up by a full reindex — the index is rebuilt from the files.
    dispatcher.dispatch("add", {"type": "decision", "title": "Existing", "description": "d"})
    decisions = settings.docs_root / "decisions"
    (decisions / "adr-0002-manual.md").write_text(
        "---\n"
        "created: '2026-07-07'\n"
        "description: manual doc\n"
        "id: adr-0002\n"
        "related: []\n"
        "status: proposed\n"
        "tags: []\n"
        "title: Manual\n"
        "type: decision\n"
        "updated: '2026-07-07'\n"
        "---\n\nmanual body\n",
        encoding="utf-8",
    )
    result = dispatcher.dispatch("reindex", {})
    assert result["documents_indexed"] == 2
    assert dispatcher.dispatch("get", {"doc_id": "adr-0002"})["title"] == "Manual"


def test_reindex_removes_deleted_files(dispatcher: Dispatcher, settings: Settings) -> None:
    dispatcher.dispatch("add", {"type": "decision", "title": "Gone", "description": "d"})
    path = settings.docs_root / "decisions" / "adr-0001-gone.md"
    path.unlink()
    result = dispatcher.dispatch("reindex", {})
    assert result["documents_removed"] == 1


def test_reindex_changed_only(dispatcher: Dispatcher, settings: Settings) -> None:
    dispatcher.dispatch("add", {"type": "decision", "title": "A", "description": "d"})
    result = dispatcher.dispatch("reindex", {"changed_only": True})
    # Unchanged file is skipped.
    assert result["documents_indexed"] == 0


def test_reindex_embeddings(seeded: Dispatcher) -> None:
    assert seeded.dispatch("reindex", {"embeddings": True})["embedded"] >= 1


def test_reindex_skips_malformed_file(dispatcher: Dispatcher, settings: Settings) -> None:
    # F2: a malformed hand-edited file must not abort the reindex of good files.
    dispatcher.dispatch("add", {"type": "decision", "title": "Good", "description": "d"})
    (settings.docs_root / "decisions" / "adr-9999-bad.md").write_text(
        _MALFORMED_FILE, encoding="utf-8"
    )
    dispatcher.dispatch("reindex", {})  # must not raise
    assert dispatcher.dispatch("get", {"doc_id": "adr-0001"})["title"] == "Good"


def test_check_reports_malformed_file(dispatcher: Dispatcher, settings: Settings) -> None:
    # F2: the skipped file is surfaced as a Tier 1 finding, not silently ignored.
    dispatcher.dispatch("add", {"type": "decision", "title": "Good", "description": "d"})
    (settings.docs_root / "decisions" / "adr-9999-bad.md").write_text(
        _MALFORMED_FILE, encoding="utf-8"
    )
    issues = dispatcher.dispatch("check", {})
    assert any(i["kind"] == "malformed" for i in issues)
