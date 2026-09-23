"""Tests for the multi-branch merge-safety features.

#2 collision-resistant ids (id_style: random) and #3 the merge-guard checks
(duplicate ids from files, dangling relations from the graph).
"""

from __future__ import annotations

import re
from collections.abc import Callable

import pytest

from docir.config.settings import Settings
from docir.entry_points.composition import build_container
from docir.entry_points.dispatch import Dispatcher
from docir.platform.errors import DuplicateDocumentIdError, ValidationError

RANDOM_SCHEMA = """\
types:
  decision:
    prefix: adr
    default_status: proposed
    id_style: random
    statuses:
      proposed: [accepted]
      accepted: []
"""

_DUP_FILE = (
    "---\n"
    "created: '2026-07-07'\n"
    "description: a colliding doc from another branch\n"
    "id: adr-0001\n"
    "related: []\n"
    "status: proposed\n"
    "tags: []\n"
    "title: Collision\n"
    "type: decision\n"
    "updated: '2026-07-07'\n"
    "---\n\nbody\n"
)


def test_random_ids_are_unique_and_collision_safe(settings: Settings) -> None:
    settings.ensure_directories()
    settings.schema_path.write_text(RANDOM_SCHEMA, encoding="utf-8")
    container = build_container(settings, background_embeddings=False)
    try:
        docs = container.dispatcher
        ids = [
            docs.dispatch("add", {"type": "decision", "title": f"T{i}", "description": "x"})["id"]
            for i in range(25)
        ]
        assert len(set(ids)) == 25  # no collisions
        assert all(re.fullmatch(r"adr-[0-9a-f]{12}", doc_id) for doc_id in ids)
    finally:
        container.close()


def test_check_detects_duplicate_id_from_merged_file(container, settings: Settings) -> None:
    docs = container.dispatcher
    docs.dispatch("add", {"type": "decision", "title": "Original", "description": "d"})
    # Simulate a merge bringing a second file that reused the same id.
    dup = settings.docs_root / "decisions" / "adr-0001-collision.md"
    dup.write_text(_DUP_FILE, encoding="utf-8")

    issues = docs.dispatch("check", {})
    assert any(i["kind"] == "duplicate-id" for i in issues)


def test_reindex_restores_the_id_counter(container, settings: Settings) -> None:
    # Guards issue-b7ddde3ce860: the counter lives in the derived index, which is gitignored.
    # A fresh clone therefore reindexes from files alone; before this fix the next
    # add re-minted a live id, and the older document fell out of every read path.
    docs = container.dispatcher
    docs.dispatch("add", {"type": "decision", "title": "First", "description": "d"})
    docs.dispatch("add", {"type": "decision", "title": "Second", "description": "d"})

    # Wipe only the derived index, exactly as a clone would arrive.
    with container.engine.connect() as conn:
        conn.exec_driver_sql("DELETE FROM id_sequences")
        conn.exec_driver_sql("DELETE FROM documents")
        conn.commit()

    docs.dispatch("reindex", {})
    third = docs.dispatch("add", {"type": "decision", "title": "Third", "description": "d"})

    assert third["id"] == "adr-0003"
    assert {issue["kind"] for issue in docs.dispatch("check", {})}.isdisjoint({"duplicate-id"})
    titles = {doc["title"] for doc in docs.dispatch("query", {})}
    assert titles == {"First", "Second", "Third"}  # nothing became invisible


def test_reindex_never_rewinds_the_counter(container) -> None:
    # Deleting the highest-numbered document must not free its id for reuse.
    docs = container.dispatcher
    docs.dispatch("add", {"type": "decision", "title": "First", "description": "d"})
    docs.dispatch("add", {"type": "decision", "title": "Second", "description": "d"})
    docs.dispatch("delete", {"doc_id": "adr-0002", "force": True})

    docs.dispatch("reindex", {})

    assert (
        docs.dispatch("add", {"type": "decision", "title": "Next", "description": "d"})["id"]
        == "adr-0003"
    )


