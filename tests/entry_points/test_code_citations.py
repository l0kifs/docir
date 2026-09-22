"""A `file.py:line` in docir's own prose points where it says it points.

Reading the corpus against its code turned up five documents whose citation
columns had shifted *wholesale*: an architecture note on the **write** path
pointing `IndexProjected` into `_ranking_trace`, a read-path helper; a tag note
pointing `TagRenamed` at the `TagService` class header while `rename` sat eighty
lines below. Nothing caught any of it, because a stale line number is a
well-formed string and a checker holding only the number cannot tell
(issue-d4b194eca41d).

So a citation carries its own redundancy — the symbol it points at, named beside
it — and both halves are checked here. The corpus was swept to that form in the
same pass: of 266 citations, the 9 the prose already confirmed were paired, and
the rest lost the line and kept the file, because a line that is wrong two times
in five is worse than no line at all. What survived is 17, every one verified.

There is deliberately **no grandfathered set**. One was written, with 250
entries, and deleted when the sweep took the count to zero: a baseline is for a
rule that cannot yet hold everywhere, and this one can.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts"))

from code_citations import problems, symbol_at

_REPO = pathlib.Path(__file__).resolve().parents[2]
_STORE = _REPO / ".docir" / "docs"


def _documents() -> dict[str, str]:
    assert _STORE.is_dir(), (
        f"{_STORE} is missing — the suite runs from the checkout, so an absent "
        "store means this guard is scanning nothing rather than finding nothing"
    )
    found = {p.name: p.read_text(encoding="utf-8") for p in sorted(_STORE.rglob("*.md"))}
    assert found, f"{_STORE} holds no documents — see above"
    return found


DOCUMENTS = _documents()


@pytest.mark.parametrize("name", sorted(DOCUMENTS))
def test_every_citation_names_the_symbol_it_points_at(name: str) -> None:
    """The file resolves, the line exists, and the symbol beside it spans that line.

    The frontmatter is scanned too, not only the body: two of the last three
    citations to be fixed were in a `description`, which is the field every
    search result shows.
    """
    issues = problems(_REPO, DOCUMENTS[name], require_pair=True)
    assert not issues, f"{name}:\n  " + "\n  ".join(issues)


def test_the_store_still_carries_citations_to_check() -> None:
    """A guard over an empty set passes for the wrong reason.

    The sweep that made this rule holdable also made it easy to satisfy by
    deleting every citation, which would leave the corpus pointing at nothing
    and this file green.
    """
    from code_citations import citations

    total = sum(len(citations(text)) for text in DOCUMENTS.values())
    assert total >= 10, f"only {total} citations remain — has the store stopped citing code?"


def test_the_guard_sees_a_wrong_symbol() -> None:
    """Guard the guard: a checker that judges nothing passes everything."""
    text = "See `src/docir/platform/naming/slug.py:1` (`NoSuchSymbol`) for the rule."
    assert problems(_REPO, text, require_pair=True), "a wrong pairing must be reported"


def test_the_guard_sees_an_unpaired_citation() -> None:
    text = "See `src/docir/platform/naming/slug.py:1` for the rule."
    assert problems(_REPO, text, require_pair=True), "an unpaired citation must be reported"


def test_the_guard_sees_a_line_past_the_end() -> None:
    text = "See `src/docir/platform/naming/slug.py:99999` (`slugify`)."
    assert problems(_REPO, text, require_pair=True), "a line past EOF must be reported"


def test_the_guard_accepts_a_correct_pair() -> None:
    path = _REPO / "src/docir/modules/documents/application/dto.py"
    actual = symbol_at(path, 170)
    text = f"See `src/docir/modules/documents/application/dto.py:170` (`{actual}`)."
    assert not problems(_REPO, text, require_pair=True), f"line 170 is in {actual}"
