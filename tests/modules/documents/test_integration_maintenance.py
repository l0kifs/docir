"""Integration tests for reindex, check (Tier 1), lint (Tier 2), embed flush."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import closing

import pytest

from docir import __version__
from docir.config.settings import Settings
from docir.entry_points.composition import Container, build_container
from docir.entry_points.dispatch import Dispatcher
from docir.platform.errors import (
    DocumentNotFoundError,
    MissingRequiredFieldError,
    UnknownRelationKindError,
    ValidationError,
)
from docir.platform.persistence.unit_of_work import UnitOfWork

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


class TestARebuildIsHowVectorsAreRecomputed:
    """There is no "recompute the vectors too" mode, and none is needed.

    `reindex --embeddings` returned before the rebuild, so it recomputed exactly
    the vectors a rebuild recomputes anyway and wrote neither the schema
    baseline nor the build stamp — the 0.14.0 upgrade note told people to run it
    (adr-6a4718fa7a7d, issue-b24e14474820).
    """

    def test_a_rebuild_reports_the_documents_it_re_embedded(self, seeded: Dispatcher) -> None:
        # It always re-embedded them and never said so, which is what made a
        # separate flag look necessary. The count is documents, not vectors —
        # the queue is keyed by document, and each writes one per `##` section
        # as well as its own.
        assert seeded.dispatch("reindex", {})["embeddings_recomputed"] >= 1

    def test_vectors_written_is_the_real_vector_count(
        self, dispatcher: Dispatcher, settings: Settings
    ) -> None:
        """The document count could not say why a rebuild takes a minute.

        Embedding is ~96% of a rebuild and is linear in *vectors*, so reporting
        315 documents for 1,326 vectors understated the work 4x — and the line
        used to call that number "vectors" outright. Asserted against the rows
        actually in the index rather than against `1 + len(sections)` recomputed
        here, which would only prove the arithmetic agrees with itself.
        """
        dispatcher.dispatch(
            "add",
            {
                "type": "decision",
                "title": "Sectioned",
                "description": "d",
                "body": "## One\n\nalpha\n\n## Two\n\nbeta\n\n## Three\n\ngamma",
            },
        )
        result = dispatcher.dispatch("reindex", {})
        with closing(sqlite3.connect(settings.db_path)) as conn:
            stored = (
                conn.execute("SELECT COUNT(*) FROM embeddings WHERE vector IS NOT NULL").fetchone()[
                    0
                ]
                + conn.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0]
            )
        assert result["vectors_written"] == stored
        assert result["vectors_written"] > result["embeddings_recomputed"]

    def test_changed_re_embeds_nothing_when_nothing_moved(self, seeded: Dispatcher) -> None:
        seeded.dispatch("reindex", {})
        result = seeded.dispatch("reindex", {"changed_only": True})
        assert result["documents_indexed"] == 0
        assert result["embeddings_recomputed"] == 0

    def test_a_leftover_embeddings_key_is_not_a_second_mode(self, seeded: Dispatcher) -> None:
        # A caller still sending the retired key gets the rebuild, not the
        # stamp-skipping path it used to select.
        seeded.dispatch("reindex", {})
        result = seeded.dispatch("reindex", {"changed_only": True, "embeddings": True})
        assert result["documents_indexed"] == 0
        assert result["embeddings_recomputed"] == 0


class TestResyncRebuildsOnlyWhenTheBuildMoved:
    """`docir self upgrade` paid for a full re-embed of an unchanged corpus.

    A full pass re-embeds every document it re-saves, which measured 58.4 s
    against 1.5 s for the changed pass on a 315-document store — 96% of the
    command, recomputing vectors byte-identical to the ones already indexed.
    The build stamp is the only thing that separates "the reader moved under
    these documents" from "nothing to do", so `resync` reads it *before* the
    rebuild: both modes write it, so a cheap pass would erase the evidence.
    """

    @staticmethod
    def _stamp(uow_factory: Callable[[], UnitOfWork], version: str) -> None:
        with uow_factory() as uow:
            uow.index_build.set(version)
            uow.commit()

    def test_a_store_this_build_indexed_is_not_rebuilt(self, seeded: Dispatcher) -> None:
        seeded.dispatch("reindex", {})  # stamps the running version
        result = seeded.dispatch("reindex", {"resync": True})
        assert result["documents_indexed"] == 0
        assert result["embeddings_recomputed"] == 0

    def test_another_version_forces_the_full_rebuild(
        self, seeded: Dispatcher, uow_factory: Callable[[], UnitOfWork]
    ) -> None:
        seeded.dispatch("reindex", {})
        self._stamp(uow_factory, "0.0.1")
        result = seeded.dispatch("reindex", {"resync": True})
        assert result["documents_indexed"] >= 1
        assert result["embeddings_recomputed"] >= 1

    def test_a_downgrade_rebuilds_too(
        self, seeded: Dispatcher, uow_factory: Callable[[], UnitOfWork]
    ) -> None:
        # Equality, not "older than" — the same rule `stale-index-build` uses.
        seeded.dispatch("reindex", {})
        self._stamp(uow_factory, "99.0.0")
        assert seeded.dispatch("reindex", {"resync": True})["documents_indexed"] >= 1

    def test_an_absent_stamp_rebuilds(
        self, seeded: Dispatcher, uow_factory: Callable[[], UnitOfWork]
    ) -> None:
        """Unknown means rebuild here, the opposite of what `check` does with it.

        `check` folds "never recorded" into silence because absent means unknown
        and a finding nobody can act on is noise. This decision cannot borrow
        that reading: a store with no stamp was last built by code that did not
        write one, so its vectors are exactly the ones a full pass replaces.
        Routing through `stale_index_build()` — which returns `None` for both
        "this build" and "never recorded" — would skip the rebuild here.
        """
        with uow_factory() as uow:
            assert uow.index_build.get() is None
        assert seeded.dispatch("reindex", {"resync": True})["documents_indexed"] >= 1

    def test_it_still_stamps_and_leaves_check_quiet(
        self, seeded: Dispatcher, uow_factory: Callable[[], UnitOfWork]
    ) -> None:
        # The cheap path must not cost the store its stamp or its baseline —
        # that was the defect that retired `reindex --embeddings`.
        seeded.dispatch("reindex", {})
        seeded.dispatch("reindex", {"resync": True})
        with uow_factory() as uow:
            assert uow.index_build.get() == __version__
        kinds = {i["kind"] for i in seeded.dispatch("check", {})}
        assert "stale-index-build" not in kinds and "schema-drift" not in kinds


def test_repair_does_not_re_embed_untouched_documents(
    seeded: Dispatcher, container: Container, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`check --fix` reindexed in full first, so it paid the same ~60 s.

    Its rebuild is only there to make the index agree with the files before id
    allocation reads it, and `--changed` does that: the deletion sweep and the
    id-counter restore run in both modes.

    Counted at the embedder, not asserted through a later `reindex --changed`:
    that would report 0 whichever mode `repair` used — a full rebuild also
    leaves the index agreeing with the files — so it would hold with the defect
    reintroduced and prove nothing.
    """
    seeded.dispatch("reindex", {})  # index and vectors now current
    calls: list[str] = []
    embed = container.embedder.embed
    monkeypatch.setattr(
        container.embedder, "embed", lambda text: (calls.append(text), embed(text))[1]
    )

    seeded.dispatch("repair", {})

    assert calls == []


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


