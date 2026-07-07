"""Unit tests for the pure domain services (Tiers 0/1/2, scoring, markdown)."""

from __future__ import annotations

from datetime import date

import pytest

from docir.domain.entities.document import Document
from docir.domain.entities.relation import Relation
from docir.domain.errors import (
    MissingRequiredFieldError,
    UnknownRelatedError,
    UnknownTagError,
    ValidationError,
)
from docir.domain.schema import Schema, TypeSchema
from docir.domain.services.graph_checks import GraphChecker
from docir.domain.services.markdown_sections import append_section, replace_section
from docir.domain.services.scoring import HybridScorer
from docir.domain.services.similarity_lint import SimilarityLinter
from docir.domain.services.validation import Tier0Validator
from docir.domain.value_objects.embedding import Embedding
from docir.domain.value_objects.results import SearchHit


def _schema() -> Schema:
    return Schema(
        types={
            "decision": TypeSchema(
                "decision",
                "adr",
                (),
                ("proposed", "accepted"),
                "proposed",
                {"proposed": frozenset({"accepted"}), "accepted": frozenset()},
                level=3,
            ),
            "issue": TypeSchema(
                "issue",
                "issue",
                (),
                ("open", "resolved"),
                "open",
                {"open": frozenset({"resolved"}), "resolved": frozenset()},
                level=1,
            ),
        }
    )


def _doc(doc_id: str, doc_type: str = "decision", **kw: object) -> Document:
    defaults: dict[str, object] = {
        "title": "T",
        "description": "D",
        "status": "proposed",
        "created": date(2026, 1, 1),
        "updated": date(2026, 1, 1),
    }
    defaults.update(kw)
    return Document(id=doc_id, type=doc_type, **defaults)  # type: ignore[arg-type]


class TestTier0Validator:
    def test_missing_required_field(self) -> None:
        validator = Tier0Validator(_schema())
        with pytest.raises(MissingRequiredFieldError):
            validator.validate_required_fields(_doc("adr-0001", title="  "))

    def test_unknown_tag(self) -> None:
        validator = Tier0Validator(_schema())
        with pytest.raises(UnknownTagError):
            validator.validate_tags(["ghost"], ["auth"])

    def test_unknown_related(self) -> None:
        validator = Tier0Validator(_schema())
        with pytest.raises(UnknownRelatedError):
            validator.validate_related(["adr-9999"], ["adr-0001"])

    def test_valid_passes(self) -> None:
        validator = Tier0Validator(_schema())
        validator.validate_required_fields(_doc("adr-0001"))
        validator.validate_tags(["auth"], ["auth"])
        validator.validate_related(["adr-0001"], ["adr-0001"])


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


class TestGraphChecker:
    def test_orphan_detected(self) -> None:
        issues = GraphChecker(_schema()).check([_doc("adr-0001")], [])
        assert any(i.kind == "orphan" for i in issues)

    def test_cycle_detected(self) -> None:
        docs = [_doc("adr-0001"), _doc("adr-0002")]
        rels = [Relation("adr-0001", "adr-0002"), Relation("adr-0002", "adr-0001")]
        issues = GraphChecker(_schema()).check(docs, rels)
        assert any(i.kind == "cycle" for i in issues)

    def test_layering_violation(self) -> None:
        docs = [_doc("arch-0001", "decision"), _doc("issue-0001", "issue")]
        # decision(level 3) -> issue(level 1) is a downward dependency.
        rels = [Relation("arch-0001", "issue-0001")]
        issues = GraphChecker(_schema()).check(docs, rels)
        assert any(i.kind == "layering" for i in issues)

    def test_no_issues_when_healthy(self) -> None:
        docs = [_doc("adr-0001"), _doc("issue-0001", "issue", status="open")]
        rels = [Relation("issue-0001", "adr-0001")]
        issues = GraphChecker(_schema()).check(docs, rels)
        assert issues == []

    def test_dangling_relation_detected(self) -> None:
        docs = [_doc("issue-0001", "issue", status="open")]
        # target adr-9999 does not exist (e.g. deleted on another branch).
        rels = [Relation("issue-0001", "adr-9999")]
        issues = GraphChecker(_schema()).check(docs, rels)
        assert any(i.kind == "dangling" for i in issues)


class TestSimilarityLinter:
    def test_duplicates_flagged(self) -> None:
        vectors = [("a", Embedding((1.0, 0.0))), ("b", Embedding((1.0, 0.0)))]
        findings = SimilarityLinter(similarity_threshold=0.9).find_duplicates(vectors)
        assert findings and findings[0].kind == "duplicate"

    def test_scope_creep_flagged(self) -> None:
        big = _doc("adr-0001", body="x" * 10)
        findings = SimilarityLinter(size_threshold_chars=5).find_scope_creep([big])
        assert findings and findings[0].kind == "scope-creep"


class TestMarkdownSections:
    def test_append_section_on_empty(self) -> None:
        result = append_section("", "Resolution", "Fixed it")
        assert result == "## Resolution\n\nFixed it\n"

    def test_append_section_keeps_existing(self) -> None:
        result = append_section("# Intro\n\ntext", "More", "extra")
        assert "# Intro" in result
        assert result.strip().endswith("extra")

    def test_replace_section(self) -> None:
        body = "## A\n\nold\n\n## B\n\nkeep"
        result = replace_section(body, "A", "new")
        assert "new" in result
        assert "old" not in result
        assert "keep" in result

    def test_replace_missing_section_raises(self) -> None:
        with pytest.raises(ValidationError):
            replace_section("## A\n\ntext", "Z", "new")
