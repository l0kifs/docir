"""Hybrid scoring tests for the indexing module."""

from __future__ import annotations

from docir.modules.indexing.domain.results import SearchHit
from docir.modules.indexing.domain.scoring import HybridScorer
from docir.platform.embedding.vector import Embedding


class TestHybridScorer:
    def test_semantic_ranking_orders_by_similarity(self) -> None:
        scorer = HybridScorer()
        query = Embedding((1.0, 0.0))
        vectors = [("a", Embedding((0.0, 1.0))), ("b", Embedding((1.0, 0.0)))]
        ranked = scorer.semantic_ranking(query, vectors)
        assert ranked[0][0] == "b"

    def test_fuse_combines_both_sources(self) -> None:
        scorer = HybridScorer(rrf_k=1)
        lexical = [SearchHit("a", 1.0), SearchHit("b", 2.0)]
        semantic = [("b", 0.9), ("c", 0.5)]
        fused = scorer.fuse(lexical, semantic)
        ids = [f.doc_id for f in fused]
        assert set(ids) == {"a", "b", "c"}
        # 'b' appears in both lists so it should rank first.
        assert fused[0].doc_id == "b"
        assert fused[0].lexical > 0 and fused[0].semantic > 0


class TestSimilarityIsCarriedThrough:
    """The raw cosine survives fusion (guards issue-93152f7b9213).

    RRF is rank-derived, so `score` says where a document placed and never how
    good the match was: against a store holding one unrelated document, a
    nonsense query returned it at the same magnitude a perfect match would. The
    cosine was computed, used to sort, and then discarded. Carrying it is what
    makes "nothing relevant exists" expressible.
    """

    def test_similarity_is_the_raw_cosine_not_the_rrf_component(self) -> None:
        scorer = HybridScorer(rrf_k=1)
        fused = scorer.fuse([], [("a", 0.9), ("b", 0.5)])
        by_id = {f.doc_id: f for f in fused}
        assert by_id["a"].similarity == 0.9
        assert by_id["b"].similarity == 0.5
        # The RRF component is rank-derived and differs from the cosine.
        assert by_id["a"].semantic != 0.9

    def test_lexical_only_hit_has_unknown_similarity(self) -> None:
        # No vector means *unknown*, not zero — a document retrieved by full
        # text alone must not be filtered out as if it had scored 0.0.
        scorer = HybridScorer(rrf_k=1)
        fused = scorer.fuse([SearchHit("a", 1.0)], [])
        assert fused[0].similarity is None

    def test_a_genuine_zero_similarity_is_not_none(self) -> None:
        scorer = HybridScorer(rrf_k=1)
        fused = scorer.fuse([], [("a", 0.0)])
        assert fused[0].similarity == 0.0