def _doc_file(doc_id: str, title: str) -> str:
    return (
        "---\n"
        "created: '2026-07-07'\n"
        "description: d\n"
        f"id: {doc_id}\n"
        "related: []\n"
        "status: proposed\n"
        "tags: []\n"
        f"title: {title}\n"
        "type: decision\n"
        "updated: '2026-07-07'\n"
        "---\n\nbody\n"
    )


def test_reindex_ignores_random_ids_when_restoring_the_counter(settings: Settings) -> None:
    # Guards issue-f09fab3f5c36. Hex digits include the decimal digits, so ~1 random token in
    # 281 is all-digits and parses as a valid (huge) sequential number. Restoring
    # the counter from it would push the next sequential id to eleven digits.
    settings.ensure_directories()
    settings.schema_path.write_text(RANDOM_SCHEMA, encoding="utf-8")
    decisions = settings.docs_root / "decisions"
    decisions.mkdir(parents=True, exist_ok=True)
    (decisions / "adr-012345678901-all-digits.md").write_text(
        _doc_file("adr-012345678901", "All digits"), encoding="utf-8"
    )

    container = build_container(settings, background_embeddings=False)
    try:
        container.dispatcher.dispatch("reindex", {})
    finally:
        container.close()

    # Switch the type to sequential; the counter must still start from scratch.
    settings.schema_path.write_text(
        RANDOM_SCHEMA.replace("    id_style: random\n", ""), encoding="utf-8"
    )
    container = build_container(settings, background_embeddings=False)
    try:
        added = container.dispatcher.dispatch(
            "add", {"type": "decision", "title": "Next", "description": "d"}
        )
    finally:
        container.close()
    assert added["id"] == "adr-0001"


def test_reindex_still_restores_the_counter_for_sequential_types(settings: Settings) -> None:
    # The guard above must not disarm the issue-b7ddde3ce860 fix for genuine sequential ids.
    settings.ensure_directories()
    decisions = settings.docs_root / "decisions"
    decisions.mkdir(parents=True, exist_ok=True)
    (decisions / "adr-0007-seven.md").write_text(_doc_file("adr-0007", "Seven"), encoding="utf-8")

    container = build_container(settings, background_embeddings=False)
    try:
        container.dispatcher.dispatch("reindex", {})
        added = container.dispatcher.dispatch(
            "add", {"type": "decision", "title": "Next", "description": "d"}
        )
    finally:
        container.close()
    assert added["id"] == "adr-0008"


def test_add_refuses_to_clobber_a_file_owning_the_allocated_id(
    container, settings: Settings
) -> None:
    # Last line of defence: if the counter is behind the files for any reason,
    # the create fails loudly instead of silently overwriting a document.
    docs = container.dispatcher
    docs.dispatch("add", {"type": "decision", "title": "Original", "description": "d"})
    with container.engine.connect() as conn:
        conn.exec_driver_sql("DELETE FROM id_sequences")
        conn.exec_driver_sql("DELETE FROM documents")
        conn.commit()

    with pytest.raises(DuplicateDocumentIdError):
        docs.dispatch("add", {"type": "decision", "title": "Colliding", "description": "d"})

    # The original survives and no second file claimed its id — a differing title
    # slug must not let the collision through on a different path.
    files = sorted(p.name for p in (settings.docs_root / "decisions").glob("adr-0001-*.md"))
    assert files == ["adr-0001-original.md"]
    assert "Original" in (settings.docs_root / "decisions" / files[0]).read_text(encoding="utf-8")