class TestTheSchemaChangingUnderTheStore:
    """`check` reports that the *rule* moved, not only its consequences (issue-d891ab5501e6).

    The schema's types and cadences come from the installed docir as much as
    from `docs-schema.yaml`, so an upgrade can change what a store enforces with
    no local edit and nothing in `git diff` to read. The baseline is the index's
    record of what it was built against; the diff against it is the review that
    was never possible.
    """

    @staticmethod
    def _rewrite_schema(settings: Settings, *, prefix: str = "adr") -> None:
        settings.schema_path.write_text(
            "types:\n"
            "  decision:\n"
            f"    prefix: {prefix}\n"
            "    required: [owner]\n"
            "    default_status: proposed\n"
            "    statuses:\n"
            "      proposed: [accepted]\n"
            "      accepted: []\n",
            encoding="utf-8",
        )

    def test_a_store_with_no_baseline_reports_nothing(self, dispatcher: Dispatcher) -> None:
        # Absent means unknown, not unchanged. A store predating the baseline
        # table has nothing to compare against, and an empty baseline would
        # report the whole schema as newly added, once, on every store.
        dispatcher.dispatch("add", {"type": "decision", "title": "A", "description": "d"})
        assert dispatcher.dispatch("schema_drift", {})["drift"] == []

    def test_reindex_records_the_baseline_and_check_stays_quiet(
        self, dispatcher: Dispatcher
    ) -> None:
        dispatcher.dispatch("add", {"type": "decision", "title": "A", "description": "d"})
        dispatcher.dispatch("reindex", {})
        assert dispatcher.dispatch("schema_drift", {})["drift"] == []
        kinds = {i["kind"] for i in dispatcher.dispatch("check", {})}
        assert "schema-drift" not in kinds

    def test_check_names_what_moved(self, dispatcher: Dispatcher, settings: Settings) -> None:
        dispatcher.dispatch("add", {"type": "decision", "title": "A", "description": "d"})
        dispatcher.dispatch("reindex", {})
        self._rewrite_schema(settings, prefix="dec")

        with closing(build_container(settings, background_embeddings=False)) as after:
            issues = after.dispatcher.dispatch("check", {})

        messages = [i["message"] for i in issues if i["kind"] == "schema-drift"]
        assert any("required [] -> ['owner']" in m for m in messages)
        assert any("prefix 'adr' -> 'dec'" in m for m in messages)

    def test_drift_is_a_warning_and_does_not_fail_the_ci_gate(
        self, dispatcher: Dispatcher, settings: Settings
    ) -> None:
        # The change ships in the package, so `--strict` going red would fail
        # every repo on the release that made it — the corpus is untouched and
        # it is the rule that moved.
        dispatcher.dispatch("add", {"type": "decision", "title": "A", "description": "d"})
        dispatcher.dispatch("reindex", {})
        self._rewrite_schema(settings)

        with closing(build_container(settings, background_embeddings=False)) as after:
            issues = after.dispatcher.dispatch("check", {})
        drift = [i for i in issues if i["kind"] == "schema-drift"]
        assert drift and all(i["severity"] == "warning" for i in drift)

    def test_reindex_clears_it(self, dispatcher: Dispatcher, settings: Settings) -> None:
        # The baseline advances on `reindex` and nowhere else: the existing
        # "resync derived state" verb, not a new acknowledgement ritual.
        dispatcher.dispatch("add", {"type": "decision", "title": "A", "description": "d"})
        dispatcher.dispatch("reindex", {})
        self._rewrite_schema(settings)

        with closing(build_container(settings, background_embeddings=False)) as after:
            assert after.dispatcher.dispatch("schema_drift", {})["drift"]
            after.dispatcher.dispatch("reindex", {})
            assert after.dispatcher.dispatch("schema_drift", {})["drift"] == []

    def test_the_drift_explains_the_findings_beside_it(
        self, dispatcher: Dispatcher, settings: Settings
    ) -> None:
        # The point of the cause being reported: `missing-required` on a
        # document nobody edited stops looking like it came from nowhere.
        dispatcher.dispatch("add", {"type": "decision", "title": "A", "description": "d"})
        dispatcher.dispatch("reindex", {})
        self._rewrite_schema(settings)

        with closing(build_container(settings, background_embeddings=False)) as after:
            kinds = {i["kind"] for i in after.dispatcher.dispatch("check", {})}
        assert {"schema-drift", "missing-required"} <= kinds


