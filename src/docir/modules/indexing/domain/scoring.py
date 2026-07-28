"""Hybrid scoring for ``docs context`` — fuse lexical and semantic ranks.

Rather than replacing FTS5 outright (lexical matches are valuable and cheap),
the context read path combines the BM25 ranking with cosine-similarity ranking.
Reciprocal Rank Fusion (RRF) is used: it is scale-free, so it sidesteps the
problem of BM25 scores and cosine scores living on incomparable numeric ranges.
"""

from __future__ import annotations

from dataclasses import dataclass

from docir.modules.indexing.domain.results import SearchHit
from docir.platform.embedding.vector import Embedding

# RRF dampening constant; 60 is the value from the original RRF paper.
DEFAULT_RRF_K = 60


@dataclass(frozen=True, slots=True)
class FusedScore:
    """A fused ranking for one document id.

    ``score``/``lexical``/``semantic`` are all RRF components — rank-derived, so
    they say where a document placed, never how good the match was. A perfect hit
    and the only-document-in-the-store score the same ~0.0328 at rank 1.

    ``similarity`` is the raw cosine that produced the semantic rank, carried
    through precisely because the fused score cannot answer "is this actually
    relevant?". It is ``None`` when the document had no current vector — a
    lexical-only hit — which is *unknown*, not zero.
    """

    doc_id: str
    score: float
    lexical: float
    semantic: float
    similarity: float | None = None


class HybridScorer:
    """Combines lexical (BM25) and semantic (cosine) rankings via RRF."""

    def __init__(self, rrf_k: int = DEFAULT_RRF_K) -> None:
        self._k = rrf_k

    def semantic_ranking(
        self, query: Embedding, vectors: list[tuple[str, Embedding]]
    ) -> list[tuple[str, float]]:
        """Rank candidate vectors by cosine similarity to the query, desc."""
        scored = [(doc_id, query.cosine_similarity(vector)) for doc_id, vector in vectors]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored

    def fuse(
        self,
        lexical: list[SearchHit],
        semantic: list[tuple[str, float]],
    ) -> list[FusedScore]:
        """Fuse two ranked lists into a single descending ranking.

        ``lexical`` is ordered best-first as returned by the FTS index;
        ``semantic`` is ordered best-first by cosine similarity.
        """
        lexical_component: dict[str, float] = {}
        for rank, hit in enumerate(lexical):
            lexical_component[hit.doc_id] = 1.0 / (self._k + rank + 1)

        semantic_component: dict[str, float] = {}
        similarity: dict[str, float] = {}
        for rank, (doc_id, sim) in enumerate(semantic):
            semantic_component[doc_id] = 1.0 / (self._k + rank + 1)
            similarity[doc_id] = sim

        all_ids = set(lexical_component) | set(semantic_component)
        fused = [
            FusedScore(
                doc_id=doc_id,
                score=lexical_component.get(doc_id, 0.0) + semantic_component.get(doc_id, 0.0),
                lexical=lexical_component.get(doc_id, 0.0),
                semantic=semantic_component.get(doc_id, 0.0),
                similarity=similarity.get(doc_id),
            )
            for doc_id in all_ids
        ]
        fused.sort(key=lambda f: (f.score, f.doc_id), reverse=True)
        return fused
