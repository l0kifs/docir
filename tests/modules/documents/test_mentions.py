"""The derived mention graph: ids one document's body names in another.

`related:` is the authored graph — typed, hand-written, and the thing every
structural check polices. Mentions are inferred from prose and exist to answer
one question the authored graph answered badly: *is this document connected to
anything?* `orphan` fired for every document whose author had linked it by
writing its id in a sentence, which is how most people link.

Half of these tests are about what mentions must **not** do. The derived graph
shares a corpus with the authored one, and every check that reads `related`
would be wrong to read this: a cycle nobody wrote is noise, and a delete refused
because a paragraph quotes an id is a corpus nobody can maintain.
"""

from __future__ import annotations

import pytest

from docir.config.settings import Settings
from docir.entry_points.dispatch import Dispatcher
from docir.platform.errors import DocirError
from docir.platform.naming import scan_document_ids


class TestScanner:
    """`scan_document_ids` — the grammar, in isolation."""

    def test_it_finds_ids_for_the_declared_prefixes_only(self) -> None:
        # The prefix set is what makes scanning free text safe. Without it any
        # hyphenated word with a hex tail is an id, and `sha-1beef` in a
        # sentence about hashing would link to a document that never existed.
        text = "See adr-1cfb1b212237 and issue-0001, but sha-1beef is a hash."
        assert scan_document_ids(text, {"adr", "issue"}) == ("adr-1cfb1b212237", "issue-0001")

    def test_it_deduplicates_and_sorts(self) -> None:
        # A set of edges, not a reading order: a body naming one id three times
        # is one edge, and a stable order stops a rebuild rewriting rows that
        # did not change.
        text = "issue-0002 then adr-0001 then issue-0002 again"
        assert scan_document_ids(text, {"adr", "issue"}) == ("adr-0001", "issue-0002")

    def test_a_fenced_code_block_still_names_documents(self) -> None:
        # Unlike headings, where a `##` inside a fence is a comment. An id in an
        # example command is naming that document as surely as a sentence is.
        text = "Run it:\n\n```bash\ndocir get adr-1cfb1b212237\n```\n"
        assert scan_document_ids(text, {"adr"}) == ("adr-1cfb1b212237",)

    @pytest.mark.parametrize(
        ("text", "because"),
        [
            ("adr-xyz", "the suffix is not hex"),
            ("adr-1b", "the suffix is shorter than the id grammar allows"),
            ("xadr-1beef", "the prefix is not one the schema declares"),
            ("ADR-1BEEF", "ids are lowercase"),
        ],
    )
    def test_near_misses_are_not_ids(self, text: str, because: str) -> None:
        assert scan_document_ids(text, {"adr"}) == ()

    def test_no_prefixes_means_no_mentions(self) -> None:
        # A store with no types cannot be mentioning anything. Guards the empty
        # alternation, which would compile to a pattern matching everything.
        assert scan_document_ids("adr-1cfb1b212237", set()) == ()


class TestOrphans:
    """The finding this exists to fix."""

    def _linked_in_prose(self, dispatcher: Dispatcher) -> tuple[str, str]:
        target = dispatcher.dispatch(
            "add", {"type": "decision", "title": "Tokens", "description": "d", "body": "Chosen."}
        )["id"]
        source = dispatcher.dispatch(
            "add",
            {
                "type": "issue",
                "title": "Login is slow",
                "description": "d",
                "body": f"Profiling points at the path chosen in {target}.",
            },
        )["id"]
        return str(source), str(target)

    def _orphans(self, dispatcher: Dispatcher) -> set[str]:
        return {
            issue["doc_ids"][0]
            for issue in dispatcher.dispatch("check", {})
            if issue["kind"] == "orphan"
        }

    def test_naming_a_document_in_prose_connects_both(self, dispatcher: Dispatcher) -> None:
        source, target = self._linked_in_prose(dispatcher)
        assert self._orphans(dispatcher) == set()
        # And the link really is prose-only: neither file gained an edge.
        assert dispatcher.dispatch("get", {"doc_id": source})["related"] == ()
        assert dispatcher.dispatch("get", {"doc_id": target})["related"] == ()

    def test_a_document_nobody_names_is_still_an_orphan(self, dispatcher: Dispatcher) -> None:
        # The finding has to keep working, or this change traded a false
        # positive for a check that reports nothing at all.
        alone = dispatcher.dispatch(
            "add", {"type": "decision", "title": "Alone", "description": "d", "body": "Nothing."}
        )["id"]
        assert alone in self._orphans(dispatcher)

    def test_naming_an_id_that_does_not_exist_connects_nothing(
        self, dispatcher: Dispatcher
    ) -> None:
        # Only resolved pairs count. A typo, or a document deleted since, is not
        # a connection to anything — and must not silence the finding.
        alone = dispatcher.dispatch(
            "add",
            {
                "type": "decision",
                "title": "Alone",
                "description": "d",
                "body": "As decided in adr-deadbeefcafe.",
            },
        )["id"]
        assert alone in self._orphans(dispatcher)

    def test_a_self_mention_is_not_a_link(self, dispatcher: Dispatcher) -> None:
        # A document restating its own id is describing itself. Counting it
        # would make every document non-orphan the moment it quoted its id.
        created = dispatcher.dispatch(
            "add", {"type": "decision", "title": "T", "description": "d", "body": "x"}
        )["id"]
        dispatcher.dispatch(
            "update", {"doc_id": created, "replace_body": f"I am {created}.", "force": True}
        )
        assert created in self._orphans(dispatcher)

    def test_removing_the_id_from_the_body_restores_the_finding(
        self, dispatcher: Dispatcher
    ) -> None:
        source, target = self._linked_in_prose(dispatcher)
        dispatcher.dispatch(
            "update", {"doc_id": source, "replace_body": "Nothing points anywhere.", "force": True}
        )
        assert self._orphans(dispatcher) == {source, target}


