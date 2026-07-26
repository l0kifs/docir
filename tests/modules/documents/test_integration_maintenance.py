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


def test_check_reports_unknown_type(dispatcher: Dispatcher, settings: Settings) -> None:
    # A file whose type is not in the active schema (e.g. its profile was
    # disabled) is surfaced, not silently skipped — its grammar can't be enforced.
    (settings.docs_root / "hyp-0001-guess.md").write_text(
        "---\n"
        "created: '2026-07-07'\n"
        "description: a guess\n"
        "id: hyp-0001\n"
        "related: []\n"
        "status: proposed\n"
        "tags: []\n"
        "title: A guess\n"
        "type: hypothesis\n"  # not in the default (software) schema
        "updated: '2026-07-07'\n"
        "---\n\nbody\n",
        encoding="utf-8",
    )
    dispatcher.dispatch("reindex", {})
    issues = dispatcher.dispatch("check", {})
    assert any(i["kind"] == "unknown-type" and "hyp-0001" in i["doc_ids"] for i in issues)


def _stale_decision_file(*, verified: str | None) -> str:
    # A `decision` (365-day cadence) last touched in early 2024 — far past due
    # against the fixture clock (2026-07-07) unless recently verified.
    verified_line = f"verified: '{verified}'\n" if verified else ""
    return (
        "---\n"
        "created: '2024-01-01'\n"
        "description: an old accepted decision\n"
        "id: adr-0001\n"
        "owner: platform-team\n"
        "related: []\n"
        "status: accepted\n"
        "tags: []\n"
        "title: Old decision\n"
        "type: decision\n"
        "updated: '2024-01-01'\n"
        f"{verified_line}"
        "---\n\nbody\n"
    )


def test_check_reports_stale_documents(dispatcher: Dispatcher, settings: Settings) -> None:
    decisions = settings.docs_root / "decisions"
    decisions.mkdir(parents=True, exist_ok=True)
    (decisions / "adr-0001-old.md").write_text(
        _stale_decision_file(verified=None), encoding="utf-8"
    )
    dispatcher.dispatch("reindex", {})
    issues = dispatcher.dispatch("check", {})
    assert any(i["kind"] == "stale" and "adr-0001" in i["doc_ids"] for i in issues)
    # The staleness is also carried on the read side (skeleton + full view).
    assert dispatcher.dispatch("get", {"doc_id": "adr-0001"})["stale"] is True


def test_recent_verification_clears_staleness(dispatcher: Dispatcher, settings: Settings) -> None:
    decisions = settings.docs_root / "decisions"
    decisions.mkdir(parents=True, exist_ok=True)
    (decisions / "adr-0001-old.md").write_text(
        _stale_decision_file(verified="2026-07-01"), encoding="utf-8"
    )
    dispatcher.dispatch("reindex", {})
    issues = dispatcher.dispatch("check", {})
    assert not any(i["kind"] == "stale" for i in issues)


# -- repair (`docir check --fix`) -------------------------------------------
#
# Guards GAP-012: `check` reported four kinds of corrupt state and nothing could
# fix any of them, while the product's own rule says agents never edit markdown
# directly — so recovery required the one action the design forbids.

_BRANCH_DUPLICATE = (
    "---\ncreated: '2026-07-01'\ndescription: authored on another branch\n"
    "id: adr-0001\nrelated: []\nstatus: proposed\ntags: []\ntitle: From branch\n"
    "type: decision\nupdated: '2026-07-01'\n---\n\nbranch body\n"
)


def test_repair_reissues_a_duplicate_id_and_keeps_both_documents(
    dispatcher: Dispatcher, settings: Settings
) -> None:
    dispatcher.dispatch("add", {"type": "decision", "title": "Original", "description": "d"})
    # A merge brings a second file claiming the same id; the index dedupes by
    # primary key, so one document is invisible to every read path.
    (settings.docs_root / "decisions" / "adr-0001-from-branch.md").write_text(
        _BRANCH_DUPLICATE, encoding="utf-8"
    )

    result = dispatcher.dispatch("repair", {})

    assert [a["kind"] for a in result["actions"]] == ["duplicate-id"]
    assert not [i for i in result["remaining"] if i["kind"] == "duplicate-id"]
    # Both documents survive and are reachable, under distinct ids.
    titles = {d["title"] for d in dispatcher.dispatch("query", {})}
    assert titles == {"Original", "From branch"}


