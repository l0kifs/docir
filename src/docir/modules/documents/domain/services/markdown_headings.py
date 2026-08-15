"""Where a markdown body's headings are — the one answer everything else reads.

Two modules used to decide this independently. :mod:`chunking` tracked fenced
code blocks, because a ``##`` inside a fence is a comment and cutting there
yields two invalid chunks. :mod:`markdown_sections` did not, so on a body that
quotes a markdown template the two disagreed about what the sections *were*
(issue-af046a467575): the reader saw four headings where the chunker saw one.

That divergence was not cosmetic. ``get --section`` returned a fragment ending
in an unclosed fence; ``update --replace-section`` wrote the replacement, ended
it at the phantom boundary and stranded the rest of the quoted template at top
level — a corrupted body, reported as success. Both are now derived from
:func:`scan_headings`, so the span an agent reads and the span it overwrites
cannot come apart, and neither can drift from the span that got embedded.

An **unterminated** fence swallows the headings after it, by construction. That
is the honest reading of the text and, more importantly, the same reading in all
three places: a body that renders as one code block to a reader must not be
silently sectioned behind their back.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True)
class Heading:
    """One heading found outside any fenced code block."""

    #: Zero-based index of the heading's line in ``body.splitlines()``.
    line: int
    #: Depth, as the number of leading ``#`` (1-6).
    level: int
    #: The heading text, markers and surrounding whitespace stripped.
    text: str


def scan_headings(body: str) -> list[Heading]:
    """Every heading in ``body``, in document order, skipping fenced blocks."""
    headings: list[Heading] = []
    in_fence = False
    for index, line in enumerate(body.splitlines()):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if (match := _HEADING_RE.match(line)) is not None:
            headings.append(Heading(index, len(match.group(1)), match.group(2).strip()))
    return headings
