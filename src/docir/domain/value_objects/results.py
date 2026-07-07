"""Read-side value records returned by the search and context paths."""

from __future__ import annotations

from dataclasses import dataclass

from docir.domain.entities.document import Document


@dataclass(frozen=True, slots=True)
class SearchHit:
    """A single FTS5 hit: the matching id and its (lower-is-better) BM25 score."""

    doc_id: str
    bm25: float


@dataclass(frozen=True, slots=True)
class ScoredDocument:
    """A document ranked by the hybrid (lexical + semantic) scorer.

    ``lexical`` is the normalized BM25 contribution, ``semantic`` the cosine
    contribution, and ``score`` the fused final ranking value (higher is more
    relevant). ``via_graph`` marks documents pulled in by one-hop ``related``
    traversal rather than by direct query relevance.
    """

    document: Document
    score: float
    lexical: float
    semantic: float
    via_graph: bool = False
