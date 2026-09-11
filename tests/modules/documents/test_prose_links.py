"""`[[...]]` prose links: the resolution rule, and the check that reads it.

The other prose graph. `scan_document_ids` finds ids *named* in a sentence and
feeds navigation only; this finds ids, stems, slugs and titles somebody wrapped
in brackets, which is an explicit claim that a document is there. That is the
whole reason the unresolved ones are a Tier 1 warning where an unresolved
mention is a Tier 2 advisory (adr-ae631a356639) — so most of what is pinned here
is the boundary between the two: what resolves, what is skipped, and what the
check must *not* start doing.
"""

from __future__ import annotations

import pytest

from docir.entry_points.dispatch import Dispatcher
from docir.platform.naming.links import (
    LinkIndex,
    LinkTarget,
    parse_wikilink,
    scan_wikilinks,
)

_TARGET = LinkTarget(
    doc_id="adr-3f9a2b1c7d4e",
    title="Hub API reads revocation epochs from its own service keyspace",
    # Truncated at 60 characters, as the file store writes it — the form a
    # reader gets by copying a path, and the one no title can reproduce.
    stem="adr-3f9a2b1c7d4e-hub-api-reads-revocation-epochs-from-its-own-service-keyspac",
)


class TestScanner:
    """`scan_wikilinks` — the grammar, in isolation."""

    def test_it_finds_links_in_prose(self) -> None:
        assert [link.target for link in scan_wikilinks("See [[adr-0001]] and [[how-auth]].")] == [
            "adr-0001",
            "how-auth",
        ]

    def test_a_fenced_block_holds_no_links(self) -> None:
        # The opposite of `scan_document_ids`, deliberately: an id in an example
        # command names a document, but `[[...]]` in one is the *syntax* being
        # shown. The renderer agrees — a fence is opaque in the token stream —
        # so a link there was never a link.
        assert scan_wikilinks("Write it like this:\n\n```\n[[some-target]]\n```\n") == ()

    def test_an_inline_code_span_holds_no_links(self) -> None:
        # This repository's only two occurrences are both of this shape, in the
        # document explaining what a wikilink is. Read literally they would be
        # the check's only two findings.
        assert scan_wikilinks("Basic Memory's `[[Target]]` links render elsewhere.") == ()

    @pytest.mark.parametrize(
        ("inner", "expected"),
        [
            ("adr-0001", ("adr-0001", "", "")),
            ("adr-0001#Why it matters", ("adr-0001", "Why it matters", "")),
            ("adr-0001|the auth decision", ("adr-0001", "", "the auth decision")),
            ("adr-0001#Why|the auth decision", ("adr-0001", "Why", "the auth decision")),
            ("  adr-0001  ", ("adr-0001", "", "")),
        ],
    )
    def test_it_splits_the_target_from_its_section_and_label(
        self, inner: str, expected: tuple[str, str, str]
    ) -> None:
        link = parse_wikilink(inner)
        assert link is not None
        assert (link.target, link.section, link.label) == expected

    @pytest.mark.parametrize("inner", ["", "   ", "|label", "#heading"])
    def test_a_link_naming_nothing_is_not_a_link(self, inner: str) -> None:
        # Not a finding either: reporting `[[|x]]` as broken tells somebody to
        # go and find a document that was never named.
        assert parse_wikilink(inner) is None

    def test_an_unclosed_bracket_does_not_swallow_the_paragraph(self) -> None:
        assert scan_wikilinks("An [[unclosed link\nand the next line [[adr-0001]].") == (
            parse_wikilink("adr-0001"),
        )


