"""The splitting rule — pure text in, chunks out (adr-927aa43d9635).

Every case here is a boundary the rule has to get right for the vectors built
from it to mean anything. The code-fence case is the one that silently corrupts
everything downstream when it is wrong: a ``##`` comment inside a Python block
is not a heading, and cutting there produces two chunks that are each invalid
markdown and each embed as nonsense.
"""

from __future__ import annotations

from datetime import date

import pytest

from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.services.chunking import (
    MAX_CHUNK_CHARS,
    MIN_CHUNK_CHARS,
    split_body,
)

_FIXED_DATE = date(2026, 7, 7)

_PARA = "Sentences enough to clear the minimum length so this section stands on its own. " * 3


def _section(heading: str, body: str = _PARA) -> str:
    return f"## {heading}\n\n{body}\n"


class TestSplitting:
    def test_an_empty_body_produces_no_chunks(self) -> None:
        """A document with no body is already fully covered by its own vector."""
        assert split_body("") == []
        assert split_body("   \n\n  ") == []

    def test_a_body_with_no_headings_is_one_chunk(self) -> None:
        chunks = split_body(_PARA)
        assert len(chunks) == 1
        assert chunks[0].ordinal == 0
        assert chunks[0].heading == ""

    def test_each_h2_starts_a_chunk(self) -> None:
        body = _section("Context") + _section("Decision") + _section("Consequences")
        chunks = split_body(body)
        assert [chunk.heading for chunk in chunks] == ["Context", "Decision", "Consequences"]
        assert [chunk.ordinal for chunk in chunks] == [0, 1, 2]

    def test_a_h1_does_not_split(self) -> None:
        """`#` is the title restated in the body, not a section boundary.

        Splitting there would put the whole document back in one chunk, which is
        the state chunking exists to leave.
        """
        body = f"# Adopt MCP\n\n{_PARA}\n\n" + _section("Context")
        chunks = split_body(body)
        assert len(chunks) == 2
        assert chunks[0].heading == ""
        assert "# Adopt MCP" in chunks[0].text

    def test_deeper_headings_split_too(self) -> None:
        body = _section("Context") + f"### Detail\n\n{_PARA}\n"
        assert [chunk.heading for chunk in split_body(body)] == ["Context", "Detail"]

    def test_preamble_becomes_chunk_zero(self) -> None:
        body = f"{_PARA}\n\n" + _section("Decision")
        chunks = split_body(body)
        assert chunks[0].heading == ""
        assert chunks[0].text.startswith("Sentences enough")


class TestCodeFences:
    def test_a_heading_inside_a_fence_is_not_a_boundary(self) -> None:
        """The case that corrupts every chunk after it when handled naively."""
        body = (
            _section("Usage")
            + "```python\n"
            + "## not a heading, a comment\n"
            + "value = 1\n"
            + "```\n\n"
            + _section("Notes")
        )
        chunks = split_body(body)
        assert [chunk.heading for chunk in chunks] == ["Usage", "Notes"]
        assert "## not a heading, a comment" in chunks[0].text
        assert "```python" in chunks[0].text, "the fence was split away from its content"

    def test_tilde_fences_count_too(self) -> None:
        body = _section("Usage") + "~~~\n## still not a heading\n~~~\n\n" + _section("Notes")
        assert [chunk.heading for chunk in split_body(body)] == ["Usage", "Notes"]


