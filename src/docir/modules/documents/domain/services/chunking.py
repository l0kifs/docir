"""Split a document body into the units that actually get embedded.

The embedding model reads a fixed number of tokens and silently ignores the
rest. Measured against ``BAAI/bge-small-en-v1.5`` on this project's own prose,
that window is about **1,900 characters**: append a sentence past it and the
vector comes back bit-identical, cosine 1.000000. 83 of the 103 documents in
docir's own store are longer than that, and the largest has 5% of its text
inside the window — so for most of the corpus, most of the body was not in the
semantic index at all. It was not ranked badly; it was not there.

Chunking is the fix: embed each section separately, so every part of a document
lands inside some vector. This module owns the *splitting* rule and nothing
else — pure text in, pure text out, no I/O, no embedder.

The rule (ADR-0014):

* Split at ``##`` and deeper headings. ``#`` is the document title repeated in
  the body and is not a section boundary.
* Text before the first heading is the preamble and becomes chunk 0, so a
  document with no headings at all is exactly one chunk.
* **Never split inside a fenced code block.** A ``##`` inside a Python fence is
  a comment, not a heading, and cutting there produces two chunks that are each
  invalid.
* Sections shorter than :data:`MIN_CHUNK_CHARS` are merged forward into the
  next one — a bare heading with one line under it costs a whole vector and
  says almost nothing on its own.
* Sections longer than :data:`MAX_CHUNK_CHARS` are hard-split on paragraph
  boundaries, because a chunk over the window has the same problem the document
  had.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import NamedTuple

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")

#: Sections shorter than this are merged into the following one. A heading plus
#: a single sentence is not worth a vector of its own, and merging keeps the
#: neighbouring context that makes it interpretable.
MIN_CHUNK_CHARS = 200

#: Hard ceiling on a chunk's own text. Deliberately well under the ~1,900-char
#: model window rather than at it: :meth:`Chunk.embedding_text` prepends the
#: document title and the heading path, and a chunk that overflows the window
#: reintroduces exactly the truncation this module exists to remove. A section
#: longer than this is split on paragraph boundaries.
MAX_CHUNK_CHARS = 1200

#: The heading depth a split happens at. ``#`` is the title restated in the
#: body — splitting there would put the whole document in one chunk again.
SPLIT_LEVEL = 2


class EmbeddableChunk(NamedTuple):
    """A chunk with its text already rendered for the embedder.

    What :meth:`Document.embedding_chunks` hands the scheduler. Distinct from
    :class:`Chunk` because ``text`` here is the *prefixed* string that gets
    embedded, not the raw section — and a tuple, so the scheduler can consume it
    without importing anything from this module (``indexing`` may not depend on
    ``documents``; the entity is the seam).
    """

    ordinal: int
    heading: str
    text: str


@dataclass(frozen=True, slots=True)
class Chunk:
    """One embeddable slice of a document body.

    ``ordinal`` is the position in the body, stable for a given body and used as
    the persisted key. ``heading`` is the section title (empty for the preamble
    and for an overflow continuation), carried so a reader can be pointed at the
    section by name rather than by offset.
    """

    ordinal: int
    heading: str
    text: str

    def embedding_text(self, title: str) -> str:
        """The text actually embedded for this chunk.

        Prefixed with the document title and the section heading, because a
        section read in isolation frequently omits what it is a section *of* —
        "Rotation is a runbook step" does not mention certificates, payments, or
        the provider. The prefix is what lets a chunk answer a query phrased in
        the document's terms rather than the section's.
        """
        parts = [part for part in (title.strip(), self.heading.strip(), self.text.strip()) if part]
        return "\n\n".join(parts)


def split_body(body: str) -> list[Chunk]:
    """Split ``body`` into embeddable chunks, in document order.

    Always returns at least one chunk for a non-empty body, and an empty list
    for a body that is blank — a document with no body is fully described by its
    title and description, which the document-level vector already covers.
    """
    if not body.strip():
        return []
    sections = _split_on_headings(body)
    merged = _merge_short(sections)
    chunks: list[Chunk] = []
    for heading, text in merged:
        for index, piece in enumerate(_split_long(text)):
            # Only the first piece of an over-long section keeps the heading:
            # the continuations are not separately addressable sections, and
            # labelling them with the same name would make `get --section`
            # ambiguous about which one it meant.
            chunks.append(Chunk(len(chunks), heading if index == 0 else "", piece))
    return chunks


def _split_on_headings(body: str) -> list[tuple[str, str]]:
    """``(heading, text)`` pairs, cutting at level-2-or-deeper headings.

    Tracks fenced code blocks so a ``##`` comment inside one is never mistaken
    for a heading — the single case where a naive line scan silently corrupts
    every chunk boundary after it.
    """
    sections: list[tuple[str, list[str]]] = [("", [])]
    in_fence = False
    for line in body.splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            sections[-1][1].append(line)
            continue
        match = None if in_fence else _HEADING_RE.match(line)
        if match is not None and len(match.group(1)) >= SPLIT_LEVEL:
            sections.append((match.group(2).strip(), []))
            continue
        sections[-1][1].append(line)
    return [
        (heading, "\n".join(lines).strip())
        for heading, lines in sections
        if heading or "\n".join(lines).strip()
    ]


def _merge_short(sections: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Fold sections under :data:`MIN_CHUNK_CHARS` into the one that follows.

    Forward rather than backward so the merged block keeps the *first*
    heading — that is the one a reader would name, and the one the section read
    path resolves.
    """
    merged: list[tuple[str, str]] = []
    pending: tuple[str, str] | None = None
    for heading, text in sections:
        if pending is not None:
            heading_text = f"## {heading}\n\n{text}" if heading else text
            text = f"{pending[1]}\n\n{heading_text}".strip()
            heading = pending[0] or heading
            pending = None
        if len(text) < MIN_CHUNK_CHARS:
            pending = (heading, text)
            continue
        merged.append((heading, text))
    if pending is not None:
        # Nothing followed it. Append to the previous chunk if there is one,
        # rather than emitting a chunk below the minimum.
        if merged:
            last_heading, last_text = merged[-1]
            merged[-1] = (last_heading, f"{last_text}\n\n{_render(pending)}".strip())
        else:
            merged.append(pending)
    return merged


def _render(section: tuple[str, str]) -> str:
    heading, text = section
    return f"## {heading}\n\n{text}".strip() if heading else text


def _split_long(text: str) -> list[str]:
    """Break text over :data:`MAX_CHUNK_CHARS` on paragraph boundaries.

    Paragraphs rather than sentences or a fixed offset: a paragraph is the
    largest unit that reliably survives being read alone, and a split mid-fence
    would again hand the model something that is not valid markdown.
    """
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]
    pieces: list[str] = []
    current: list[str] = []
    size = 0
    for paragraph in text.split("\n\n"):
        # A single paragraph over the ceiling is emitted whole: cutting inside
        # one is worse than a chunk the model will trim the tail of.
        if size and size + len(paragraph) > MAX_CHUNK_CHARS:
            pieces.append("\n\n".join(current).strip())
            current, size = [], 0
        current.append(paragraph)
        size += len(paragraph) + 2
    if current:
        pieces.append("\n\n".join(current).strip())
    return [piece for piece in pieces if piece]
