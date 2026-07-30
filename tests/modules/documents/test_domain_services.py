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
        # decision(level 3) depends_on issue(level 1) is a downward dependency.
        rels = [Relation("arch-0001", "issue-0001", "depends_on")]
        issues = GraphChecker(_schema()).check(docs, rels)
        assert any(i.kind == "layering" for i in issues)

    def test_refines_edge_is_also_a_dependency(self) -> None:
        docs = [_doc("arch-0001", "decision"), _doc("issue-0001", "issue")]
        rels = [Relation("arch-0001", "issue-0001", "refines")]
        issues = GraphChecker(_schema()).check(docs, rels)
        assert any(i.kind == "layering" for i in issues)

    def test_relates_to_never_reports_layering(self) -> None:
        """Guards GAP-008: the default kind is not a dependency claim.

        `relates_to` is what every bare id in `related:` becomes, so when the
        check exempted only supersedes/contradicts, a decision linking the issue
        that motivated it — the pairing in the README's own quickstart — was a
        permanent violation with no way to silence it. Users who cannot make a
        warning stop learn to ignore `docs check`, and duplicate-id detection
        lives there too.
        """
        docs = [_doc("arch-0001", "decision"), _doc("issue-0001", "issue")]
        rels = [Relation("arch-0001", "issue-0001")]  # default kind
        issues = GraphChecker(_schema()).check(docs, rels)
        assert not any(i.kind == "layering" for i in issues)

    def test_implements_edge_is_not_a_dependency(self) -> None:
        # `implements` points impl -> spec by its nature; the direction carries
        # no claim about which document is allowed to rely on which.
        docs = [_doc("arch-0001", "decision"), _doc("issue-0001", "issue")]
        rels = [Relation("arch-0001", "issue-0001", "implements")]
        issues = GraphChecker(_schema()).check(docs, rels)
        assert not any(i.kind == "layering" for i in issues)

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

    def test_unknown_status_flagged(self) -> None:
        # Tier 0 validates every status the CLI writes, so this can only come
        # from a hand-edit or a merge — and `check` used to be blind to it.
        docs = [_doc("adr-0001", "decision", status="invented")]
        issues = GraphChecker(_schema()).check(docs, [])
        assert any(i.kind == "unknown-status" and "adr-0001" in i.doc_ids for i in issues)

    def test_unknown_status_is_not_reported_for_an_unknown_type(self) -> None:
        # Already covered by `unknown-type`; two findings for one cause is noise.
        docs = [_doc("hyp-0001", "hypothesis", status="whatever")]
        kinds = {i.kind for i in GraphChecker(_schema()).check(docs, [])}
        assert "unknown-type" in kinds
        assert "unknown-status" not in kinds

    def test_unknown_tag_flagged_against_the_registry(self) -> None:
        docs = [_doc("adr-0001", "decision", tags=("ghost",))]
        issues = GraphChecker(_schema()).check(docs, [], known_tags=frozenset({"auth"}))
        assert any(i.kind == "unknown-tag" and "adr-0001" in i.doc_ids for i in issues)

    def test_registered_tags_are_silent(self) -> None:
        docs = [_doc("adr-0001", "decision", tags=("auth",))]
        issues = GraphChecker(_schema()).check(docs, [], known_tags=frozenset({"auth"}))
        assert not any(i.kind == "unknown-tag" for i in issues)

    def test_tags_are_unchecked_when_no_registry_is_supplied(self) -> None:
        # Permissive-when-absent, like the relation-kind registry: a caller that
        # cannot supply the registry must not get false findings.
        docs = [_doc("adr-0001", "decision", tags=("ghost",))]
        issues = GraphChecker(_schema()).check(docs, [])
        assert not any(i.kind == "unknown-tag" for i in issues)

    def test_supersedes_edge_is_not_a_dependency(self) -> None:
        # A supersedes edge is lateral (replacement), not a downward dependency.
        docs = [_doc("arch-0001", "decision"), _doc("issue-0001", "issue")]
        rels = [Relation("arch-0001", "issue-0001", "supersedes")]
        issues = GraphChecker(_schema()).check(docs, rels)
        assert not any(i.kind == "layering" for i in issues)


def _schema_with_limits(limits: dict[str, int | None]) -> Schema:
    """A schema whose types differ only in their `max_body_chars`."""
    return Schema(
        types={
            name: TypeSchema(
                name,
                name[:3],
                (),
                ("proposed",),
                "proposed",
                {"proposed": frozenset()},
                max_body_chars=limit,
            )
            for name, limit in limits.items()
        }
    )


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

    def test_a_linked_pair_is_not_reported(self) -> None:
        """GAP-055: the edge is the answer to "why are these two similar?".

        Every one of the 14 duplicate findings against docir's own corpus was a
        pair the author had linked on purpose, which leaves the reader nothing
        to do but delete a document or unlink a correct relation.
        """
        vectors = [("a", Embedding((1.0, 0.0))), ("b", Embedding((1.0, 0.0)))]
        linter = SimilarityLinter(similarity_threshold=0.9)
        assert linter.find_duplicates(vectors, [frozenset(("a", "b"))]) == []
        # direction is not part of the question
        assert linter.find_duplicates(vectors, [frozenset(("b", "a"))]) == []
        # and an unrelated edge does not silence the pair
        assert linter.find_duplicates(vectors, [frozenset(("a", "c"))])

    def test_an_unlinked_duplicate_is_still_reported(self) -> None:
        # The case the check exists for. Without this, "no duplicates" and
        # "duplicates are never reported" look identical.
        vectors = [("a", Embedding((1.0, 0.0))), ("b", Embedding((1.0, 0.0)))]
        findings = SimilarityLinter(similarity_threshold=0.9).find_duplicates(vectors, [])
        assert [f.kind for f in findings] == ["duplicate"]
        assert findings[0].doc_ids == ("a", "b")

    def test_scope_creep_flagged(self) -> None:
        big = _doc("adr-0001", body="x" * 10)
        findings = SimilarityLinter(size_threshold_chars=5).find_scope_creep([big])
        assert findings and findings[0].kind == "scope-creep"

    def test_a_type_may_opt_out_of_the_size_check(self) -> None:
        """GAP-056: one threshold for every type made a register always too long.

        A glossary or a rule register split in half is two half-registers, so
        the advice could not be taken — the failure mode `orphan` had under
        `--strict`, a warning that fires on correct usage.
        """
        schema = _schema_with_limits({"decision": None, "reference": 0})
        linter = SimilarityLinter(size_threshold_chars=5)
        register = _doc("ref-0001", doc_type="reference", body="x" * 10)
        assert linter.find_scope_creep([register], schema) == []
        # and a type that did not opt out is still flagged
        flagged = linter.find_scope_creep([_doc("adr-0001", body="x" * 10)], schema)
        assert [f.kind for f in flagged] == ["scope-creep"]

    def test_a_type_may_set_its_own_limit(self) -> None:
        schema = _schema_with_limits({"decision": 100})
        linter = SimilarityLinter(size_threshold_chars=5)
        assert linter.find_scope_creep([_doc("adr-0001", body="x" * 10)], schema) == []
        assert linter.find_scope_creep([_doc("adr-0001", body="x" * 200)], schema)

    def test_without_a_schema_the_flat_default_applies(self) -> None:
        # The domain service stays usable standalone, as it was before.
        big = _doc("adr-0001", body="x" * 10)
        assert SimilarityLinter(size_threshold_chars=5).find_scope_creep([big])


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
