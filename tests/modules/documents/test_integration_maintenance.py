"""Integration tests for reindex, check (Tier 1), lint (Tier 2), embed flush."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import closing

import pytest

from docir.config.settings import Settings
from docir.entry_points.composition import build_container
from docir.entry_points.dispatch import Dispatcher
from docir.platform.errors import (
    DocumentNotFoundError,
    MissingRequiredFieldError,
    ValidationError,
)

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


class TestChangedReindexStillRemovesDeletions:
    """`--changed` sweeps deleted files too (guards issue-c33edcf431fa).

    The sweep was skipped under `--changed`, so the fast path had quietly
    different semantics: a document deleted from the filesystem stayed indexed
    and kept being returned by every read path — `get` answered for a file that
    no longer existed — and nothing in `--help` or the README said so.

    Skipping it was never why `--changed` is fast. `scan()` runs in full either
    way (and `seen` must be complete for the id-counter restore), so the sweep
    costs one query; what `--changed` actually skips is the writes.
    """

    @staticmethod
    def _two_docs_then_delete_one(dispatcher: Dispatcher, settings: Settings) -> None:
        dispatcher.dispatch("add", {"type": "decision", "title": "Alpha", "description": "d"})
        dispatcher.dispatch("add", {"type": "decision", "title": "Beta", "description": "d"})
        (settings.docs_root / "decisions" / "adr-0001-alpha.md").unlink()

    def test_deletion_is_swept(self, dispatcher: Dispatcher, settings: Settings) -> None:
        self._two_docs_then_delete_one(dispatcher, settings)
        result = dispatcher.dispatch("reindex", {"changed_only": True})
        assert result["documents_removed"] == 1

    def test_the_deleted_document_leaves_every_read_path(
        self, dispatcher: Dispatcher, settings: Settings
    ) -> None:
        self._two_docs_then_delete_one(dispatcher, settings)
        dispatcher.dispatch("reindex", {"changed_only": True})
        assert [d["id"] for d in dispatcher.dispatch("query", {})] == ["adr-0002"]
        with pytest.raises(DocumentNotFoundError):
            dispatcher.dispatch("get", {"doc_id": "adr-0001"})

    def test_changed_still_skips_unchanged_files(
        self, dispatcher: Dispatcher, settings: Settings
    ) -> None:
        # The sweep must not turn --changed into a full reindex.
        dispatcher.dispatch("add", {"type": "decision", "title": "Alpha", "description": "d"})
        assert dispatcher.dispatch("reindex", {"changed_only": True})["documents_indexed"] == 0
        assert dispatcher.dispatch("reindex", {})["documents_indexed"] == 1


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


def test_check_catches_tier0_violations_made_by_hand(
    dispatcher: Dispatcher, settings: Settings
) -> None:
    """A hand-edit that parses but breaks Tier 0 is now visible (issue-6817ed1851e2 groundwork).

    `check` caught `malformed`, `duplicate-id`, `dangling` and `unknown-type`,
    but a hand-edited tag or status parsed cleanly and passed silently — the
    document stayed queryable by a tag the registry had never heard of. Both are
    rules the CLI enforces on every write, so either one means the file was
    edited outside it, which is the whole premise of `reindex`.
    """
    dispatcher.dispatch("add", {"type": "decision", "title": "Alpha", "description": "d"})
    path = settings.docs_root / "decisions" / "adr-0001-alpha.md"
    path.write_text(
        path.read_text(encoding="utf-8")
        .replace("tags: []", "tags: [ghost]")
        .replace("status: proposed", "status: invented"),
        encoding="utf-8",
    )
    dispatcher.dispatch("reindex", {})

    kinds = {i["kind"] for i in dispatcher.dispatch("check", {})}
    assert "unknown-tag" in kinds
    assert "unknown-status" in kinds


class TestASchemaChangeThatMakesAFieldRequired:
    """The upgrade case: the rule changes, the documents do not (issue-8f6576cd7bc9).

    Every other Tier 1 classification finding needs a hand-edit or a merge to
    occur. This one does not: core and profile types are compiled into the
    package and re-merged on every command, so a release that adds a `required:`
    entry changes what an untouched store enforces. Before the check existed the
    corpus was silently non-conforming and the first report was a write being
    refused — `--set-title` failing on a field the caller never mentioned.

    Both halves are exercised against a real store: the schema is rewritten
    under documents that already exist, then a *new* container reads it, which
    is what an upgrade looks like from the store's side.
    """

    @staticmethod
    def _require_owner(settings: Settings) -> None:
        settings.schema_path.write_text(
            "types:\n"
            "  decision:\n"
            "    prefix: adr\n"
            "    required: [owner]\n"
            "    default_status: proposed\n"
            "    statuses:\n"
            "      proposed: [accepted]\n"
            "      accepted: []\n",
            encoding="utf-8",
        )

    def test_check_names_the_documents_the_new_rule_breaks(
        self, dispatcher: Dispatcher, settings: Settings
    ) -> None:
        dispatcher.dispatch("add", {"type": "decision", "title": "Before", "description": "d"})
        self._require_owner(settings)

        with closing(build_container(settings, background_embeddings=False)) as after:
            issues = after.dispatcher.dispatch("check", {})

        found = [i for i in issues if i["kind"] == "missing-required"]
        assert [tuple(i["doc_ids"]) for i in found] == [("adr-0001",)]
        assert "'owner'" in found[0]["message"]

    def test_it_reports_exactly_what_the_next_write_would_refuse(
        self, dispatcher: Dispatcher, settings: Settings
    ) -> None:
        # The claim the finding makes has to be the truth: the same document,
        # the same field, and a write that really is refused. If `check` and
        # Tier 0 ever disagree about "empty", this is what catches it.
        dispatcher.dispatch("add", {"type": "decision", "title": "Before", "description": "d"})
        self._require_owner(settings)

        with closing(build_container(settings, background_embeddings=False)) as after:
            reported = {
                i["doc_ids"][0]
                for i in after.dispatcher.dispatch("check", {})
                if i["kind"] == "missing-required"
            }
            with pytest.raises(MissingRequiredFieldError):
                after.dispatcher.dispatch("update", {"doc_id": "adr-0001", "set_title": "Renamed"})
            assert reported == {"adr-0001"}

    def test_supplying_the_field_clears_the_finding(
        self, dispatcher: Dispatcher, settings: Settings
    ) -> None:
        # The recovery the message names, end to end — and the guard that the
        # check goes quiet again, rather than reporting a document forever.
        dispatcher.dispatch("add", {"type": "decision", "title": "Before", "description": "d"})
        self._require_owner(settings)

        with closing(build_container(settings, background_embeddings=False)) as after:
            after.dispatcher.dispatch(
                "update", {"doc_id": "adr-0001", "set_owner": "platform-team"}
            )
            kinds = {i["kind"] for i in after.dispatcher.dispatch("check", {})}
        assert "missing-required" not in kinds

    def test_it_does_not_fail_the_ci_gate(self, dispatcher: Dispatcher, settings: Settings) -> None:
        # A warning, not an error. The change ships in the package, so `--strict`
        # would go red on a corpus nobody touched — how the gate became unusable
        # the first time.
        dispatcher.dispatch("add", {"type": "decision", "title": "Before", "description": "d"})
        self._require_owner(settings)

        with closing(build_container(settings, background_embeddings=False)) as after:
            issues = after.dispatcher.dispatch("check", {})
        assert all(i["severity"] == "warning" for i in issues if i["kind"] == "missing-required")


def test_a_healthy_corpus_reports_neither(dispatcher: Dispatcher) -> None:
    # The issue-9cb85759076d/issue-40d1792bc9f9 guard: a new check must stay quiet on correct usage.
    dispatcher.dispatch("tag_add", {"key": "auth", "description": "Auth."})
    dispatcher.dispatch(
        "add", {"type": "decision", "title": "A", "description": "d", "tags": ["auth"]}
    )
    kinds = {i["kind"] for i in dispatcher.dispatch("check", {})}
    assert "unknown-tag" not in kinds
    assert "unknown-status" not in kinds


def test_hand_edits_do_not_fail_the_ci_gate(dispatcher: Dispatcher, settings: Settings) -> None:
    # Warnings, not errors: they leave the document readable and every edge
    # resolvable. Promoting them would red-build every repo already carrying a
    # hand-edited tag, which is how --strict became unusable before.
    dispatcher.dispatch("add", {"type": "decision", "title": "Alpha", "description": "d"})
    path = settings.docs_root / "decisions" / "adr-0001-alpha.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("tags: []", "tags: [ghost]"), encoding="utf-8"
    )
    dispatcher.dispatch("reindex", {})
    assert all(
        i["severity"] == "warning"
        for i in dispatcher.dispatch("check", {})
        if i["kind"] in {"unknown-tag", "unknown-status"}
    )


class TestReindexReportsWhatItSkipped:
    """A partial rebuild must not look like a complete one (guards issue-5f979576ef7d).

    `scan` is best-effort by design — one unparseable file must not abort the
    rebuild of the rest — but `reindex` reported only what succeeded. On a fresh
    clone, where there is nothing in the index to remove, two files on disk and
    one indexed produced output that read as success, and the dropped document
    was absent from every read path. That is the exact scenario `reindex` exists
    for: rebuilding after a hand-edit or a merge.
    """

    @staticmethod
    def _corpus_with_one_bad_file(dispatcher: Dispatcher, settings: Settings) -> None:
        dispatcher.dispatch("add", {"type": "decision", "title": "Good", "description": "d"})
        (settings.docs_root / "decisions" / "adr-9999-bad.md").write_text(
            _MALFORMED_FILE, encoding="utf-8"
        )

    def test_skipped_files_are_counted(self, dispatcher: Dispatcher, settings: Settings) -> None:
        self._corpus_with_one_bad_file(dispatcher, settings)
        result = dispatcher.dispatch("reindex", {})
        assert result["documents_indexed"] == 1
        assert result["documents_skipped"] == 1

    def test_a_clean_corpus_reports_zero(self, dispatcher: Dispatcher) -> None:
        dispatcher.dispatch("add", {"type": "decision", "title": "Good", "description": "d"})
        assert dispatcher.dispatch("reindex", {})["documents_skipped"] == 0

    def test_the_count_survives_a_rebuild_from_nothing(
        self, dispatcher: Dispatcher, settings: Settings
    ) -> None:
        # The case with no signal at all before: nothing was in the index, so
        # `documents_removed` stayed 0 and only the (lower) indexed count moved.
        self._corpus_with_one_bad_file(dispatcher, settings)
        result = dispatcher.dispatch("reindex", {})
        assert result["documents_removed"] == 0
        assert result["documents_skipped"] == 1


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
# Guards issue-476b4e188fab: `check` reported four kinds of corrupt state and nothing could
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


def test_repair_drops_dead_edges(
    dispatcher: Dispatcher, settings: Settings, drop_file_of: Callable[[str], None]
) -> None:
    dispatcher.dispatch("add", {"type": "decision", "title": "Target", "description": "d"})
    dispatcher.dispatch(
        "add",
        {"type": "decision", "title": "Source", "description": "d", "related": ["adr-0001"]},
    )
    # A merge that removed the target's file — `delete --force` no longer leaves
    # this state behind, since it strips the edges it breaks (issue-fd547a293d01).
    drop_file_of("adr-0001")
    dispatcher.dispatch("reindex", {})
    assert any(i["kind"] == "dangling" for i in dispatcher.dispatch("check", {}))

    result = dispatcher.dispatch("repair", {})

    assert [a["kind"] for a in result["actions"]] == ["dangling"]
    assert not [i for i in result["remaining"] if i["kind"] == "dangling"]
    # Repaired in the canonical file, not just the index.
    source = settings.docs_root / "decisions" / "adr-0002-source.md"
    assert "adr-0001" not in source.read_text(encoding="utf-8")


def test_repair_does_not_reset_the_staleness_clock(
    dispatcher: Dispatcher, settings: Settings, drop_file_of: Callable[[str], None]
) -> None:
    # Dropping a dead link is maintenance, not a human re-reading the document.
    # Bumping `updated` would make an overdue doc look freshly reviewed.
    dispatcher.dispatch("add", {"type": "decision", "title": "Target", "description": "d"})
    dispatcher.dispatch(
        "add",
        {"type": "decision", "title": "Source", "description": "d", "related": ["adr-0001"]},
    )
    before = dispatcher.dispatch("get", {"doc_id": "adr-0002"})["updated"]
    drop_file_of("adr-0001")
    dispatcher.dispatch("reindex", {})

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


# -- the staleness worklist (issue-b4f441c7210f) ---------------------------------------
#
# Staleness was detected and never routed: `owner` was stored and interpolated
# into one `check` message, and there was no way to ask "what do I own?" or
# "what of it is overdue?". Detection without a queue meant a stale document
# stayed stale until someone happened to run `check` and read past the orphan
# warnings. These pin the queue.


def _write_decision(
    settings: Settings, doc_id: str, *, owner: str, updated: str, title: str
) -> None:
    decisions = settings.docs_root / "decisions"
    decisions.mkdir(parents=True, exist_ok=True)
    (decisions / f"{doc_id}-{title}.md").write_text(
        "---\n"
        f"created: '{updated}'\n"
        "description: a decision\n"
        f"id: {doc_id}\n"
        f"owner: {owner}\n"
        "related: []\n"
        "status: accepted\n"
        "tags: []\n"
        f"title: {title}\n"
        "type: decision\n"
        f"updated: '{updated}'\n"
        "---\n\nbody\n",
        encoding="utf-8",
    )


def _worklist_corpus(dispatcher: Dispatcher, settings: Settings) -> None:
    # Against the fixture clock (2026-07-07) and a 365-day cadence: adr-0001 is
    # overdue, adr-0002 is current, adr-0003 is overdue but someone else's.
    _write_decision(settings, "adr-0001", owner="platform-team", updated="2024-01-01", title="old")
    _write_decision(settings, "adr-0002", owner="platform-team", updated="2026-07-01", title="new")
    _write_decision(settings, "adr-0003", owner="data-team", updated="2024-01-01", title="theirs")
    dispatcher.dispatch("reindex", {})


def test_query_filters_by_owner(dispatcher: Dispatcher, settings: Settings) -> None:
    _worklist_corpus(dispatcher, settings)
    results = dispatcher.dispatch("query", {"owner": "platform-team"})
    assert {d["id"] for d in results} == {"adr-0001", "adr-0002"}


def test_query_filters_by_staleness(dispatcher: Dispatcher, settings: Settings) -> None:
    _worklist_corpus(dispatcher, settings)
    results = dispatcher.dispatch("query", {"stale": True})
    assert {d["id"] for d in results} == {"adr-0001", "adr-0003"}
    assert all(d["stale"] for d in results)


def test_owner_and_stale_compose_into_one_review_queue(
    dispatcher: Dispatcher, settings: Settings
) -> None:
    _worklist_corpus(dispatcher, settings)
    results = dispatcher.dispatch("query", {"owner": "platform-team", "stale": True})
    assert [d["id"] for d in results] == ["adr-0001"]


def test_stale_is_filtered_before_the_limit(dispatcher: Dispatcher, settings: Settings) -> None:
    # `--stale --limit 1` must mean "one stale document", not "the stale ones
    # among the first document". adr-0002 is the newest and sorts first, so a
    # limit applied before the filter would return nothing at all.
    _worklist_corpus(dispatcher, settings)
    results = dispatcher.dispatch("query", {"stale": True, "limit": 1})
    assert len(results) == 1
    assert results[0]["stale"] is True


def test_verifying_a_document_removes_it_from_the_queue(
    dispatcher: Dispatcher, settings: Settings
) -> None:
    # The loop closes: the queue is what `--verified` is for.
    _worklist_corpus(dispatcher, settings)
    dispatcher.dispatch("update", {"doc_id": "adr-0001", "mark_verified": True})
    results = dispatcher.dispatch("query", {"owner": "platform-team", "stale": True})
    assert results == []


def test_no_filters_still_returns_everything(dispatcher: Dispatcher, settings: Settings) -> None:
    _worklist_corpus(dispatcher, settings)
    assert len(dispatcher.dispatch("query", {})) == 3


class TestPagination:
    """List paths window in the query, not after it (guards issue-f6a5d0b86806).

    `query` fetched every match and sliced in Python, `tag list` had no window
    at all, and nothing stated a corpus ceiling. That is fine at a hundred
    documents and the wrong shape at ten thousand: the cost of a page should not
    grow with the corpus behind it.

    A page shorter than `limit` means the end. There is no total in the
    response — it is a bare JSON array, and a wrapper to carry one would break
    every existing caller.
    """

    @staticmethod
    def _decisions(dispatcher: Dispatcher, count: int) -> None:
        for i in range(count):
            dispatcher.dispatch(
                "add", {"type": "decision", "title": f"D{i}", "description": f"policy {i}"}
            )

    def test_query_pages_without_gaps_or_overlap(self, dispatcher: Dispatcher) -> None:
        self._decisions(dispatcher, 12)
        seen: list[str] = []
        for offset in (0, 5, 10):
            page = dispatcher.dispatch("query", {"limit": 5, "offset": offset})
            seen.extend(d["id"] for d in page)
        assert len(seen) == 12
        assert len(set(seen)) == 12

    def test_a_short_page_signals_the_end(self, dispatcher: Dispatcher) -> None:
        self._decisions(dispatcher, 12)
        assert len(dispatcher.dispatch("query", {"limit": 5, "offset": 10})) == 2
        assert dispatcher.dispatch("query", {"limit": 5, "offset": 12}) == []

    def test_tag_list_pages(self, dispatcher: Dispatcher) -> None:
        for i in range(7):
            dispatcher.dispatch("tag_add", {"key": f"tag-{i}", "description": "d"})
        first = dispatcher.dispatch("tag_list", {"limit": 3})
        second = dispatcher.dispatch("tag_list", {"limit": 3, "offset": 3})
        assert [t["key"] for t in first] == ["tag-0", "tag-1", "tag-2"]
        assert [t["key"] for t in second] == ["tag-3", "tag-4", "tag-5"]

    def test_search_pages(self, dispatcher: Dispatcher) -> None:
        self._decisions(dispatcher, 8)
        first = {d["id"] for d in dispatcher.dispatch("search", {"text": "policy", "limit": 4})}
        second = {
            d["id"]
            for d in dispatcher.dispatch("search", {"text": "policy", "limit": 4, "offset": 4})
        }
        assert len(first) == 4
        assert not (first & second)

    def test_stale_pages_over_the_filtered_set(
        self, dispatcher: Dispatcher, settings: Settings
    ) -> None:
        """`--stale` cannot use a SQL window, so it pages over the filter.

        Overdue documents are interleaved with fresh ones here: a window applied
        in SQL would count rows scanned rather than stale documents, which is
        the ordering bug issue-b4f441c7210f already fixed once for `--limit`.
        """
        decisions = settings.docs_root / "decisions"
        decisions.mkdir(parents=True, exist_ok=True)
        for i in range(1, 13):
            when = "2024-01-01" if i % 2 else "2026-07-07"
            (decisions / f"adr-{i:04d}-d{i}.md").write_text(
                f"---\ncreated: '{when}'\ndescription: d\nid: adr-{i:04d}\nrelated: []\n"
                f"status: accepted\ntags: []\ntitle: D{i}\ntype: decision\n"
                f"updated: '{when}'\n---\n\nbody\n",
                encoding="utf-8",
            )
        dispatcher.dispatch("reindex", {})

        everything = [d["id"] for d in dispatcher.dispatch("query", {"stale": True, "limit": 99})]
        paged: list[str] = []
        for offset in (0, 2, 4):
            paged.extend(
                d["id"]
                for d in dispatcher.dispatch("query", {"stale": True, "limit": 2, "offset": offset})
            )
        assert len(everything) == 6
        assert paged == everything

    def test_a_negative_offset_is_rejected(self, dispatcher: Dispatcher) -> None:
        # SQLite ignores a negative OFFSET, so it has to be caught before it.
        with pytest.raises(ValidationError):
            dispatcher.dispatch("query", {"limit": 5, "offset": -1})


def test_lint_does_not_flag_a_pair_that_is_related(dispatcher: Dispatcher) -> None:
    """issue-08437ba704ff, through the full stack: linking the pair clears the finding."""
    ids = []
    for title in ("Auth tokens one", "Auth tokens two"):
        ids.append(
            dispatcher.dispatch(
                "add",
                {
                    "type": "decision",
                    "title": title,
                    "description": "identical text about authentication tokens and refresh",
                    "body": "the same body about authentication tokens and refresh sessions",
                },
            )["id"]
        )
    assert any(f["kind"] == "duplicate" for f in dispatcher.dispatch("lint", {}))

    dispatcher.dispatch("update", {"doc_id": ids[0], "set_related": [ids[1]]})
    findings = dispatcher.dispatch("lint", {})
    assert [f for f in findings if f["kind"] == "duplicate"] == []