class TestAnIndexBuiltByCodeThatIsNoLongerInstalled:
    """`check` reports the *build*, which the schema baseline cannot see.

    The baseline compares two schemas, so it stays silent when a release changes
    how documents are read rather than what they must contain — chunked
    embeddings rewrote every vector in the index without touching a type, a
    status or a cadence. This is the finding that says "rebuild it" then.
    """

    @staticmethod
    def _pretend_an_older_docir_built_it(
        uow_factory: Callable[[], UnitOfWork], version: str = "0.0.1"
    ) -> None:
        with uow_factory() as uow:
            uow.index_build.set(version)
            uow.commit()

    def test_a_store_that_has_never_been_reindexed_reports_nothing(
        self, dispatcher: Dispatcher
    ) -> None:
        # Absent means unknown, not stale — the rule the schema baseline
        # follows. Otherwise every store fires this once, for nothing.
        dispatcher.dispatch("add", {"type": "decision", "title": "A", "description": "d"})
        kinds = {i["kind"] for i in dispatcher.dispatch("check", {})}
        assert "stale-index-build" not in kinds

    def test_reindex_stamps_the_running_version_and_check_stays_quiet(
        self, dispatcher: Dispatcher, uow_factory: Callable[[], UnitOfWork]
    ) -> None:
        dispatcher.dispatch("add", {"type": "decision", "title": "A", "description": "d"})
        dispatcher.dispatch("reindex", {})

        with uow_factory() as uow:
            assert uow.index_build.get() == __version__
        kinds = {i["kind"] for i in dispatcher.dispatch("check", {})}
        assert "stale-index-build" not in kinds

    def test_check_names_the_version_that_built_it(
        self, dispatcher: Dispatcher, uow_factory: Callable[[], UnitOfWork]
    ) -> None:
        dispatcher.dispatch("add", {"type": "decision", "title": "A", "description": "d"})
        dispatcher.dispatch("reindex", {})
        self._pretend_an_older_docir_built_it(uow_factory)

        findings = [i for i in dispatcher.dispatch("check", {}) if i["kind"] == "stale-index-build"]
        assert len(findings) == 1
        assert "0.0.1" in findings[0]["message"] and __version__ in findings[0]["message"]

    def test_it_is_a_warning_so_the_ci_gate_stays_green(
        self, dispatcher: Dispatcher, uow_factory: Callable[[], UnitOfWork]
    ) -> None:
        # Every store is in this state between an upgrade and the next rebuild;
        # failing the build for it would red-light every repo on release day.
        dispatcher.dispatch("add", {"type": "decision", "title": "A", "description": "d"})
        dispatcher.dispatch("reindex", {})
        self._pretend_an_older_docir_built_it(uow_factory)

        findings = [i for i in dispatcher.dispatch("check", {}) if i["kind"] == "stale-index-build"]
        assert findings and all(i["severity"] == "warning" for i in findings)

    def test_a_downgrade_reports_it_too(
        self, dispatcher: Dispatcher, uow_factory: Callable[[], UnitOfWork]
    ) -> None:
        # Inequality, not "older than": going back a version needs the same
        # rebuild, and ordering version strings is a question this avoids.
        dispatcher.dispatch("add", {"type": "decision", "title": "A", "description": "d"})
        dispatcher.dispatch("reindex", {})
        self._pretend_an_older_docir_built_it(uow_factory, version="99.0.0")

        kinds = {i["kind"] for i in dispatcher.dispatch("check", {})}
        assert "stale-index-build" in kinds

    def test_reindex_clears_it(
        self, dispatcher: Dispatcher, uow_factory: Callable[[], UnitOfWork]
    ) -> None:
        dispatcher.dispatch("add", {"type": "decision", "title": "A", "description": "d"})
        dispatcher.dispatch("reindex", {})
        self._pretend_an_older_docir_built_it(uow_factory)

        dispatcher.dispatch("reindex", {})
        kinds = {i["kind"] for i in dispatcher.dispatch("check", {})}
        assert "stale-index-build" not in kinds

    def test_no_reindex_payload_can_skip_the_stamp(
        self, dispatcher: Dispatcher, uow_factory: Callable[[], UnitOfWork]
    ) -> None:
        # One payload could: `embeddings` selected a path that recomputed
        # vectors and returned, so a store that had just been reindexed still
        # reported a stale build and read as if the command had failed
        # (issue-b24e14474820). The key is retired; sending it must not resurrect
        # that path.
        dispatcher.dispatch("add", {"type": "decision", "title": "A", "description": "d"})
        dispatcher.dispatch("reindex", {})
        self._pretend_an_older_docir_built_it(uow_factory)

        dispatcher.dispatch("reindex", {"embeddings": True})
        kinds = {i["kind"] for i in dispatcher.dispatch("check", {})}
        assert "stale-index-build" not in kinds


