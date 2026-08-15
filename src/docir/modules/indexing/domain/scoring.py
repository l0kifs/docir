"""Hybrid scoring for ``docir context`` — fuse lexical and semantic ranks.

Rather than replacing FTS5 outright (lexical matches are valuable and cheap),
the context read path combines the BM25 ranking with cosine-similarity ranking.
Reciprocal Rank Fusion (RRF) is used: it is scale-free, so it sidesteps the
problem of BM25 scores and cosine scores living on incomparable numeric ranges.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from docir.modules.indexing.domain.results import SearchHit, VectorCandidate
from docir.platform.embedding.vector import Embedding

# RRF dampening constant; 60 is the value from the original RRF paper.
DEFAULT_RRF_K = 60


@dataclass(frozen=True, slots=True)
class SemanticHit:
    """One document's best cosine similarity, and where in it that was found.

    ``section`` is the heading of the winning chunk, or ``None`` when the
    document's own vector won (or the winning chunk has no heading). Absent
    means "the match is not addressable as a section", never "no section
    matched".
    """

    doc_id: str
    similarity: float
    section: str | None = None


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
    #: The heading of the section whose vector produced ``similarity``, when one
    #: did. ``None`` for a lexical-only hit, and for a document matched by its
    #: own vector — in both cases the match is not addressable as a section.
    section: str | None = None


class HybridScorer:
    """Combines lexical (BM25) and semantic (cosine) rankings via RRF."""

    def __init__(self, rrf_k: int = DEFAULT_RRF_K) -> None:
        self._k = rrf_k

    def semantic_ranking(
        self, query: Embedding, candidates: Sequence[VectorCandidate]
    ) -> list[SemanticHit]:
        """Rank candidate vectors by cosine similarity to the query, desc.

        Accepts repeated ``doc_id`` entries and keeps each document's **best**
        one — that is what turns per-section chunk vectors back into a document
        ranking (adr-927aa43d9635). RRF fuses two rankings *of documents*, so the
        collapse has to happen before fusion, not after it.

        Max rather than mean: a document is relevant when *some* part of it
        answers the query, and averaging in five sections about something else
        is precisely the dilution chunking exists to undo. The consequence,
        recorded rather than hidden, is that more sections mean more chances to
        score — which is why the benchmark gates on no recall regression.

        The collapse keeps the *winning candidate*, not just its score, so the
        section that earned a document its rank survives into the result. It was
        discarded here for as long as chunking existed, which left an agent told
        which document matched and guessing which section to read back
        (issue-afd25273ff1f).
        """
        best: dict[str, SemanticHit] = {}
        for candidate in candidates:
            similarity = query.cosine_similarity(candidate.vector)
            current = best.get(candidate.doc_id)
            if current is None or similarity > current.similarity:
                best[candidate.doc_id] = SemanticHit(
                    doc_id=candidate.doc_id,
                    similarity=similarity,
                    section=candidate.section,
                )
        return sorted(best.values(), key=lambda hit: (hit.similarity, hit.doc_id), reverse=True)

    def fuse(
        self,
        lexical: list[SearchHit],
        semantic: list[SemanticHit],
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
        section: dict[str, str | None] = {}
        for rank, semantic_hit in enumerate(semantic):
            semantic_component[semantic_hit.doc_id] = 1.0 / (self._k + rank + 1)
            similarity[semantic_hit.doc_id] = semantic_hit.similarity
            section[semantic_hit.doc_id] = semantic_hit.section

        all_ids = set(lexical_component) | set(semantic_component)
        fused = [
            FusedScore(
                doc_id=doc_id,
                score=lexical_component.get(doc_id, 0.0) + semantic_component.get(doc_id, 0.0),
                lexical=lexical_component.get(doc_id, 0.0),
                semantic=semantic_component.get(doc_id, 0.0),
                similarity=similarity.get(doc_id),
                section=section.get(doc_id),
            )
            for doc_id in all_ids
        ]
        fused.sort(key=lambda f: (f.score, f.doc_id), reverse=True)
        return fused
