"""The ``code`` field: the globs a document declares it governs.

Step 1 of issue-90aea6d1b891 — the data only. Tier 0 checks the *shape* of a
pattern and nothing about the working tree, because a decision is routinely
written before the code it decides and stays true after that code moves. The
"does this still match anything" question is Tier 1's and is not built here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from docir.config.settings import Settings
from docir.entry_points.composition import build_container
from docir.entry_points.dispatch import Dispatcher
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


def _repo_dispatcher(settings: Settings, tmp_path: Path):
    """A container whose store sits inside a git repository.

    Built here rather than through the shared fixture because the code matcher
    is resolved when the container is built: the repository has to exist first,
    which is also the real order — `docir init` runs inside a checkout.
    """
    (tmp_path / ".git").mkdir()
    settings.ensure_directories()
    return build_container(settings, background_embeddings=False)


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