def test_check_detects_dangling_reference(
    seeded: Dispatcher, drop_file_of: Callable[[str], None]
) -> None:
    # issue-0001 relates to adr-0001. Remove adr-0001's file the way a merge
    # from a branch that deleted it would, then reindex: issue-0001's own file
    # still names an id no file provides.
    #
    # This used `delete --force` before, which no longer produces the state —
    # that command now strips the edges it breaks (issue-fd547a293d01). A dangling edge is
    # now only reachable from outside the CLI, which is where it always came
    # from in practice.
    drop_file_of("adr-0001")
    seeded.dispatch("reindex", {})
    issues = seeded.dispatch("check", {})
    assert any(i["kind"] == "dangling" for i in issues)


class TestDeleteRefusesAnAmbiguousId:
    """`delete` on an id two files claim refuses, `--force` included (GitHub #27).

    Every step of the delete reads the index, which holds one row per id — the
    last file in sorted path order, because `reindex` upserts as it walks. So
    the command acted on a file nobody chose, stripped the edge from documents
    citing the file it was *not* deleting, and left the survivor with no index
    row: invisible to `get`, `query` and `context`, while `check --strict`
    exited 0 because the duplicate scan then found one file.

    None of that is findable afterwards. `related: []` is a valid state and the
    index half heals on the next `reindex`, so these tests are the only place
    the behaviour is pinned.
    """

    def _collided(self, docs: Dispatcher, settings: Settings) -> tuple[str, str]:
        """Two files claiming `adr-0001`, and a third document citing it."""
        original = docs.dispatch(
            "add", {"type": "decision", "title": "Established", "description": "d"}
        )
        citer = docs.dispatch(
            "add",
            {
                "type": "decision",
                "title": "Citer",
                "description": "d",
                "related": [str(original["id"])],
            },
        )
        # Sorts *before* the established file, so the index resolves the id to
        # the established one and the delete would act on that: the survivor is
        # the copy, and the citer's edge points at neither in particular.
        dup = settings.docs_root / "decisions" / "adr-0001-aaa-copy.md"
        dup.write_text(_DUP_FILE, encoding="utf-8")
        docs.dispatch("reindex", {})
        return str(original["id"]), str(citer["id"])

    def test_it_refuses_and_names_every_file_that_claims_the_id(
        self, container, settings: Settings
    ) -> None:
        docs = container.dispatcher
        doc_id, _ = self._collided(docs, settings)

        with pytest.raises(DuplicateDocumentIdError) as excinfo:
            docs.dispatch("delete", {"doc_id": doc_id})

        message = str(excinfo.value)
        # Which files, not just how many — the repair is a choice between them,
        # and a count cannot be acted on.
        assert "decisions/adr-0001-aaa-copy.md" in message
        assert "decisions/adr-0001-established.md" in message
        assert "check --fix" in message

    def test_force_does_not_override_it(self, container, settings: Settings) -> None:
        """`--force` overrides incoming references, not which document is meant.

        This is the whole decision: the flag exists to say "strip the edges
        anyway", and the edges it would strip here cannot be told apart by id.
        """
        docs = container.dispatcher
        doc_id, _ = self._collided(docs, settings)

        with pytest.raises(DuplicateDocumentIdError):
            docs.dispatch("delete", {"doc_id": doc_id, "force": True})

    def test_nothing_is_deleted_rewritten_or_dropped_from_the_index(
        self, container, settings: Settings
    ) -> None:
        """The three defects, asserted as state rather than as an exception.

        A refusal that had already written something would still pass the two
        tests above.
        """
        docs = container.dispatcher
        doc_id, citer_id = self._collided(docs, settings)
        decisions = settings.docs_root / "decisions"
        before = sorted(path.name for path in decisions.glob("*.md"))

        with pytest.raises(DuplicateDocumentIdError):
            docs.dispatch("delete", {"doc_id": doc_id, "force": True})

        assert sorted(path.name for path in decisions.glob("*.md")) == before
        assert [ref["target"] for ref in docs.dispatch("get", {"doc_id": citer_id})["related"]] == [
            doc_id
        ]
        assert docs.dispatch("get", {"doc_id": doc_id})["id"] == doc_id
        assert any(i["kind"] == "duplicate-id" for i in docs.dispatch("check", {}))

    def test_an_ordinary_delete_is_untouched(self, container) -> None:
        """The half that makes the rest mean something.

        A guard that refused every delete would pass all three tests above.
        """
        docs = container.dispatcher
        view = docs.dispatch("add", {"type": "decision", "title": "Alone", "description": "d"})
        doc_id = str(view["id"])

        assert docs.dispatch("delete", {"doc_id": doc_id}) == {"deleted": doc_id, "unlinked": []}

    def test_a_forced_delete_still_strips_edges_when_the_id_is_unambiguous(self, container) -> None:
        # The behaviour adr-3cfa867c8537 deliberately keeps: --force still
        # overrides incoming references, which is what it was built for.
        docs = container.dispatcher
        target = docs.dispatch("add", {"type": "decision", "title": "Target", "description": "d"})
        citer = docs.dispatch(
            "add",
            {
                "type": "decision",
                "title": "Citer",
                "description": "d",
                "related": [str(target["id"])],
            },
        )

        result = docs.dispatch("delete", {"doc_id": str(target["id"]), "force": True})

        assert result["unlinked"] == [str(citer["id"])]
        assert not docs.dispatch("get", {"doc_id": str(citer["id"])})["related"]


