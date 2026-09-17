"""The ``code`` field: the globs a document declares it governs.

Step 1 of issue-90aea6d1b891 — the data only. Tier 0 checks the *shape* of a
pattern and nothing about the working tree, because a decision is routinely
written before the code it decides and stays true after that code moves. The
"does this still match anything" question is Tier 1's and is not built here.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from docir.config.settings import Settings
from docir.entry_points.composition import build_container
from docir.entry_points.dispatch import Dispatcher
from docir.platform.clock import Clock
from docir.platform.errors import InvalidCodeReferenceError


class TestWriteAndRead:
    def test_code_reaches_the_file_the_index_and_both_read_shapes(
        self, dispatcher: Dispatcher, settings: Settings
    ) -> None:
        view = dispatcher.dispatch(
            "add",
            {
                "type": "decision",
                "title": "SQLite is a derived index",
                "description": "The index is rebuildable from the files.",
                "code": ["src/docir/platform/persistence/**", "docs/*.md"],
                "body": "Body.",
            },
        )
        assert view["code"] == ("src/docir/platform/persistence/**", "docs/*.md")
        raw = (settings.docs_root / view["path"]).read_text(encoding="utf-8")
        assert "- src/docir/platform/persistence/**" in raw

        # Rebuilt from the files alone, the index still knows it: the field is
        # derived state like everything else in the index, not a write-only one.
        dispatcher.dispatch("reindex", {})
        assert set(dispatcher.dispatch("get", {"doc_id": view["id"]})["code"]) == {
            "src/docir/platform/persistence/**",
            "docs/*.md",
        }
        # And it rides on the skeleton, so "does this document concern the code
        # I am about to change" is answerable without fetching bodies.
        summary = dispatcher.dispatch("query", {"limit": 5})[0]
        assert "docs/*.md" in summary["code"]

    def test_a_document_governing_nothing_carries_no_code(
        self, dispatcher: Dispatcher, settings: Settings
    ) -> None:
        view = dispatcher.dispatch("add", {"type": "decision", "title": "T", "description": "d"})
        assert view["code"] == ()
        assert "code:" not in (settings.docs_root / view["path"]).read_text(encoding="utf-8")


class TestUpdate:
    def test_set_code_replaces_wholesale_and_an_empty_list_clears(
        self, dispatcher: Dispatcher
    ) -> None:
        view = dispatcher.dispatch(
            "add",
            {"type": "decision", "title": "T", "description": "d", "code": ["src/a/**"]},
        )
        replaced = dispatcher.dispatch(
            "update", {"doc_id": view["id"], "set_code": ["src/b/**", "src/c/**"]}
        )
        assert replaced["code"] == ("src/b/**", "src/c/**")
        cleared = dispatcher.dispatch("update", {"doc_id": view["id"], "set_code": []})
        assert cleared["code"] == ()

    def test_omitting_set_code_leaves_the_globs_alone(self, dispatcher: Dispatcher) -> None:
        # ``None`` means "unchanged" and ``[]`` means "clear" — the convention
        # set_tags/set_related already use. A title edit must not drop them.
        view = dispatcher.dispatch(
            "add",
            {"type": "decision", "title": "T", "description": "d", "code": ["src/a/**"]},
        )
        patched = dispatcher.dispatch("update", {"doc_id": view["id"], "set_title": "Renamed"})
        assert patched["code"] == ("src/a/**",)

    def test_a_document_that_round_tripped_through_the_index_is_not_diverged(
        self, dispatcher: Dispatcher
    ) -> None:
        # ``content_hash`` sorts the globs, because the file keeps the author's
        # order and the index returns them sorted. Unsorted, a reindexed
        # document would read as hand-edited and ``--replace-body`` — the one
        # mode the divergence guard blocks — would refuse a write that loses
        # nothing.
        view = dispatcher.dispatch(
            "add",
            {
                "type": "decision",
                "title": "T",
                "description": "d",
                "code": ["src/z/**", "src/a/**"],
            },
        )
        dispatcher.dispatch("reindex", {})
        rewritten = dispatcher.dispatch(
            "update", {"doc_id": view["id"], "replace_body": "new body", "force": True}
        )
        assert rewritten["body"] == "new body"


class TestTier0Shape:
    @pytest.mark.parametrize(
        ("pattern", "because"),
        [
            ("/etc/passwd", "absolute paths address a machine, not a repository"),
            ("../other-repo/**", "'..' escapes the repository the store belongs to"),
            ("src\\docir", "a backslash is a literal filename to every glob matcher"),
            ("   ", "an empty entry names nothing"),
        ],
    )
    def test_unusable_patterns_are_refused_on_write(
        self, dispatcher: Dispatcher, pattern: str, because: str
    ) -> None:
        with pytest.raises(InvalidCodeReferenceError):
            dispatcher.dispatch(
                "add",
                {"type": "decision", "title": "T", "description": "d", "code": [pattern]},
            )

    def test_update_is_guarded_too(self, dispatcher: Dispatcher) -> None:
        view = dispatcher.dispatch("add", {"type": "decision", "title": "T", "description": "d"})
        with pytest.raises(InvalidCodeReferenceError):
            dispatcher.dispatch("update", {"doc_id": view["id"], "set_code": ["/abs/path"]})

    def test_a_pattern_matching_nothing_is_accepted_at_write_time(
        self, dispatcher: Dispatcher
    ) -> None:
        # The deliberate non-check. A decision may land before the code it
        # governs, and code moves without the decision becoming false; making
        # this a write error would push authors to omit the field entirely,
        # which is the state this feature exists to leave.
        view = dispatcher.dispatch(
            "add",
            {
                "type": "decision",
                "title": "T",
                "description": "d",
                "code": ["src/not/written/yet/**"],
            },
        )
        assert view["code"] == ("src/not/written/yet/**",)


class _MovableClock(Clock):
    """A clock a test can push forward.

    The shared `FixedClock` cannot: a date that never moves makes "this write did
    not stamp `updated`" indistinguishable from "nothing could have stamped it",
    and `_repo_dispatcher` does not even take one, so its stores run on the wall
    clock and every date in a test is today either way. Both readings of the two
    clock tests below were unfalsifiable until this existed.
    """

    def __init__(self, day: date) -> None:
        self._day = day

    def today(self) -> date:
        return self._day

    def advance(self, days: int) -> None:
        self._day += timedelta(days=days)


def _repo_dispatcher(settings: Settings, tmp_path: Path, clock: Clock | None = None):
    """A container whose store sits inside a git repository.

    Built here rather than through the shared fixture because the code matcher
    is resolved when the container is built: the repository has to exist first,
    which is also the real order — `docir init` runs inside a checkout.
    """
    (tmp_path / ".git").mkdir()
    settings.ensure_directories()
    return build_container(settings, background_embeddings=False, clock=clock)


class TestTier1Check:
    """`docir check` reports a glob that no longer matches (step 2)."""

    def test_a_glob_that_matches_nothing_is_a_warning_and_a_matching_one_is_silent(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "auth.py").write_text("", encoding="utf-8")
        container = _repo_dispatcher(settings, tmp_path)
        try:
            docs = container.dispatcher
            live = docs.dispatch(
                "add",
                {"type": "decision", "title": "Live", "description": "d", "code": ["src/*.py"]},
            )
            gone = docs.dispatch(
                "add",
                {"type": "decision", "title": "Gone", "description": "d", "code": ["src/gone/**"]},
            )
            findings = [i for i in docs.dispatch("check", {}) if i["kind"] == "unmatched-code"]
            assert [i["doc_ids"] for i in findings] == [(gone["id"],)]
            assert live["id"] not in findings[0]["message"]
            # A warning, not an error: `check --strict` must stay green, since
            # the corpus is intact — a pattern is out of date, not broken.
            assert findings[0]["severity"] == "warning"
        finally:
            container.close()

    def test_the_check_is_skipped_when_the_store_has_no_repository(
        self, settings: Settings
    ) -> None:
        # The global-store case: nothing to resolve a repo-relative glob
        # against, so every pattern would read as missing. The shared
        # `dispatcher` fixture's store has no `.git` above it.
        settings.ensure_directories()
        container = build_container(settings, background_embeddings=False)
        try:
            docs = container.dispatcher
            docs.dispatch(
                "add",
                {"type": "decision", "title": "T", "description": "d", "code": ["src/gone/**"]},
            )
            assert not [i for i in docs.dispatch("check", {}) if i["kind"] == "unmatched-code"]
        finally:
            container.close()

    def test_check_fix_does_not_touch_it(self, settings: Settings, tmp_path: Path) -> None:
        # Nothing mechanical can repair this: only a human knows whether the
        # glob is stale or the document is. It must survive --fix and be
        # reported as remaining, like `malformed` and `unknown-type`.
        container = _repo_dispatcher(settings, tmp_path)
        try:
            docs = container.dispatcher
            docs.dispatch(
                "add",
                {"type": "decision", "title": "T", "description": "d", "code": ["src/gone/**"]},
            )
            result = docs.dispatch("repair", {})
            assert any(i["kind"] == "unmatched-code" for i in result["remaining"])
        finally:
            container.close()


class TestVerificationDigests:
    """`--verified` records what the code looked like; `check` reports it moving.

    The evidence half of staleness. Every test here injects the real defect —
    an edit to the governed file — rather than asserting the shape of a digest,
    because a fingerprint compared against itself agrees with itself.
    """

    def _governing(self, docs: Dispatcher, pattern: str, title: str = "Auth") -> str:
        view = docs.dispatch(
            "add", {"type": "decision", "title": title, "description": "d", "code": [pattern]}
        )
        return str(view["id"])

    def _findings(self, docs: Dispatcher) -> list[dict]:
        return [i for i in docs.dispatch("check", {}) if i["kind"] == "code-changed"]

    def test_an_edit_to_the_governed_code_is_reported_after_a_verification(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        source = tmp_path / "src" / "auth.py"
        source.parent.mkdir()
        source.write_text("def login():\n    return True\n", encoding="utf-8")
        container = _repo_dispatcher(settings, tmp_path)
        try:
            docs = container.dispatcher
            doc_id = self._governing(docs, "src/*.py")
            docs.dispatch("update", {"doc_id": doc_id, "mark_verified": True})
            # Verified against the code as it stands: nothing has moved yet.
            assert not self._findings(docs)

            source.write_text("def login(mfa: bool):\n    return 'token'\n", encoding="utf-8")
            findings = self._findings(docs)
            assert [i["doc_ids"] for i in findings] == [(doc_id,)]
            assert "src/*.py" in findings[0]["message"]
            # A warning: a branch that edits code before its docs is the ordinary
            # shape of a change, and failing its own CI is how a gate teaches
            # people to stop reading `docir check`.
            assert findings[0]["severity"] == "warning"
        finally:
            container.close()

    def test_the_evidence_survives_a_rebuilt_index(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        # The digest lives in the frontmatter, not only in the index — which is
        # what makes it visible to a teammate who clones the repo, where the
        # index is gitignored and has to be rebuilt from the files alone.
        source = tmp_path / "src" / "auth.py"
        source.parent.mkdir()
        source.write_text("original\n", encoding="utf-8")
        container = _repo_dispatcher(settings, tmp_path)
        try:
            docs = container.dispatcher
            doc_id = self._governing(docs, "src/*.py")
            docs.dispatch("update", {"doc_id": doc_id, "mark_verified": True})
            source.write_text("rewritten\n", encoding="utf-8")
            docs.dispatch("reindex", {})
            assert [i["doc_ids"] for i in self._findings(docs)] == [(doc_id,)]
        finally:
            container.close()

    def test_re_verifying_clears_it(self, settings: Settings, tmp_path: Path) -> None:
        source = tmp_path / "src" / "auth.py"
        source.parent.mkdir()
        source.write_text("original\n", encoding="utf-8")
        container = _repo_dispatcher(settings, tmp_path)
        try:
            docs = container.dispatcher
            doc_id = self._governing(docs, "src/*.py")
            docs.dispatch("update", {"doc_id": doc_id, "mark_verified": True})
            source.write_text("rewritten\n", encoding="utf-8")
            assert self._findings(docs)
            docs.dispatch("update", {"doc_id": doc_id, "mark_verified": True})
            assert not self._findings(docs)
        finally:
            container.close()

    def test_a_document_nobody_verified_reports_nothing(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        # Absent means unknown, never unchanged. Without this, every document
        # that governs code would report as changed from the moment it was
        # written — the `orphan`-on-a-healthy-corpus failure again.
        source = tmp_path / "src" / "auth.py"
        source.parent.mkdir()
        source.write_text("original\n", encoding="utf-8")
        container = _repo_dispatcher(settings, tmp_path)
        try:
            docs = container.dispatcher
            self._governing(docs, "src/*.py")
            source.write_text("rewritten\n", encoding="utf-8")
            assert not self._findings(docs)
        finally:
            container.close()

    def test_a_pattern_added_after_the_verification_is_unknown(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "auth.py").write_text("a\n", encoding="utf-8")
        (tmp_path / "src" / "later.py").write_text("b\n", encoding="utf-8")
        container = _repo_dispatcher(settings, tmp_path)
        try:
            docs = container.dispatcher
            doc_id = self._governing(docs, "src/auth.py")
            docs.dispatch("update", {"doc_id": doc_id, "mark_verified": True})
            docs.dispatch("update", {"doc_id": doc_id, "set_code": ["src/auth.py", "src/later.py"]})
            (tmp_path / "src" / "later.py").write_text("edited\n", encoding="utf-8")
            # The new glob was never verified, so its edit says nothing about
            # whether a human has read the document against it.
            assert not self._findings(docs)
        finally:
            container.close()

    def test_dropping_a_glob_drops_its_evidence(self, settings: Settings, tmp_path: Path) -> None:
        # Re-adding a pattern must not resurrect a digest recorded before it was
        # removed: the document was verified against a set that no longer
        # includes it, and a stale digest under a live pattern reports a change
        # nobody can date.
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "auth.py").write_text("a\n", encoding="utf-8")
        container = _repo_dispatcher(settings, tmp_path)
        try:
            docs = container.dispatcher
            doc_id = self._governing(docs, "src/auth.py")
            docs.dispatch("update", {"doc_id": doc_id, "mark_verified": True})
            docs.dispatch("update", {"doc_id": doc_id, "set_code": []})
            docs.dispatch("update", {"doc_id": doc_id, "set_code": ["src/auth.py"]})
            (tmp_path / "src" / "auth.py").write_text("edited\n", encoding="utf-8")
            assert not self._findings(docs)
        finally:
            container.close()

    def test_adding_a_file_under_a_directory_glob_counts_as_a_change(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        # The digest folds in each path beside its contents, so a file appearing
        # or disappearing registers even when nothing that survived was edited.
        pkg = tmp_path / "src" / "auth"
        pkg.mkdir(parents=True)
        (pkg / "login.py").write_text("a\n", encoding="utf-8")
        container = _repo_dispatcher(settings, tmp_path)
        try:
            docs = container.dispatcher
            doc_id = self._governing(docs, "src/auth/**")
            docs.dispatch("update", {"doc_id": doc_id, "mark_verified": True})
            (pkg / "mfa.py").write_text("b\n", encoding="utf-8")
            assert [i["doc_ids"] for i in self._findings(docs)] == [(doc_id,)]
        finally:
            container.close()

    def test_an_archived_document_is_skipped(self, settings: Settings, tmp_path: Path) -> None:
        source = tmp_path / "src" / "auth.py"
        source.parent.mkdir()
        source.write_text("original\n", encoding="utf-8")
        container = _repo_dispatcher(settings, tmp_path)
        try:
            docs = container.dispatcher
            doc_id = self._governing(docs, "src/*.py")
            docs.dispatch("update", {"doc_id": doc_id, "mark_verified": True})
            docs.dispatch("archive", {"doc_id": doc_id})
            source.write_text("rewritten\n", encoding="utf-8")
            assert not self._findings(docs)
        finally:
            container.close()

    def test_a_store_with_no_repository_records_no_evidence(
        self, dispatcher: Dispatcher, settings: Settings
    ) -> None:
        # The global-store case. There is no tree to fingerprint, so the
        # verification records a date and nothing else — rather than carrying
        # forward a digest from an older review under a fresh date.
        view = dispatcher.dispatch(
            "add", {"type": "decision", "title": "T", "description": "d", "code": ["src/a.py"]}
        )
        dispatcher.dispatch("update", {"doc_id": view["id"], "mark_verified": True})
        raw = (settings.docs_root / view["path"]).read_text(encoding="utf-8")
        assert "verified:" in raw
        assert "verified_code:" not in raw

    def test_a_verified_document_that_round_tripped_is_not_diverged(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        # ``content_hash`` covers the digests, so the index and the file must
        # agree about them after a rebuild. Unsorted or half-covered, a verified
        # document would read as hand-edited and `--replace-body` would refuse a
        # write that loses nothing.
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "auth.py").write_text("a\n", encoding="utf-8")
        (tmp_path / "src" / "user.py").write_text("b\n", encoding="utf-8")
        container = _repo_dispatcher(settings, tmp_path)
        try:
            docs = container.dispatcher
            view = docs.dispatch(
                "add",
                {
                    "type": "decision",
                    "title": "T",
                    "description": "d",
                    "code": ["src/user.py", "src/auth.py"],
                },
            )
            docs.dispatch("update", {"doc_id": view["id"], "mark_verified": True})
            docs.dispatch("reindex", {})
            rewritten = docs.dispatch(
                "update", {"doc_id": view["id"], "replace_body": "new body", "force": True}
            )
            assert rewritten["body"] == "new body"
        finally:
            container.close()

    def test_nothing_mechanical_repairs_it(self, settings: Settings, tmp_path: Path) -> None:
        # Only a human can say whether the document still describes the code —
        # which is precisely what re-verifying asserts. Like `unmatched-code`,
        # it survives --fix and is reported as remaining.
        source = tmp_path / "src" / "auth.py"
        source.parent.mkdir()
        source.write_text("original\n", encoding="utf-8")
        container = _repo_dispatcher(settings, tmp_path)
        try:
            docs = container.dispatcher
            doc_id = self._governing(docs, "src/*.py")
            docs.dispatch("update", {"doc_id": doc_id, "mark_verified": True})
            source.write_text("rewritten\n", encoding="utf-8")
            result = docs.dispatch("repair", {})
            assert any(i["kind"] == "code-changed" for i in result["remaining"])
        finally:
            container.close()


class TestCodeBaseline:
    """The authorship half: a glob is watched from the moment it is declared.

    `code-changed` needs a verification to exist, and in docir's own store not one
    of the 99 governed documents had ever been verified, so every glob named its
    code and nothing watched it. Every test here injects the real
    defect (an edit to the governed file) on a document nobody has verified,
    which is the case the older check reports nothing for.
    """

    def _governing(self, docs: Dispatcher, *patterns: str, title: str = "Auth") -> str:
        view = docs.dispatch(
            "add",
            {"type": "decision", "title": title, "description": "d", "code": list(patterns)},
        )
        return str(view["id"])

    def _drifted(self, docs: Dispatcher) -> list[dict]:
        return [i for i in docs.dispatch("check", {}) if i["kind"] == "code-drifted"]

    def test_an_edit_is_reported_on_a_document_nobody_ever_verified(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        source = tmp_path / "src" / "auth.py"
        source.parent.mkdir()
        source.write_text("def login():\n    return True\n", encoding="utf-8")
        container = _repo_dispatcher(settings, tmp_path)
        try:
            docs = container.dispatcher
            doc_id = self._governing(docs, "src/*.py")
            # Born watched, and the tree has not moved: silence.
            assert not self._drifted(docs)

            source.write_text("def login(mfa: bool):\n    return 'token'\n", encoding="utf-8")
            findings = self._drifted(docs)
            assert [i["doc_ids"] for i in findings] == [(doc_id,)]
            assert "src/*.py" in findings[0]["message"]
            # A warning, for the reason `code-changed` is one: editing code
            # before its documentation is the ordinary shape of a change.
            assert findings[0]["severity"] == "warning"
        finally:
            container.close()

    def test_a_pattern_that_was_verified_is_reported_once_and_as_code_changed(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        source = tmp_path / "src" / "auth.py"
        source.parent.mkdir()
        source.write_text("original\n", encoding="utf-8")
        container = _repo_dispatcher(settings, tmp_path)
        try:
            docs = container.dispatcher
            doc_id = self._governing(docs, "src/*.py")
            docs.dispatch("update", {"doc_id": doc_id, "mark_verified": True})
            source.write_text("rewritten\n", encoding="utf-8")

            kinds = [
                i["kind"]
                for i in docs.dispatch("check", {})
                if i["kind"] in {"code-changed", "code-drifted"}
            ]
            # One moved file, one sentence about it: the two checks partition
            # the patterns rather than both claiming this one.
            assert kinds == ["code-changed"]
            assert doc_id
        finally:
            container.close()

    def test_a_document_carrying_both_reports_each_pattern_under_its_own_kind(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "auth.py").write_text("a\n", encoding="utf-8")
        (src / "billing.py").write_text("b\n", encoding="utf-8")
        container = _repo_dispatcher(settings, tmp_path)
        try:
            docs = container.dispatcher
            doc_id = self._governing(docs, "src/auth.py")
            docs.dispatch("update", {"doc_id": doc_id, "mark_verified": True})
            # Added after the verification, so it carries a baseline and no
            # verified digest — the split this test is about.
            docs.dispatch(
                "update",
                {"doc_id": doc_id, "set_code": ["src/auth.py", "src/billing.py"]},
            )
            (src / "auth.py").write_text("a2\n", encoding="utf-8")
            (src / "billing.py").write_text("b2\n", encoding="utf-8")

            by_kind = {
                i["kind"]: i["message"]
                for i in docs.dispatch("check", {})
                if i["kind"] in {"code-changed", "code-drifted"}
            }
            assert set(by_kind) == {"code-changed", "code-drifted"}
            assert "src/auth.py" in by_kind["code-changed"]
            assert "src/billing.py" not in by_kind["code-changed"]
            assert "src/billing.py" in by_kind["code-drifted"]
            assert "src/auth.py" not in by_kind["code-drifted"]
        finally:
            container.close()

    def test_re_declaring_the_same_glob_does_not_clear_a_drift_nobody_read(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        # The laundering guard. `--set-code` is mechanical and needs no reading,
        # so re-basing a surviving pattern would let any write silence the
        # finding — the cheapest possible door onto what adr-bd7c4f3c5764
        # forbids.
        src = tmp_path / "src"
        src.mkdir()
        (src / "auth.py").write_text("original\n", encoding="utf-8")
        container = _repo_dispatcher(settings, tmp_path)
        try:
            docs = container.dispatcher
            doc_id = self._governing(docs, "src/auth.py")
            (src / "auth.py").write_text("rewritten\n", encoding="utf-8")
            assert self._drifted(docs)

            (src / "billing.py").write_text("b\n", encoding="utf-8")
            docs.dispatch(
                "update", {"doc_id": doc_id, "set_code": ["src/auth.py", "src/billing.py"]}
            )
            findings = self._drifted(docs)
            assert [i["doc_ids"] for i in findings] == [(doc_id,)]
            assert "src/auth.py" in findings[0]["message"]
            # The glob that arrived with this write is based by it, so it is
            # not swept into the same finding.
            assert "src/billing.py" not in findings[0]["message"]
        finally:
            container.close()

    def test_verifying_rebases_and_the_next_edit_is_reported_as_code_changed(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        source = tmp_path / "src" / "auth.py"
        source.parent.mkdir()
        source.write_text("original\n", encoding="utf-8")
        container = _repo_dispatcher(settings, tmp_path)
        try:
            docs = container.dispatcher
            doc_id = self._governing(docs, "src/*.py")
            source.write_text("rewritten\n", encoding="utf-8")
            assert self._drifted(docs)

            # Somebody read it against the code as it now stands.
            docs.dispatch("update", {"doc_id": doc_id, "mark_verified": True})
            assert not self._drifted(docs)
            assert not [i for i in docs.dispatch("check", {}) if i["kind"] == "code-changed"]

            source.write_text("rewritten again\n", encoding="utf-8")
            assert [i["kind"] for i in docs.dispatch("check", {}) if "code-" in i["kind"]] == [
                "code-changed"
            ]
        finally:
            container.close()

    def test_a_dropped_glob_takes_its_baseline_out_of_the_file(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "auth.py").write_text("a\n", encoding="utf-8")
        container = _repo_dispatcher(settings, tmp_path)
        try:
            docs = container.dispatcher
            doc_id = self._governing(docs, "src/auth.py")
            view = docs.dispatch("update", {"doc_id": doc_id, "set_code": []})
            raw = (settings.docs_root / view["path"]).read_text(encoding="utf-8")
            assert "code_baseline" not in raw
        finally:
            container.close()

    def test_the_baseline_round_trips_through_a_rebuild(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        # The index is derived and gitignored, so the baseline has to survive
        # being thrown away and rebuilt from the file alone.
        source = tmp_path / "src" / "auth.py"
        source.parent.mkdir()
        source.write_text("original\n", encoding="utf-8")
        container = _repo_dispatcher(settings, tmp_path)
        try:
            docs = container.dispatcher
            doc_id = self._governing(docs, "src/*.py")
            source.write_text("rewritten\n", encoding="utf-8")
            docs.dispatch("reindex", {})
            assert [i["doc_ids"] for i in self._drifted(docs)] == [(doc_id,)]
        finally:
            container.close()

    def test_declaring_a_glob_stamps_updated_and_leaves_the_review_clock(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        """`--set-code` moves `updated` and moves nothing staleness reads.

        The two are separate clocks and this is the write that shows it.
        `updated` is stamped by every flag `update` carries, because the
        mechanical-rewrite rule governs the writes nobody asked for — a tag
        rename, `check --fix` — not an edit somebody typed. The review clock
        runs from `verified`, else `revoked`, else `created`, and never reads
        `updated` at all (adr-fad49eaa4648), so a fresh stamp cannot buy a
        document another cadence.

        Both halves need a clock that moves. An earlier version asserted
        `updated` was unchanged and passed for the wrong reason: the store ran
        on the wall clock, so both reads returned today whatever the write did —
        and the assertion it made was false besides.
        """
        src = tmp_path / "src"
        src.mkdir()
        (src / "auth.py").write_text("a\n", encoding="utf-8")
        clock = _MovableClock(date(2026, 1, 1))
        container = _repo_dispatcher(settings, tmp_path, clock)
        try:
            docs = container.dispatcher
            doc_id = self._governing(docs, "src/auth.py")
            created = docs.dispatch("get", {"doc_id": doc_id})["created"]

            # Past the `decision` cadence, so staleness has an answer to give.
            clock.advance(400)
            docs.dispatch("update", {"doc_id": doc_id, "set_code": ["src/auth.py"]})

            after = docs.dispatch("get", {"doc_id": doc_id})
            assert after["updated"] == "2027-02-05"
            assert after["created"] == created
            # The document is overdue on the day it was declared overdue: the
            # cadence still runs from `created`, not from the stamp just made.
            assert after["stale"] is True
            assert after["verified"] is None
        finally:
            container.close()

    def test_a_store_with_no_repository_records_nothing_to_watch(self, settings: Settings) -> None:
        # The global-store case: no tree above the store, so there is nothing to
        # fingerprint and the key must not appear at all.
        settings.ensure_directories()
        container = build_container(settings, background_embeddings=False)
        try:
            docs = container.dispatcher
            view = docs.dispatch(
                "add",
                {"type": "decision", "title": "T", "description": "d", "code": ["src/**"]},
            )
            raw = (settings.docs_root / view["path"]).read_text(encoding="utf-8")
            assert "code_baseline" not in raw
            assert not [i for i in docs.dispatch("check", {}) if i["kind"] == "code-drifted"]
        finally:
            container.close()


class TestBackfillingTheBaseline:
    """`check --fix` starts watching globs declared before baselines existed.

    Not a repair of damage: the document is intact and reports nothing, which is
    the problem. Every test here works from a file with the key stripped, which
    is what a document looks like in both ways it can lose one: written by a
    build that predates the field, or rewritten by one — an older `render`
    writes the fields it knows and drops the rest. Measured, not assumed: 0.26.0
    reads a store carrying the key with nothing skipped, and removes it on the
    next write it makes. So this is the recovery path, not a one-time migration.
    """

    def _unwatched(self, settings: Settings, docs: Dispatcher, pattern: str) -> tuple[str, Path]:
        """A document governing ``pattern`` whose file carries no baseline."""
        view = docs.dispatch(
            "add", {"type": "decision", "title": "Auth", "description": "d", "code": [pattern]}
        )
        path = settings.docs_root / view["path"]
        stripped = [
            line
            for line in path.read_text(encoding="utf-8").splitlines(keepends=True)
            if "code_baseline" not in line and not line.startswith("  src/")
        ]
        path.write_text("".join(stripped), encoding="utf-8")
        docs.dispatch("reindex", {})
        return str(view["id"]), path

    def test_a_document_written_without_one_is_invisible_until_fix_runs(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        source = tmp_path / "src" / "auth.py"
        source.parent.mkdir()
        source.write_text("original\n", encoding="utf-8")
        container = _repo_dispatcher(settings, tmp_path)
        try:
            docs = container.dispatcher
            doc_id, path = self._unwatched(settings, docs, "src/*.py")
            source.write_text("rewritten\n", encoding="utf-8")
            # The defect this whole change is about: the glob names the code,
            # the code moved, and nothing says so.
            assert not [i for i in docs.dispatch("check", {}) if i["kind"] == "code-drifted"]

            result = docs.dispatch("repair", {})
            minted = [a for a in result["actions"] if a["kind"] == "code-baseline"]
            assert [a["doc_ids"] for a in minted] == [(doc_id,)]
            assert "src/*.py" in minted[0]["message"]
            assert "code_baseline" in path.read_text(encoding="utf-8")

            # Watched from here, not from when the glob was declared: the edit
            # that already happened stays unreported, the next one does not.
            assert not [i for i in docs.dispatch("check", {}) if i["kind"] == "code-drifted"]
            source.write_text("rewritten again\n", encoding="utf-8")
            assert [
                i["doc_ids"] for i in docs.dispatch("check", {}) if i["kind"] == "code-drifted"
            ] == [(doc_id,)]
        finally:
            container.close()

    def test_a_second_run_changes_nothing(self, settings: Settings, tmp_path: Path) -> None:
        source = tmp_path / "src" / "auth.py"
        source.parent.mkdir()
        source.write_text("original\n", encoding="utf-8")
        container = _repo_dispatcher(settings, tmp_path)
        try:
            docs = container.dispatcher
            self._unwatched(settings, docs, "src/*.py")
            assert [
                a for a in docs.dispatch("repair", {})["actions"] if a["kind"] == "code-baseline"
            ]
            assert not [
                a for a in docs.dispatch("repair", {})["actions"] if a["kind"] == "code-baseline"
            ]
        finally:
            container.close()

    def test_the_backfill_does_not_move_updated(self, settings: Settings, tmp_path: Path) -> None:
        """`check --fix` is a write nobody asked for, so it stamps nothing.

        This is the half of the rule `--set-code` is exempt from: an edit
        somebody typed may move `updated`, a repair may not, or a run of the
        maintenance command would relabel the whole corpus as freshly edited.

        The clock is advanced between the write and the repair, because with a
        frozen one — or the wall clock `_repo_dispatcher` used to hand out —
        "did not move" and "could not have moved" read identically.
        """
        source = tmp_path / "src" / "auth.py"
        source.parent.mkdir()
        source.write_text("original\n", encoding="utf-8")
        clock = _MovableClock(date(2026, 1, 1))
        container = _repo_dispatcher(settings, tmp_path, clock)
        try:
            docs = container.dispatcher
            doc_id, _ = self._unwatched(settings, docs, "src/*.py")
            before = docs.dispatch("get", {"doc_id": doc_id})["updated"]
            assert before == "2026-01-01"

            clock.advance(400)
            actions = docs.dispatch("repair", {})["actions"]
            assert [a for a in actions if a["kind"] == "code-baseline"], "nothing was filed"
            assert docs.dispatch("get", {"doc_id": doc_id})["updated"] == before
        finally:
            container.close()

    def test_it_never_mints_a_verification(self, settings: Settings, tmp_path: Path) -> None:
        # The line `--fix` may not cross: a baseline says what the tree held,
        # never that somebody read it. A repair that filed `verified_code`
        # would make the review clock a side effect of running a command.
        source = tmp_path / "src" / "auth.py"
        source.parent.mkdir()
        source.write_text("original\n", encoding="utf-8")
        container = _repo_dispatcher(settings, tmp_path)
        try:
            docs = container.dispatcher
            doc_id, path = self._unwatched(settings, docs, "src/*.py")
            docs.dispatch("repair", {})
            raw = path.read_text(encoding="utf-8")
            assert "verified_code" not in raw
            assert "verified:" not in raw
            assert docs.dispatch("get", {"doc_id": doc_id})["verified"] is None
        finally:
            container.close()


class TestQueryByPath:
    """`query --code <path>` — which documents govern this file (step 3)."""

    def _corpus(self, dispatcher: Dispatcher) -> dict[str, str]:
        return {
            "auth": dispatcher.dispatch(
                "add",
                {
                    "type": "decision",
                    "title": "Auth",
                    "description": "d",
                    "code": ["src/auth/**"],
                },
            )["id"],
            "dir": dispatcher.dispatch(
                "add",
                {"type": "decision", "title": "Dir", "description": "d", "code": ["src/api"]},
            )["id"],
            "none": dispatcher.dispatch(
                "add", {"type": "decision", "title": "None", "description": "d"}
            )["id"],
        }

    def test_a_path_finds_the_documents_governing_it(self, dispatcher: Dispatcher) -> None:
        ids = self._corpus(dispatcher)
        hits = dispatcher.dispatch("query", {"code": ["src/auth/login.py"]})
        assert [hit["id"] for hit in hits] == [ids["auth"]]

    def test_a_document_governing_a_directory_governs_what_is_in_it(
        self, dispatcher: Dispatcher
    ) -> None:
        # `src/api` is a directory, and the file inside it is what someone is
        # editing when they ask the question.
        ids = self._corpus(dispatcher)
        hits = dispatcher.dispatch("query", {"code": ["src/api/routes.py"]})
        assert [hit["id"] for hit in hits] == [ids["dir"]]

    def test_several_paths_are_matched_as_any_of(self, dispatcher: Dispatcher) -> None:
        # The shape of the real use: the files a branch touched.
        ids = self._corpus(dispatcher)
        hits = dispatcher.dispatch(
            "query", {"code": ["src/auth/login.py", "src/api/routes.py", "README.md"]}
        )
        assert {hit["id"] for hit in hits} == {ids["auth"], ids["dir"]}

    def test_a_deleted_path_still_finds_its_documents(
        self, dispatcher: Dispatcher, settings: Settings
    ) -> None:
        # The case that decides the whole design: matching is textual, not a
        # filesystem walk, because the branch that *removes* code is exactly
        # when its decisions must be re-read.
        ids = self._corpus(dispatcher)
        assert not (settings.home.parent / "src" / "auth").exists()
        hits = dispatcher.dispatch("query", {"code": ["src/auth/deleted.py"]})
        assert [hit["id"] for hit in hits] == [ids["auth"]]

    def test_a_path_nobody_governs_returns_nothing(self, dispatcher: Dispatcher) -> None:
        self._corpus(dispatcher)
        assert dispatcher.dispatch("query", {"code": ["docs/README.md"]}) == []

    def test_the_filter_runs_before_the_limit(self, dispatcher: Dispatcher) -> None:
        # `--code --limit 1` means one governing document, not "the governing
        # ones among the first document" — the ordering bug `--stale` already
        # fixed once (issue-b4f441c7210f).
        for index in range(6):
            dispatcher.dispatch(
                "add", {"type": "decision", "title": f"Filler {index}", "description": "d"}
            )
        governing = dispatcher.dispatch(
            "add",
            {"type": "decision", "title": "Auth", "description": "d", "code": ["src/auth/**"]},
        )["id"]
        hits = dispatcher.dispatch("query", {"code": ["src/auth/login.py"], "limit": 1})
        assert [hit["id"] for hit in hits] == [governing]

    def test_it_composes_with_the_other_filters(self, dispatcher: Dispatcher) -> None:
        # Both post-SQL predicates and a SQL one in the same call: all must
        # narrow, which is why they are combined into a single test.
        dispatcher.dispatch(
            "add",
            {
                "type": "decision",
                "title": "Owned",
                "description": "d",
                "code": ["src/auth/**"],
                "owner": "platform",
            },
        )
        dispatcher.dispatch(
            "add",
            {
                "type": "decision",
                "title": "Someone else's",
                "description": "d",
                "code": ["src/auth/**"],
                "owner": "other",
            },
        )
        hits = dispatcher.dispatch("query", {"code": ["src/auth/login.py"], "owner": "platform"})
        assert [hit["title"] for hit in hits] == ["Owned"]