class TestAnEdgeWhoseKindTheRegistryStoppedListing:
    """`check` now reports it; before, only rewriting it was refused (issue-0e3d1d9c81d3).

    The asymmetry is what made this worth fixing: Tier 0 refuses to *write* the
    kind while every read path keeps serving it, so the corpus held a
    classification the schema had disowned and the one command that exists to
    find that was silent.
    """

    @staticmethod
    def _narrow_the_registry(settings: Settings) -> None:
        settings.schema_path.write_text(
            "relation_types: [relates_to, supersedes]\n"
            "types:\n"
            "  decision:\n"
            "    prefix: adr\n"
            "    default_status: proposed\n"
            "    statuses:\n"
            "      proposed: [accepted]\n"
            "      accepted: []\n"
            "  issue:\n"
            "    prefix: issue\n"
            "    default_status: open\n"
            "    statuses:\n"
            "      open: [resolved]\n"
            "      resolved: []\n",
            encoding="utf-8",
        )

    @staticmethod
    def _linked_pair(dispatcher: Dispatcher) -> None:
        dispatcher.dispatch("add", {"type": "decision", "title": "Target", "description": "d"})
        dispatcher.dispatch(
            "add",
            {
                "type": "issue",
                "title": "Source",
                "description": "d",
                "related": ["adr-0001:depends_on"],
            },
        )

    def test_check_names_the_edge(self, dispatcher: Dispatcher, settings: Settings) -> None:
        self._linked_pair(dispatcher)
        self._narrow_the_registry(settings)

        with closing(build_container(settings, background_embeddings=False)) as after:
            issues = after.dispatcher.dispatch("check", {})

        found = [i for i in issues if i["kind"] == "unknown-relation-kind"]
        assert [tuple(i["doc_ids"]) for i in found] == [("issue-0001", "adr-0001")]
        assert "'depends_on'" in found[0]["message"]

    def test_the_edge_still_reads_while_rewriting_it_is_refused(
        self, dispatcher: Dispatcher, settings: Settings
    ) -> None:
        # Both halves of the asymmetry, in one test: this is the state `check`
        # had no way to describe.
        self._linked_pair(dispatcher)
        self._narrow_the_registry(settings)

        with closing(build_container(settings, background_embeddings=False)) as after:
            view = after.dispatcher.dispatch("get", {"doc_id": "issue-0001"})
            assert [r["kind"] for r in view["related"]] == ["depends_on"]
            with pytest.raises(UnknownRelationKindError):
                after.dispatcher.dispatch(
                    "update", {"doc_id": "issue-0001", "set_related": ["adr-0001:depends_on"]}
                )

    def test_a_permissive_registry_reports_nothing(self, dispatcher: Dispatcher) -> None:
        # The shipped schema registers the core six, so the healthy corpus must
        # stay quiet — and a schema registering nothing at all is unconstrained
        # by construction, which is every schema predating typed edges.
        self._linked_pair(dispatcher)
        kinds = {i["kind"] for i in dispatcher.dispatch("check", {})}
        assert "unknown-relation-kind" not in kinds

    def test_it_does_not_fail_the_ci_gate(self, dispatcher: Dispatcher, settings: Settings) -> None:
        self._linked_pair(dispatcher)
        self._narrow_the_registry(settings)

        with closing(build_container(settings, background_embeddings=False)) as after:
            issues = after.dispatcher.dispatch("check", {})
        assert all(
            i["severity"] == "warning" for i in issues if i["kind"] == "unknown-relation-kind"
        )


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