class TestDerivedNotAuthored:
    """What the derived graph must never do to the authored one."""

    def test_it_never_reaches_the_file(self, dispatcher: Dispatcher, settings: Settings) -> None:
        target = dispatcher.dispatch(
            "add", {"type": "decision", "title": "T", "description": "d", "body": "x"}
        )["id"]
        view = dispatcher.dispatch(
            "add",
            {"type": "issue", "title": "I", "description": "d", "body": f"See {target}."},
        )
        raw = (settings.docs_root / view["path"]).read_text(encoding="utf-8")
        assert "related: []" in raw
        assert "mentions" not in raw

    def test_a_mention_does_not_block_a_delete(self, dispatcher: Dispatcher) -> None:
        # `related` blocks a delete so the graph cannot be left dangling. Prose
        # cannot dangle — the text stays true either way — and refusing here
        # would make any quoted id permanent.
        target = dispatcher.dispatch(
            "add", {"type": "decision", "title": "T", "description": "d", "body": "x"}
        )["id"]
        dispatcher.dispatch(
            "add", {"type": "issue", "title": "I", "description": "d", "body": f"See {target}."}
        )
        assert dispatcher.dispatch("delete", {"doc_id": target}) is not None

    def test_a_mention_of_a_missing_document_is_not_dangling(self, dispatcher: Dispatcher) -> None:
        # `dangling` is an *error* and gates a merge. A body naming an id that
        # does not resolve is ordinary — an ADR referencing the issue it will
        # produce — so it must never reach that check.
        dispatcher.dispatch(
            "add",
            {
                "type": "decision",
                "title": "T",
                "description": "d",
                "body": "Supersedes adr-deadbeefcafe.",
            },
        )
        kinds = {issue["kind"] for issue in dispatcher.dispatch("check", {})}
        assert "dangling" not in kinds

    def test_two_documents_naming_each_other_are_not_a_cycle(self, dispatcher: Dispatcher) -> None:
        # Mutual citation is how prose works. `cycle` fires on the authored
        # graph, where direction was asserted deliberately.
        first = dispatcher.dispatch(
            "add", {"type": "decision", "title": "A", "description": "d", "body": "x"}
        )["id"]
        second = dispatcher.dispatch(
            "add", {"type": "decision", "title": "B", "description": "d", "body": f"See {first}."}
        )["id"]
        dispatcher.dispatch(
            "update", {"doc_id": first, "replace_body": f"See {second}.", "force": True}
        )
        kinds = {issue["kind"] for issue in dispatcher.dispatch("check", {})}
        assert "cycle" not in kinds

    def test_it_does_not_create_a_layering_violation(self, dispatcher: Dispatcher) -> None:
        # Layering reads edges the schema marks `dependency: true`. A mention
        # has no kind at all, so it cannot assert a dependency in any direction.
        low = dispatcher.dispatch(
            "add", {"type": "issue", "title": "Low", "description": "d", "body": "x"}
        )["id"]
        dispatcher.dispatch(
            "add",
            {"type": "architecture", "title": "High", "description": "d", "body": f"See {low}."},
        )
        kinds = {issue["kind"] for issue in dispatcher.dispatch("check", {})}
        assert "layering" not in kinds


