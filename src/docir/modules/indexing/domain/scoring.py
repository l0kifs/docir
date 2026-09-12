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
    #: Where the document placed in each input list, 1-based, or ``None`` when
    #: that backend did not return it at all. Kept because the RRF component
    #: alone cannot be read back: ``lexical`` is ``1/(k+rank+1)``, so a reader
    #: holding 0.0156 has to invert the constant to learn it placed third
    #: (issue-d3278330eb63). Absent means *this backend did not find it*, which
    #: is the most useful single fact about a hit that ranked badly.
    lexical_rank: int | None = None
    semantic_rank: int | None = None


def _turn_order(rankings: list[list[FusedScore]]) -> list[str]:
    """The ids of per-query rankings merged by taking turns, first query first.

    A structural floor rather than a weight: with N queries the caller's task
    holds every Nth slot no matter what the others rank. That is what makes it
    survive a bad phrasing where weighting could not — weighting suppresses an
    extra query everywhere, including the documents only it can find, while
    taking turns bounds its *share* and leaves its best pick intact.

    Measured on docir's own corpus with one deliberately wrong hypothetical
    (adr-4c21693aac55): pooled RRF scored 0.25 recall@5 against this at 0.75,
    and neither lost anything on the correct hypothetical, which both take from
    0.88 to 1.00.
    """
    order: list[str] = []
    seen: set[str] = set()
    for depth in range(max((len(ranking) for ranking in rankings), default=0)):
        for ranking in rankings:
            if depth < len(ranking) and ranking[depth].doc_id not in seen:
                seen.add(ranking[depth].doc_id)
                order.append(ranking[depth].doc_id)
    return order


@dataclass(slots=True)
class _Fusion:
    """One document's fusion terms, accumulating across every pass.

    Six parallel dictionaries keyed on the same ``doc_id`` said this less
    clearly, and made "present in one of them, missing from another" a state
    every reader of the six had to hold in their head. As one record it is a
    state that cannot be written down.

    ``lexical``/``semantic`` sum across passes; the three "best" fields keep the
    single best pass, because a rank, a similarity and a section each describe
    one match and averaging them describes none.
    """

    lexical: float = 0.0
    semantic: float = 0.0
    lexical_rank: int | None = None
    semantic_rank: int | None = None
    similarity: float | None = None
    section: str | None = None

    def add_lexical(self, rank: int, contribution: float) -> None:
        self.lexical += contribution
        self.lexical_rank = _better(self.lexical_rank, rank)

    def add_semantic(self, rank: int, contribution: float, hit: SemanticHit) -> None:
        self.semantic += contribution
        self.semantic_rank = _better(self.semantic_rank, rank)
        # The similarity and section of the *best* pass, for the same reason the
        # rank is: they describe one match, not an average.
        #
        # The floor is -1.0 rather than "unset", which is what the dictionary
        # this replaces defaulted to. Cosine similarity bottoms out there, so a
        # first hit of exactly -1.0 records no similarity — preserved on purpose
        # rather than tidied, because this is a refactoring.
        if hit.similarity > (-1.0 if self.similarity is None else self.similarity):
            self.similarity = hit.similarity
            self.section = hit.section

    def to_score(self, doc_id: str) -> FusedScore:
        return FusedScore(
            doc_id=doc_id,
            score=self.lexical + self.semantic,
            lexical=self.lexical,
            semantic=self.semantic,
            similarity=self.similarity,
            section=self.section,
            lexical_rank=self.lexical_rank,
            semantic_rank=self.semantic_rank,
        )


def _better(current: int | None, rank: int) -> int:
    """The better (lower) of a recorded rank and a new one."""
    return rank if current is None or rank < current else current


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
        """Fuse one query's two ranked lists into a single descending ranking.

        ``lexical`` is ordered best-first as returned by the FTS index;
        ``semantic`` is ordered best-first by cosine similarity.
        """
        return self.fuse_many([(lexical, semantic)])

    def fuse_many(
        self,
        passes: Sequence[tuple[list[SearchHit], list[SemanticHit]]],
    ) -> list[FusedScore]:
        """Fuse every backend list of every query into one ranking.

        RRF is defined over any number of ranked lists, so N queries is the same
        operation one query already was — 2N lists rather than 2, summed per
        document. Fusing each query separately and then fusing the results would
        be a different function: it normalises away how *many* queries found a
        document, which is the signal several queries exist to produce
        (issue-fd086c0c6ab0).

        Every query weighs the same, and with more than one they **take turns**
        rather than pooling their scores. Weighting was tried first and answered
        (adr-b23dae55666f): it removes the gain along with the risk, because an
        extra query is powerful exactly to the degree it can outvote the task.
        Interleaving separates the two — the caller's task holds every Nth slot
        whatever the others rank, so a bad phrasing costs a bounded share of the
        result instead of most of it, while a good one keeps every document only
        it found.

        The reported ranks are the **best** each document achieved in any pass,
        because a rank is only meaningful against one list and "it placed first
        for one of your queries" is the fact a reader wants.
        """

        fusions: dict[str, _Fusion] = {}

        def of(doc_id: str) -> _Fusion:
            return fusions.setdefault(doc_id, _Fusion())

        for lexical, semantic in passes:
            for rank, hit in enumerate(lexical):
                of(hit.doc_id).add_lexical(rank + 1, 1.0 / (self._k + rank + 1))

            seen_here: set[str] = set()
            for rank, semantic_hit in enumerate(semantic):
                # `semantic_ranking` already collapsed each document to its best
                # chunk, so a repeat inside one pass cannot happen; across
                # passes it can, and only the first (best) one counts per pass.
                if semantic_hit.doc_id in seen_here:
                    continue
                seen_here.add(semantic_hit.doc_id)
                of(semantic_hit.doc_id).add_semantic(
                    rank + 1, 1.0 / (self._k + rank + 1), semantic_hit
                )

        fused = [fusion.to_score(doc_id) for doc_id, fusion in fusions.items()]
        fused.sort(key=lambda f: (f.score, f.doc_id), reverse=True)
        if len(passes) == 1:
            return fused
        # Pooling decides each document's *numbers*; taking turns decides the
        # *order*. Keeping both is what lets a document found by two queries
        # still report its best similarity while no single query fills the head
        # of the result (adr-4c21693aac55).
        by_id = {score.doc_id: score for score in fused}
        per_query = [self.fuse(lexical, semantic) for lexical, semantic in passes]
        return [by_id[doc_id] for doc_id in _turn_order(per_query) if doc_id in by_id]