def test_repair_lets_the_oldest_file_keep_the_id(
    dispatcher: Dispatcher, settings: Settings
) -> None:
    # Existing `related` edges were written against whichever document held the
    # id first, and an edge cannot say which of the two it meant — so the older
    # one keeps it. The branch file below is backdated to 2026-07-01.
    dispatcher.dispatch("add", {"type": "decision", "title": "Original", "description": "d"})
    (settings.docs_root / "decisions" / "adr-0001-from-branch.md").write_text(
        _BRANCH_DUPLICATE, encoding="utf-8"
    )

    dispatcher.dispatch("repair", {})

    assert dispatcher.dispatch("get", {"doc_id": "adr-0001"})["title"] == "From branch"


def test_repair_drops_dead_edges(dispatcher: Dispatcher, settings: Settings) -> None:
    dispatcher.dispatch("add", {"type": "decision", "title": "Target", "description": "d"})
    dispatcher.dispatch(
        "add",
        {"type": "decision", "title": "Source", "description": "d", "related": ["adr-0001"]},
    )
    dispatcher.dispatch("delete", {"doc_id": "adr-0001", "force": True})
    assert any(i["kind"] == "dangling" for i in dispatcher.dispatch("check", {}))

    result = dispatcher.dispatch("repair", {})

    assert [a["kind"] for a in result["actions"]] == ["dangling"]
    assert not [i for i in result["remaining"] if i["kind"] == "dangling"]
    # Repaired in the canonical file, not just the index.
    source = settings.docs_root / "decisions" / "adr-0002-source.md"
    assert "adr-0001" not in source.read_text(encoding="utf-8")


def test_repair_does_not_reset_the_staleness_clock(
    dispatcher: Dispatcher, settings: Settings
) -> None:
    # Dropping a dead link is maintenance, not a human re-reading the document.
    # Bumping `updated` would make an overdue doc look freshly reviewed.
    dispatcher.dispatch("add", {"type": "decision", "title": "Target", "description": "d"})
    dispatcher.dispatch(
        "add",
        {"type": "decision", "title": "Source", "description": "d", "related": ["adr-0001"]},
    )
    before = dispatcher.dispatch("get", {"doc_id": "adr-0002"})["updated"]
    dispatcher.dispatch("delete", {"doc_id": "adr-0001", "force": True})

    dispatcher.dispatch("repair", {})

    assert dispatcher.dispatch("get", {"doc_id": "adr-0002"})["updated"] == before


def test_repair_leaves_malformed_files_to_a_human(
    dispatcher: Dispatcher, settings: Settings
) -> None:
    # A file that will not parse needs someone to say what it was meant to be.
    (settings.docs_root / "decisions").mkdir(parents=True, exist_ok=True)
    (settings.docs_root / "decisions" / "adr-9999-broken.md").write_text(
        _MALFORMED_FILE, encoding="utf-8"
    )

    result = dispatcher.dispatch("repair", {})

    assert not result["actions"]
    assert any(i["kind"] == "malformed" for i in result["remaining"])


def test_repair_on_a_healthy_corpus_changes_nothing(dispatcher: Dispatcher) -> None:
    dispatcher.dispatch("add", {"type": "decision", "title": "Target", "description": "d"})
    dispatcher.dispatch(
        "add",
        {"type": "decision", "title": "Source", "description": "d", "related": ["adr-0001"]},
    )
    result = dispatcher.dispatch("repair", {})
    assert not result["actions"]
    assert not [i for i in result["remaining"] if i["severity"] == "error"]
