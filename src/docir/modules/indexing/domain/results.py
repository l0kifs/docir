"""Read-side value records returned by the search path."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SearchHit:
    """A single FTS5 hit: the matching id and its (lower-is-better) BM25 score."""

    doc_id: str
    bm25: float
