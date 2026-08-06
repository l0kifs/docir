"""Read-side value records returned by the search path."""

from __future__ import annotations

from dataclasses import dataclass

from docir.platform.embedding.vector import Embedding


@dataclass(frozen=True, slots=True)
class SearchHit:
    """A single FTS5 hit: the matching id and its (lower-is-better) BM25 score."""

    doc_id: str
    bm25: float


@dataclass(frozen=True, slots=True)
class VectorCandidate:
    """One vector to rank: a document's own, or one of its sections.

    ``section`` is the heading the vector came from, and ``None`` means the
    vector describes the whole document. It is carried because the ranking knows
    which vector won and every caller used to lose it: the section that put a
    long document at rank 1 is exactly what ``docir get --section`` should be
    asked for next (issue-afd25273ff1f).

    A chunk with no heading — a body's preamble, or the continuation of an
    over-long section — carries ``None`` too. It ranks like any other, it is
    simply not addressable by name.
    """

    doc_id: str
    vector: Embedding
    section: str | None = None