class TestResolution:
    """The four forms a target may take, and the one that must not resolve."""

    @pytest.mark.parametrize(
        ("target", "form"),
        [
            ("adr-3f9a2b1c7d4e", "the document id"),
            (
                "adr-3f9a2b1c7d4e-hub-api-reads-revocation-epochs-from-its-own-service-keyspac",
                "the filename stem, truncated as the file carries it",
            ),
            (
                "hub-api-reads-revocation-epochs-from-its-own-service-keyspace",
                "the untruncated title slug, as somebody writes it by hand",
            ),
            (
                "Hub API reads revocation epochs from its own service keyspace",
                "the title itself, for anyone who does not know the convention",
            ),
            (
                "decisions/adr-3f9a2b1c7d4e-hub-api-reads-revocation-epochs-from-its-own-service-keyspac.md",
                "a pasted path",
            ),
        ],
    )
    def test_every_written_form_reaches_the_document(self, target: str, form: str) -> None:
        assert LinkIndex([_TARGET]).resolve(target).doc_id == "adr-3f9a2b1c7d4e", form

    def test_a_slug_guessed_one_word_short_does_not(self) -> None:
        # The reported defect's single real broken link. Nothing can distinguish
        # it from a link to a document not written yet, which is why `--fix`
        # leaves it.
        resolution = LinkIndex([_TARGET]).resolve(
            "hub-api-reads-revocation-epochs-from-its-own-service-keyspace-not"
        )
        assert resolution.doc_id is None
        assert resolution.candidates == ()

    def test_a_title_two_documents_share_resolves_to_neither(self) -> None:
        # Picking one silently is how a reader lands on the wrong document with
        # no way to tell. The candidates are reported instead.
        index = LinkIndex(
            [
                LinkTarget(doc_id="adr-0001", title="Context", stem="adr-0001-context"),
                LinkTarget(doc_id="adr-0002", title="Context", stem="adr-0002-context"),
            ]
        )
        resolution = index.resolve("context")
        assert resolution.doc_id is None
        assert resolution.is_ambiguous
        assert resolution.candidates == ("adr-0001", "adr-0002")
        # And each is still reachable by the form that carries an id.
        assert index.resolve("adr-0002-context").doc_id == "adr-0002"


