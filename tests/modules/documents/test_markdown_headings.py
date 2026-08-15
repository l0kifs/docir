"""The one fence-aware heading scanner, and the two readers that must agree.

Guards issue-af046a467575. `chunking` skipped fenced code blocks; the
section-edit path did not, so on a body quoting a markdown template they
disagreed about what the sections *were*. The visible damage was worse than the
disagreement: `get --section` returned a fragment ending in an unclosed fence,
and `replace_section` ended the span at the phantom boundary and stranded the
rest of the quote at top level — a corrupted body reported as success.

Every test here fails against the pre-fix code. The agreement tests are the
point: either scanner can be "correct" on its own and still be wrong together.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from docir.modules.documents.domain.services.chunking import split_body
from docir.modules.documents.domain.services.markdown_headings import scan_headings
from docir.modules.documents.domain.services.markdown_sections import (
    extract_section,
    replace_section,
    section_headings,
)

_REPO = Path(__file__).resolve().parents[3]

#: A rule that quotes a markdown template — the shape that broke, and the shape
#: docir's own architecture-rules document is written in.
QUOTED_TEMPLATE = (
    "## Rule 7\n\nEvery module has a contract:\n\n"
    "```markdown\n## Purpose\nwhat it does\n## Owns\nits data\n```\n\n"
    "More of rule 7, after the fence.\n\n"
    "## Rule 8\n\nunrelated\n"
)


class TestScanHeadings:
    def test_a_heading_inside_a_fence_is_not_one(self) -> None:
        assert [h.text for h in scan_headings(QUOTED_TEMPLATE)] == ["Rule 7", "Rule 8"]

    def test_tilde_fences_count_too(self) -> None:
        body = "## A\n\n~~~md\n## Not a heading\n~~~\n\n## B\n"
        assert [h.text for h in scan_headings(body)] == ["A", "B"]

    def test_levels_and_line_indices_are_reported(self) -> None:
        body = "# Title\n\n## Section\n\n### Sub\n"
        assert [(h.line, h.level, h.text) for h in scan_headings(body)] == [
            (0, 1, "Title"),
            (2, 2, "Section"),
            (4, 3, "Sub"),
        ]

    def test_an_unterminated_fence_swallows_what_follows(self) -> None:
        """Deliberate, and the reason the scanner is shared rather than copied.

        A body that renders as one open code block must not be silently
        sectioned behind the reader's back — and whatever the answer is, the
        embedder and the section reader have to give the same one.
        """
        body = "## A\n\n```\n## B\n\n## C\n"
        assert [h.text for h in scan_headings(body)] == ["A"]


class TestTheTwoReadersAgree:
    @pytest.mark.parametrize(
        "body",
        [
            QUOTED_TEMPLATE,
            "## A\n\n```python\n## comment\n```\n\n## B\n",
            "## A\n\n~~~\n## fenced\n~~~\n\n### Deep\n\ntext\n",
            "no headings at all\n",
            "## A\n\n```\n## unterminated\n\n## C\n",
            "# Title\n\npreamble\n\n## One\n\ntext\n\n## Two\n\ntext\n",
        ],
    )
    def test_the_section_reader_and_the_chunker_see_the_same_headings(self, body: str) -> None:
        """The reader's set must *equal* the scanner's, not merely contain it.

        An earlier version of this asserted `chunked <= read`, which a reader
        that grows its own naive scanner passes trivially — a naive scan returns
        *more* headings, and that is the direction the real bug went. Injecting
        the divergence is what showed the guard was checking nothing.
        """
        scanned = {h.text for h in scan_headings(body)}
        assert set(section_headings(body)) == scanned, "the reader has its own idea of a heading"
        # The chunker splits at level 2+ and merges short sections away, so it
        # may report fewer — never a heading the scanner does not have.
        chunked = {chunk.heading for chunk in split_body(body) if chunk.heading}
        deep = {h.text for h in scan_headings(body) if h.level >= 2}
        assert chunked <= deep, f"the chunker invented {chunked - deep}"

    def test_every_document_in_this_repo_agrees(self) -> None:
        """The corpus guard — this is where the bug was actually living.

        Asserts *which* documents were scanned, not just that none failed: a
        glob that matches nothing looks exactly like a clean corpus.
        """
        docs = sorted((_REPO / ".docir" / "docs").rglob("*.md"))
        assert len(docs) > 50, f"only {len(docs)} documents scanned — the sweep found nothing"
        checked = 0
        for path in docs:
            body = re.sub(r"\A---\n.*?\n---\n", "", path.read_text(encoding="utf-8"), flags=re.S)
            scanned = {h.text for h in scan_headings(body)}
            assert set(section_headings(body)) == scanned, f"{path.name}: readers disagree"
            chunked = {chunk.heading for chunk in split_body(body) if chunk.heading}
            deep = {h.text for h in scan_headings(body) if h.level >= 2}
            assert chunked <= deep, f"{path.name}: chunker invented {chunked - deep}"
            checked += 1
        assert checked == len(docs)


class TestSectionEditsSurviveAQuotedTemplate:
    def test_the_phantom_headings_are_gone(self) -> None:
        # Before the fix this listed 'Purpose' and 'Owns' as real sections, so
        # the "no such section" error pointed callers at headings that are not.
        assert section_headings(QUOTED_TEMPLATE) == ["Rule 7", "Rule 8"]

    def test_extract_returns_a_balanced_fence(self) -> None:
        section = extract_section(QUOTED_TEMPLATE, "Rule 7")
        assert section.count("```") % 2 == 0, "the section ends inside a code fence"
        assert "More of rule 7, after the fence." in section
        assert "## Rule 8" not in section

    def test_replace_does_not_strand_the_rest_of_the_quote(self) -> None:
        result = replace_section(QUOTED_TEMPLATE, "Rule 7", "NEW")
        assert "NEW" in result
        # Everything the section held is gone, including the quoted template —
        # previously it survived as top-level headings after the replacement.
        for stranded in ("## Purpose", "## Owns", "More of rule 7"):
            assert stranded not in result, f"{stranded!r} outlived the section it belonged to"
        assert section_headings(result) == ["Rule 7", "Rule 8"]
        assert result.count("```") % 2 == 0

    def test_read_and_write_still_describe_the_same_span(self) -> None:
        # The module's standing contract, now over a body with a fence in it.
        before = extract_section(QUOTED_TEMPLATE, "Rule 7")
        after = extract_section(replace_section(QUOTED_TEMPLATE, "Rule 7", "NEW"), "Rule 7")
        assert before.splitlines()[0] == after.splitlines()[0]
        assert extract_section(QUOTED_TEMPLATE, "Rule 8") == extract_section(
            replace_section(QUOTED_TEMPLATE, "Rule 7", "NEW"), "Rule 8"
        )
