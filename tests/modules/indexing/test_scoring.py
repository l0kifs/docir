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