class TestSizeBounds:
    def test_a_short_section_merges_into_the_next(self) -> None:
        """A heading with one line under it is not worth a vector of its own."""
        body = "## Tiny\n\nOne line.\n\n" + _section("Substantial")
        chunks = split_body(body)
        assert len(chunks) == 1
        assert chunks[0].heading == "Tiny", "the merged chunk should keep the first heading"
        assert "One line." in chunks[0].text
        assert "Substantial" in chunks[0].text

    def test_a_trailing_short_section_joins_the_previous_one(self) -> None:
        body = _section("Substantial") + "## Tiny\n\nOne line.\n"
        chunks = split_body(body)
        assert len(chunks) == 1
        assert "One line." in chunks[0].text

    def test_a_merge_that_would_have_to_be_split_is_declined(self) -> None:
        """Guards issue-66d43f63e441 — the two rules composed to erase a heading.

        `arch-0a3c2d6d54a6` had a 149-char `Backbone` before a long
        `Event timeline`. The short one merged forward, the merged block then
        overflowed and was hard-split, and only the first piece kept a heading —
        so `Event timeline` named no chunk at all and `matched_section` could
        never point at it, while `get --section` still returned it fine.
        """
        long_text = "x" * (MAX_CHUNK_CHARS - 20)
        body = (
            "## Backbone\n\nsix words of summary here.\n\n" + f"## Event timeline\n\n{long_text}\n"
        )
        chunks = split_body(body)
        assert [chunk.heading for chunk in chunks] == ["Backbone", "Event timeline"]
        assert all(chunk.heading for chunk in chunks), "a heading was lost to the split"

    def test_a_short_section_still_merges_when_the_result_fits(self) -> None:
        # The decline is narrow: merging is still what a short section gets,
        # because a heading plus one line is not worth a vector of its own.
        body = "## Tiny\n\nOne line.\n\n" + _section("Substantial")
        assert len(split_body(body)) == 1

    def test_a_trailing_short_section_that_would_overflow_stays_separate(self) -> None:
        # The same composition from the other end: appending it to the previous
        # chunk would overflow, split, and drop this heading instead.
        body = "## Big\n\n" + "x" * MAX_CHUNK_CHARS + "\n\n## Tail\n\nOne line.\n"
        chunks = split_body(body)
        assert [chunk.heading for chunk in chunks] == ["Big", "Tail"]

    def test_no_heading_is_lost_to_a_split_in_either_composition(self) -> None:
        """The invariant, stated once: a split never costs an address.

        A merge may still absorb a heading — that is the documented forward-merge
        rule and a reader can still reach the text. Being cut away by the
        overflow splitter is different: nothing names the section afterwards.
        """
        long_text = "x" * MAX_CHUNK_CHARS
        for body in (
            f"## A\n\nshort.\n\n## B\n\n{long_text}\n",
            f"## A\n\n{long_text}\n\n## B\n\nshort.\n",
            f"## A\n\nshort.\n\n## B\n\n{long_text}\n\n## C\n\nshort.\n",
        ):
            chunks = split_body(body)
            headless = [chunk for chunk in chunks if not chunk.heading]
            assert not headless, f"{len(headless)} unaddressable chunk(s) in {body[:20]!r}"

    def test_a_lone_short_body_is_still_one_chunk(self) -> None:
        """Nothing to merge into: better a small chunk than no chunk at all."""
        chunks = split_body("## Tiny\n\nOne line.\n")
        assert len(chunks) == 1
        assert "One line." in chunks[0].text

    def test_a_long_section_is_split_on_paragraphs(self) -> None:
        paragraph = "A paragraph that is quite long and says a number of things. " * 5
        body = "## Big\n\n" + "\n\n".join([paragraph] * 6)
        chunks = split_body(body)
        assert len(chunks) > 1
        assert all(len(chunk.text) <= MAX_CHUNK_CHARS * 1.5 for chunk in chunks)
        # Only the first continuation keeps the name: `get --section` resolves a
        # heading to one span, so two chunks claiming it would be ambiguous.
        assert chunks[0].heading == "Big"
        assert all(chunk.heading == "" for chunk in chunks[1:])

    def test_the_ceiling_stays_under_the_model_window(self) -> None:
        """The bound is derived from the measured window, not chosen for looks.

        A chunk that overflows the window is truncated exactly like the document
        was, which would reintroduce the bug one level down. ~1,900 characters is
        the measured window; the title and heading prefix eat into it.
        """
        assert MAX_CHUNK_CHARS < 1900
        assert MIN_CHUNK_CHARS < MAX_CHUNK_CHARS

    def test_ordinals_are_contiguous_across_splits(self) -> None:
        paragraph = "Another sizeable paragraph carrying real sentences in it. " * 5
        body = _section("First") + "## Big\n\n" + "\n\n".join([paragraph] * 6)
        chunks = split_body(body)
        assert [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))


class TestEmbeddingText:
    def _document(self, body: str) -> Document:
        return Document(
            id="arch-0001",
            title="Payment provider integration surface",
            description="Everything crossing the provider boundary.",
            type="architecture",
            status="draft",
            created=_FIXED_DATE,
            updated=_FIXED_DATE,
            body=body,
        )

    def test_each_chunk_carries_the_document_title(self) -> None:
        """A section read alone often never restates its own subject.

        "Rotation is a runbook step" mentions neither certificates nor the
        provider, so without the prefix the chunk cannot be matched by a query
        phrased in the document's terms — which is how people actually ask.
        """
        document = self._document(_section("Credentials and certificate rotation"))
        (chunk,) = document.embedding_chunks()
        assert chunk.text.startswith("Payment provider integration surface")
        assert "Credentials and certificate rotation" in chunk.text

    def test_the_triples_are_positional_for_the_scheduler(self) -> None:
        """`indexing` unpacks these without importing anything from `documents`."""
        document = self._document(_section("Context") + _section("Decision"))
        for ordinal, heading, text in document.embedding_chunks():
            assert isinstance(ordinal, int)
            assert isinstance(heading, str)
            assert isinstance(text, str)

    def test_a_bodyless_document_offers_no_chunks(self) -> None:
        assert self._document("").embedding_chunks() == ()


@pytest.mark.parametrize(
    "body",
    [
        "",
        _PARA,
        _section("One") + _section("Two"),
        "```\n## fence\n```\n\n" + _section("After"),
    ],
)
def test_chunks_never_lose_or_duplicate_ordinals(body: str) -> None:
    chunks = split_body(body)
    assert [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))