class TestTheCheck:
    """`unresolved-link` end to end, through the dispatcher."""

    def _links(self, dispatcher: Dispatcher) -> dict[str, str]:
        """Every `unresolved-link` message, joined per source document.

        Joined rather than keyed one-to-one: the check reports one finding per
        (document, target) pair, and a dict keeping the last one would hide
        every broken link but the final one in a body — which is precisely the
        silence this whole check exists to end.
        """
        found: dict[str, str] = {}
        for issue in dispatcher.dispatch("check", {}):
            if issue["kind"] != "unresolved-link":
                continue
            source = issue["doc_ids"][0]
            found[source] = f"{found.get(source, '')} {issue['message']}".strip()
        return found

    def _add(self, dispatcher: Dispatcher, **fields: object) -> str:
        return str(dispatcher.dispatch("add", {"description": "d", **fields})["id"])

    def test_it_reports_the_broken_link_and_nothing_else(self, dispatcher: Dispatcher) -> None:
        target = self._add(
            dispatcher, type="decision", title="Hub API reads revocation epochs", body="Chosen."
        )
        source = self._add(
            dispatcher,
            type="architecture",
            title="Epoch propagation",
            body=(
                f"By id: [[{target}]].\n"
                "By slug: [[hub-api-reads-revocation-epochs]].\n"
                "Guessed: [[hub-api-reads-revocation-epochs-not]].\n"
                "\n```\n[[an-example]]\n```\n"
            ),
        )
        # The ids, not a count: a count cannot tell "two forms resolved" from
        # "the scan found nothing".
        assert self._links(dispatcher) == {
            source: (
                f"{source!r} links to [[hub-api-reads-revocation-epochs-not]], which names no "
                "document — find it with `docir search 'hub api reads revocation epochs not'` "
                "and link its id"
            )
        }
        assert target  # the by-id form above resolved to a real document

    def test_a_link_to_an_inactive_document_is_not_broken(self, dispatcher: Dispatcher) -> None:
        # The reporter's own second and fourth passes: `query` hides inactive
        # documents by default, so a hand-written validator calls a working link
        # broken. Resolution reads the corpus, not a default filter.
        target = self._add(dispatcher, type="issue", title="Token issuer epoch drift", body="x")
        dispatcher.dispatch("update", {"doc_id": target, "status": "resolved"})
        source = self._add(
            dispatcher,
            type="architecture",
            title="Epoch propagation",
            body="Tracked in [[token-issuer-epoch-drift]].",
        )
        assert self._links(dispatcher) == {}
        assert dispatcher.dispatch("get", {"doc_id": source})["id"] == source

    def test_a_retitle_keeps_the_stem_form_working_and_reports_the_rest(
        self, dispatcher: Dispatcher
    ) -> None:
        # The reported breakage, both halves. `update --set-title` keeps the
        # filename, so a link written against the *stem* keeps working — it
        # would break the moment the stem were derived from the title instead
        # of carried. A link written against the bare old title slug cannot
        # keep working, since that slug now names nothing; what it gains is
        # being *reported* rather than silently displaying a title no document
        # has. Resolving it would mean keeping former titles, and a slug freed
        # by one retitle is a slug the next document may claim.
        target = self._add(dispatcher, type="decision", title="Old name", body="x")
        source = self._add(
            dispatcher,
            type="architecture",
            title="Reader",
            body=f"See [[{target}-old-name]], [[old-name]] and [[new-name]].",
        )
        dispatcher.dispatch("update", {"doc_id": target, "set_title": "New name"})
        message = self._links(dispatcher)[source]
        assert f"[[{target}-old-name]]" not in message, "the stem outlives the title"
        assert "[[old-name]]" in message, "a freed title slug is reported, not guessed at"
        # The slug follows the *current* title, so a link written after the
        # retitle resolves — which is what makes the one above a real report
        # rather than the check having stopped resolving slugs at all.
        assert "[[new-name]]" not in message

    def test_it_reports_an_ambiguous_target_with_its_candidates(
        self, dispatcher: Dispatcher
    ) -> None:
        first = self._add(dispatcher, type="decision", title="Context", body="x")
        second = self._add(dispatcher, type="issue", title="Context", body="x")
        source = self._add(dispatcher, type="architecture", title="Reader", body="See [[Context]].")
        message = self._links(dispatcher)[source]
        assert "names 2 documents" in message
        assert first in message and second in message

    def test_it_is_a_warning_and_does_not_gate_a_merge(self, dispatcher: Dispatcher) -> None:
        # Promoting it would red-build a repository whose documents are all
        # intact — the failure every warning in the tier document avoids.
        self._add(dispatcher, type="decision", title="Reader", body="See [[nothing-at-all]].")
        found = [i for i in dispatcher.dispatch("check", {}) if i["kind"] == "unresolved-link"]
        assert [issue["severity"] for issue in found] == ["warning"]

    def test_repair_leaves_it_alone(self, dispatcher: Dispatcher) -> None:
        # A target that resolves to nothing needs somebody to say which document
        # was meant, and a repair has nothing to read with.
        source = self._add(dispatcher, type="decision", title="Reader", body="See [[gone]].")
        result = dispatcher.dispatch("repair", {})
        assert [action for action in result["actions"] if action["kind"] == "unresolved-link"] == []
        remaining = [i for i in result["remaining"] if i["kind"] == "unresolved-link"]
        assert [issue["doc_ids"][0] for issue in remaining] == [source]

    def test_a_prose_link_does_not_close_orphan(self, dispatcher: Dispatcher) -> None:
        # The question the report left open, answered: `related:` stays the
        # structural layer and `[[...]]` stays navigation. Without this the
        # check would be a second, untyped graph nobody declared.
        target = self._add(dispatcher, type="decision", title="Tokens", body="Chosen.")
        source = self._add(dispatcher, type="issue", title="Login is slow", body="See [[tokens]].")
        orphans = {
            issue["doc_ids"][0]
            for issue in dispatcher.dispatch("check", {})
            if issue["kind"] == "orphan"
        }
        assert orphans == {source, target}