class TestReadShape:
    def test_get_carries_both_directions_and_the_skeleton_carries_neither(
        self, dispatcher: Dispatcher
    ) -> None:
        target = dispatcher.dispatch(
            "add", {"type": "decision", "title": "T", "description": "d", "body": "x"}
        )["id"]
        source = dispatcher.dispatch(
            "add", {"type": "issue", "title": "I", "description": "d", "body": f"See {target}."}
        )["id"]

        assert dispatcher.dispatch("get", {"doc_id": source})["mentions"] == (target,)
        assert dispatcher.dispatch("get", {"doc_id": target})["mentioned_by"] == (source,)
        # The list paths stay skeletons: two more id arrays per hit is exactly
        # the context cost that contract exists to avoid.
        summary = dispatcher.dispatch("query", {"limit": 5})[0]
        assert "mentions" not in summary
        assert "mentioned_by" not in summary

    def test_an_unresolved_mention_is_absent_rather_than_listed(
        self, dispatcher: Dispatcher
    ) -> None:
        source = dispatcher.dispatch(
            "add",
            {
                "type": "decision",
                "title": "T",
                "description": "d",
                "body": "Replaces adr-deadbeefcafe.",
            },
        )["id"]
        assert dispatcher.dispatch("get", {"doc_id": source})["mentions"] == ()


class TestDerivedState:
    """It is a projection: rebuildable, and never the source of truth."""

    def test_reindex_derives_it_from_a_body_the_cli_never_wrote(
        self, dispatcher: Dispatcher, settings: Settings
    ) -> None:
        # Hand-editing a body is permitted (the by-hand table) and `reindex` is
        # what makes the index agree again — so the rebuild has to derive the
        # graph, not just carry over what a previous write stored. Asserting
        # after a reindex of rows the *CLI* already wrote would pass with the
        # rebuild removed entirely.
        target = dispatcher.dispatch(
            "add", {"type": "decision", "title": "T", "description": "d", "body": "x"}
        )["id"]
        view = dispatcher.dispatch(
            "add", {"type": "issue", "title": "I", "description": "d", "body": "Nothing yet."}
        )
        source = view["id"]
        assert dispatcher.dispatch("get", {"doc_id": source})["mentions"] == ()

        path = settings.docs_root / view["path"]
        path.write_text(
            path.read_text(encoding="utf-8").replace("Nothing yet.", f"See {target}."),
            encoding="utf-8",
        )
        dispatcher.dispatch("reindex", {})
        assert dispatcher.dispatch("get", {"doc_id": source})["mentions"] == (target,)

    def test_a_forward_reference_resolves_when_its_target_is_written(
        self, dispatcher: Dispatcher
    ) -> None:
        # An ADR naming the issue it will produce is normal, and the mention has
        # to start resolving when the issue is written — not when somebody
        # remembers to re-save the ADR. This is why the row is stored unresolved
        # and the join happens on read.
        future = "issue-0001"
        source = dispatcher.dispatch(
            "add",
            {
                "type": "decision",
                "title": "T",
                "description": "d",
                "body": f"Tracked in {future}.",
            },
        )["id"]
        assert dispatcher.dispatch("get", {"doc_id": source})["mentions"] == ()

        created = dispatcher.dispatch(
            "add", {"type": "issue", "title": "Tracked", "description": "d", "body": "x"}
        )["id"]
        assert created == future, "fixture assumes the first issue gets the sequential id"
        assert dispatcher.dispatch("get", {"doc_id": source})["mentions"] == (future,)

    def test_deleting_the_target_leaves_the_source_readable(self, dispatcher: Dispatcher) -> None:
        target = dispatcher.dispatch(
            "add", {"type": "decision", "title": "T", "description": "d", "body": "x"}
        )["id"]
        source = dispatcher.dispatch(
            "add", {"type": "issue", "title": "I", "description": "d", "body": f"See {target}."}
        )["id"]
        dispatcher.dispatch("delete", {"doc_id": target})
        # The prose still names it; it simply stops resolving. Nothing rewrote
        # the body, which is the point — a delete may not edit other people's
        # sentences the way it strips their `related` edges.
        assert dispatcher.dispatch("get", {"doc_id": source})["mentions"] == ()

    def test_a_tag_rename_does_not_disturb_it(self, dispatcher: Dispatcher) -> None:
        # `tags` writes documents without recomputing mentions, on the grounds
        # that it never touches a body. If that ever stops being true, this
        # fails rather than the graph silently going stale.
        dispatcher.dispatch("tag_add", {"key": "auth", "description": "d"})
        target = dispatcher.dispatch(
            "add", {"type": "decision", "title": "T", "description": "d", "body": "x"}
        )["id"]
        source = dispatcher.dispatch(
            "add",
            {
                "type": "issue",
                "title": "I",
                "description": "d",
                "tags": ["auth"],
                "body": f"See {target}.",
            },
        )["id"]
        dispatcher.dispatch("tag_rename", {"old": "auth", "new": "authn"})
        assert dispatcher.dispatch("get", {"doc_id": source})["mentions"] == (target,)


def test_a_write_still_fails_loudly_when_the_body_is_unreadable(
    dispatcher: Dispatcher,
) -> None:
    # Deriving edges from prose must not turn a Tier 0 rejection into a partial
    # write: the scan happens after validation, so an invalid document never
    # reaches the mention table.
    with pytest.raises(DocirError):
        dispatcher.dispatch(
            "add", {"type": "nosuchtype", "title": "T", "description": "d", "body": "adr-0001"}
        )