class TestAdoptingAnExistingId:
    """`add --id` preserves a numbered corpus (guards issue-20933967697b).

    A repository adopting docir with ADR-007..ADR-042 lost every number, and so
    every historical cross-reference; the documented workaround was to keep a
    mapping by hand and rewrite the references afterwards.

    This is deliberately *not* the bulk `import` that was built and rejected.
    That command inferred type, title and status and reported success over input
    it had mangled. An adopted id is not inferred — the caller reads it off the
    file and states it, one document at a time, after reviewing the file.
    """

    def test_the_supplied_id_is_used(self, dispatcher: Dispatcher) -> None:
        view = dispatcher.dispatch(
            "add",
            {"type": "decision", "title": "Use Postgres", "description": "d", "id": "adr-0007"},
        )
        assert view["id"] == "adr-0007"

    def test_the_next_allocation_lands_past_it(self, dispatcher: Dispatcher) -> None:
        # Without raising the counter this minted adr-0001 — safe, since the
        # generator skips indexed ids, but not what adopting a corpus implies,
        # and only corrected by the next reindex.
        dispatcher.dispatch(
            "add", {"type": "decision", "title": "Seven", "description": "d", "id": "adr-0007"}
        )
        following = dispatcher.dispatch(
            "add", {"type": "decision", "title": "Next", "description": "d"}
        )
        assert following["id"] == "adr-0008"

    def test_an_id_already_in_use_is_refused(self, dispatcher: Dispatcher) -> None:
        dispatcher.dispatch(
            "add", {"type": "decision", "title": "First", "description": "d", "id": "adr-0007"}
        )
        with pytest.raises(DuplicateDocumentIdError):
            dispatcher.dispatch(
                "add",
                {"type": "decision", "title": "Clash", "description": "d", "id": "adr-0007"},
            )

    def test_a_prefix_that_does_not_match_the_type_is_refused(self, dispatcher: Dispatcher) -> None:
        # The prefix encodes the type; letting them disagree would break that.
        with pytest.raises(ValidationError):
            dispatcher.dispatch(
                "add",
                {"type": "decision", "title": "Wrong", "description": "d", "id": "issue-0001"},
            )

    def test_a_malformed_id_is_refused(self, dispatcher: Dispatcher) -> None:
        with pytest.raises(ValidationError):
            dispatcher.dispatch(
                "add", {"type": "decision", "title": "Bad", "description": "d", "id": "ADR 7"}
            )

    def test_allocation_is_unchanged_without_the_flag(self, dispatcher: Dispatcher) -> None:
        view = dispatcher.dispatch("add", {"type": "decision", "title": "A", "description": "d"})
        assert view["id"] == "adr-0001"
