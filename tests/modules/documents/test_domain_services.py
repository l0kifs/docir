"""Unit tests for the documents domain services (Tiers 0/1/2, markdown)."""

from __future__ import annotations

from datetime import date

import pytest

from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.entities.relation import Relation
from docir.modules.documents.domain.schema import Schema, TypeSchema
from docir.modules.documents.domain.services.graph_checks import GraphChecker
from docir.modules.documents.domain.services.markdown_sections import (
    append_section,
    replace_section,
)
from docir.modules.documents.domain.services.similarity_lint import SimilarityLinter
from docir.modules.documents.domain.services.validation import Tier0Validator
from docir.modules.documents.domain.value_objects.relations import RelatedRef
from docir.platform.embedding.vector import Embedding
from docir.platform.errors import (
    DisallowedRelationError,
    MissingRequiredFieldError,
    UnknownRelatedError,
    UnknownRelationKindError,
    UnknownTagError,
    ValidationError,
)


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


def _typed_schema() -> Schema:
    # A registry of kinds, a permissive `decision`, and a constrained `issue`
    # that may only `implements` a `decision`.
    return Schema(
        types={
            "decision": TypeSchema(
                "decision", "adr", (), ("proposed",), "proposed", {"proposed": frozenset()}
            ),
            "issue": TypeSchema(
                "issue",
                "issue",
                (),
                ("open",),
                "open",
                {"open": frozenset()},
                allowed_relations={"implements": ("decision",), "relates_to": ()},
            ),
        },
        relation_types=frozenset({"relates_to", "implements", "supersedes"}),
    )


class TestRelationKindValidation:
    def test_allowed_kind_and_target_passes(self) -> None:
        validator = Tier0Validator(_typed_schema())
        validator.validate_relation_kinds(
            "issue", [RelatedRef("adr-0001", "implements")], {"adr-0001": "decision"}
        )

    def test_unknown_kind_rejected(self) -> None:
        validator = Tier0Validator(_typed_schema())
        with pytest.raises(UnknownRelationKindError):
            validator.validate_relation_kinds(
                "decision", [RelatedRef("adr-0001", "bogus")], {"adr-0001": "decision"}
            )

    def test_kind_not_whitelisted_for_source_rejected(self) -> None:
        validator = Tier0Validator(_typed_schema())
        with pytest.raises(DisallowedRelationError):
            validator.validate_relation_kinds(
                "issue", [RelatedRef("adr-0001", "supersedes")], {"adr-0001": "decision"}
            )

    def test_disallowed_target_type_rejected(self) -> None:
        validator = Tier0Validator(_typed_schema())
        with pytest.raises(DisallowedRelationError):
            validator.validate_relation_kinds(
                "issue", [RelatedRef("issue-0002", "implements")], {"issue-0002": "issue"}
            )

    def test_missing_target_deferred_to_existence_check(self) -> None:
        # An unknown target is left to validate_related; this must not raise.
        validator = Tier0Validator(_typed_schema())
        validator.validate_relation_kinds("issue", [RelatedRef("adr-9999", "implements")], {})


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

    def test_unknown_type_flagged(self) -> None:
        # A doc whose type is not in the active schema (e.g. a disabled profile).
        docs = [_doc("hyp-0001", "hypothesis")]
        issues = GraphChecker(_schema()).check(docs, [])
        assert any(i.kind == "unknown-type" and "hyp-0001" in i.doc_ids for i in issues)

    def test_supersedes_edge_exempt_from_layering(self) -> None:
        # A supersedes edge is lateral (replacement), not a downward dependency.
        docs = [_doc("arch-0001", "decision"), _doc("issue-0001", "issue")]
        rels = [Relation("arch-0001", "issue-0001", "supersedes")]
        issues = GraphChecker(_schema()).check(docs, rels)
        assert not any(i.kind == "layering" for i in issues)


def _stale_schema() -> Schema:
    return Schema(
        types={
            "decision": TypeSchema(
                "decision",
                "adr",
                (),
                ("proposed",),
                "proposed",
                {"proposed": frozenset()},
                review_days=30,
            )
        }
    )


class TestStalenessCheck:
    def test_stale_document_flagged(self) -> None:
        doc = _doc("adr-0001", updated=date(2026, 1, 1), owner="team")
        issues = GraphChecker(_stale_schema()).check([doc], [], today=date(2026, 7, 7))
        assert any(i.kind == "stale" and "team" in i.message for i in issues)

    def test_recent_verification_resets_the_clock(self) -> None:
        doc = _doc("adr-0001", updated=date(2026, 1, 1), verified=date(2026, 7, 1))
        issues = GraphChecker(_stale_schema()).check([doc], [], today=date(2026, 7, 7))
        assert not any(i.kind == "stale" for i in issues)

    def test_no_date_skips_staleness(self) -> None:
        doc = _doc("adr-0001", updated=date(2026, 1, 1))
        issues = GraphChecker(_stale_schema()).check([doc], [])
        assert not any(i.kind == "stale" for i in issues)


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
