"""Tests for the multi-branch merge-safety features.

#2 collision-resistant ids (id_style: random) and #3 the merge-guard checks
(duplicate ids from files, dangling relations from the graph).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

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


def _git(root: Path, *args: str, when: int | None = None) -> None:
    """Run one git command in ``root`` with identity and time pinned.

    The time is pinned rather than left to the wall clock because the property
    under test is *ordering*, and two commits made in the same test run land in
    the same second.
    """
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com"}
    env["GIT_COMMITTER_NAME"] = env["GIT_AUTHOR_NAME"]
    env["GIT_COMMITTER_EMAIL"] = env["GIT_AUTHOR_EMAIL"]
    if when is not None:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = f"{when} +0000"
    subprocess.run(["git", "-C", str(root), *args], check=True, env=env, capture_output=True)


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git to read a base ref")
class TestThePreMergeCheck:
    """`check --against <ref>` asks before the merge instead of after.

    The collision exists from the moment the second branch allocates — the ids
    are on both sides — but nothing could see it until both documents were in
    one tree. By then renumbering has stopped being that branch's own cheap edit
    and become a conflict for whoever merged second (GitHub #22).
    """

    def _base(self, settings: Settings, tmp_path: Path) -> Dispatcher:
        """A committed base holding `adr-0001`, and a container over it."""
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
        settings.ensure_directories()
        container = build_container(settings, background_embeddings=False)
        self._containers.append(container)
        docs = container.dispatcher
        docs.dispatch("add", {"type": "decision", "title": "Established", "description": "d"})
        _git(tmp_path, "add", "-A", when=1_600_000_000)
        _git(tmp_path, "commit", "-q", "-m", "base", when=1_600_000_000)
        return docs

    @pytest.fixture(autouse=True)
    def _closing(self):
        self._containers: list = []
        yield
        for container in self._containers:
            container.close()

    def _kinds(self, docs: Dispatcher, **payload) -> list[str]:
        return [i["kind"] for i in docs.dispatch("check", payload)]

    def test_an_id_the_base_already_uses_is_an_error_before_the_merge(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        docs = self._base(settings, tmp_path)
        # This branch mints a *different* document onto the same id, exactly as
        # a second branch cut from the same base would.
        incoming = settings.docs_root / "decisions" / "adr-0001-incoming.md"
        incoming.write_text(_DUP_FILE, encoding="utf-8")
        (settings.docs_root / "decisions" / "adr-0001-established.md").unlink()
        docs.dispatch("reindex", {})

        findings = [
            i
            for i in docs.dispatch("check", {"against": "HEAD"})
            if i["kind"] == "branch-id-collision"
        ]

        assert [i["doc_ids"] for i in findings] == [("adr-0001",)]
        # Both sides named, because the repair is to renumber one of them.
        assert "decisions/adr-0001-incoming.md" in findings[0]["message"]
        assert "decisions/adr-0001-established.md" in findings[0]["message"]
        assert findings[0]["severity"] == "error"

    def test_a_document_the_base_already_has_is_not_a_collision(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        """The half that makes the test above mean something.

        A branch that *edits* an existing document keeps its id on both sides.
        Reporting that would fire on every branch that touches a document, which
        is every branch.
        """
        docs = self._base(settings, tmp_path)
        docs.dispatch("update", {"doc_id": "adr-0001", "description": "edited here"})

        assert "branch-id-collision" not in self._kinds(docs, against="HEAD")

    def test_a_new_id_the_base_does_not_use_is_not_a_collision(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        docs = self._base(settings, tmp_path)
        docs.dispatch("add", {"type": "decision", "title": "Fresh", "description": "d"})

        assert "branch-id-collision" not in self._kinds(docs, against="HEAD")

    def test_the_repair_the_finding_names_actually_clears_it(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        """Follow the shipped instruction and the branch comes out clean.

        The finding names `git merge <ref>` then `check --fix`, and it has to,
        because there is no renumber command — an id is a document's only
        address. The first draft of this message said `docir update <id>`, which
        cannot do it; nothing caught that until somebody ran the instructions.

        The merge is performed for real, not simulated by writing a file, and
        that is load-bearing: a merge *commits* both sides, which is what lets
        the git key separate them. Restoring the base's file without committing
        leaves one side untracked, git can say nothing about it, and `created`
        decides instead — an honest fallback, and not the workflow being
        documented here.
        """
        docs = self._base(settings, tmp_path)
        decisions = settings.docs_root / "decisions"
        base_file = decisions / "adr-0001-established.md"
        established = base_file.read_text(encoding="utf-8")

        # This branch: the base's document is gone and a different one holds
        # its id, which is what a branch cut before it and merged after looks
        # like from here.
        (decisions / "adr-0001-incoming.md").write_text(_DUP_FILE, encoding="utf-8")
        base_file.unlink()
        docs.dispatch("reindex", {})
        _git(tmp_path, "add", "-A", when=1_700_000_000)
        _git(tmp_path, "commit", "-q", "-m", "mine", when=1_700_000_000)
        assert "branch-id-collision" in self._kinds(docs, against="HEAD~1")

        # The repair the finding names: bring the base in, then `check --fix`.
        base_file.write_text(established, encoding="utf-8")
        _git(tmp_path, "add", "-A", when=1_800_000_000)
        _git(tmp_path, "commit", "-q", "-m", "merge the base", when=1_800_000_000)
        docs.dispatch("reindex", {})
        repaired = docs.dispatch("repair", {})

        # This branch's document moved; the base's kept the id, because the base
        # committed it first.
        assert [a["kind"] for a in repaired["actions"]] == ["duplicate-id"]
        assert "adr-0001-incoming.md" in repaired["actions"][0]["message"]
        assert base_file.exists()
        report = docs.dispatch("check", {"against": "HEAD~2"})
        assert "branch-id-collision" not in [i["kind"] for i in report], [
            i["message"] for i in report if i["kind"] == "branch-id-collision"
        ]

    def test_a_ref_that_cannot_be_read_is_an_error_not_silence(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        """The `empty-index` argument, one merge away.

        A pre-merge gate silent because it could not read the base ref is
        indistinguishable from a clean branch, which is the one outcome a gate
        must never produce.
        """
        docs = self._base(settings, tmp_path)

        findings = [
            i
            for i in docs.dispatch("check", {"against": "origin/nope"})
            if i["kind"] == "unreadable-ref"
        ]

        assert len(findings) == 1
        assert findings[0]["severity"] == "error"
        assert "origin/nope" in findings[0]["message"]

    def test_without_the_flag_nothing_compares(self, settings: Settings, tmp_path: Path) -> None:
        # The flag is the opt-in: no ref named, no ref read, and no finding that
        # could red-build a branch that never asked for the gate.
        docs = self._base(settings, tmp_path)
        incoming = settings.docs_root / "decisions" / "adr-0001-incoming.md"
        incoming.write_text(_DUP_FILE, encoding="utf-8")
        (settings.docs_root / "decisions" / "adr-0001-established.md").unlink()
        docs.dispatch("reindex", {})

        kinds = self._kinds(docs)

        assert "branch-id-collision" not in kinds
        assert "unreadable-ref" not in kinds

    def test_a_store_with_no_repository_says_so_rather_than_passing(
        self, container, settings: Settings
    ) -> None:
        """No `.git` above this store, so there is nothing to compare against.

        Silence would be the same lie as an unreadable ref.
        """
        docs = container.dispatcher
        docs.dispatch("add", {"type": "decision", "title": "T", "description": "d"})

        findings = [
            i
            for i in docs.dispatch("check", {"against": "origin/main"})
            if i["kind"] == "unreadable-ref"
        ]

        assert len(findings) == 1
        assert findings[0]["severity"] == "error"


class TestWhichDuplicateKeepsTheId:
    """`check --fix` decides by git provenance first (GitHub #22).

    The established document keeps the id because an existing `related` edge
    naming it was written against *some* document and cannot say which, so the
    one more readers have already cited is the one to leave alone.

    `created` was the documented intent and degrades exactly when it is needed:
    it is a `date`, so two branches cut from one base and merged inside a day
    are indistinguishable by it — which is the shape of nearly every real
    collision, and why the reporter saw "first by filename keeps the id".

    Every case here names the incoming file `aaa-...` and the established one
    `zzz-...`, so a filename tiebreak hands the id to the *wrong* document. That
    is what makes the assertions discriminate: any key that really looks at
    provenance has to overrule the alphabet.
    """

    def _survivor(self, docs: Dispatcher) -> tuple[str, str]:
        """The file that kept the id, and the message that said so."""
        actions = [a for a in docs.dispatch("repair", {})["actions"] if a["kind"] == "duplicate-id"]
        assert len(actions) == 1, actions
        message = actions[0]["message"]
        keeper = message.split("); ", 1)[1].split(" keeps the id", 1)[0]
        return keeper, message

    @pytest.mark.skipif(shutil.which("git") is None, reason="needs git to record provenance")
    def test_git_provenance_overrules_the_alphabet(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        """The established file keeps the id although its name sorts last.

        Both `created` dates are the fixture clock's, so nothing but git can
        separate them — which is the collision's real shape, and exactly where
        the old key fell through to the alphabet.
        """
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
        settings.ensure_directories()
        container = build_container(settings, background_embeddings=False)
        try:
            docs = container.dispatcher
            docs.dispatch(
                "add", {"type": "decision", "title": "Zzz established", "description": "d"}
            )
            _git(tmp_path, "add", "-A", when=1_600_000_000)
            _git(tmp_path, "commit", "-q", "-m", "established", when=1_600_000_000)

            incoming = settings.docs_root / "decisions" / "adr-0001-aaa-incoming.md"
            incoming.write_text(_DUP_FILE, encoding="utf-8")
            _git(tmp_path, "add", "-A", when=1_700_000_000)
            _git(tmp_path, "commit", "-q", "-m", "incoming", when=1_700_000_000)
            docs.dispatch("reindex", {})

            keeper, message = self._survivor(docs)

            assert keeper == "decisions/adr-0001-zzz-established.md"
            assert "first added to git" in message
        finally:
            container.close()

    def test_without_git_the_older_created_still_decides(
        self, container, settings: Settings
    ) -> None:
        """The documented intent, unchanged wherever it can still separate them.

        No repository above this store, so there is no history to read and the
        second key has to carry it — as it did before this change.
        """
        docs = container.dispatcher
        docs.dispatch("add", {"type": "decision", "title": "Zzz established", "description": "d"})
        incoming = settings.docs_root / "decisions" / "adr-0001-aaa-incoming.md"
        later = _DUP_FILE.replace("created: '2026-07-07'", "created: '2026-08-08'")
        incoming.write_text(later, encoding="utf-8")
        docs.dispatch("reindex", {})

        keeper, message = self._survivor(docs)

        assert keeper == "decisions/adr-0001-zzz-established.md"
        assert "oldest `created`" in message

    def test_a_filename_tiebreak_says_it_could_not_tell(
        self, container, settings: Settings
    ) -> None:
        """The case that used to be a silent coin flip.

        Nothing separates the two, so the alphabet decides — as it always did.
        What is new is that the repair says so, because a filename tiebreak is a
        statement that docir could not tell, and only the operator knows whether
        the survivor is the document their readers cited.
        """
        docs = container.dispatcher
        docs.dispatch("add", {"type": "decision", "title": "Zzz established", "description": "d"})
        incoming = settings.docs_root / "decisions" / "adr-0001-aaa-incoming.md"
        incoming.write_text(_DUP_FILE, encoding="utf-8")
        docs.dispatch("reindex", {})

        keeper, message = self._survivor(docs)

        assert keeper == "decisions/adr-0001-aaa-incoming.md"
        assert "filename order" in message
        assert "check this is the one your readers cited" in message


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
