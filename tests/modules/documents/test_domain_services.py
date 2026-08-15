"""Unit tests for the documents domain services (Tiers 0/1/2, markdown)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.entities.relation import Relation
from docir.modules.documents.domain.schema import RelationKindSchema, Schema, TypeSchema
from docir.modules.documents.domain.services import code_globs
from docir.modules.documents.domain.services.chunking import MAX_CHUNK_CHARS, split_body
from docir.modules.documents.domain.services.graph_checks import GraphChecker
from docir.modules.documents.domain.services.markdown_sections import (
    append_section,
    extract_section,
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


def _schema_requiring(*fields: str) -> Schema:
    """`_schema()`, with the `decision` type declaring `fields` as required."""
    types = dict(_schema().types)
    types["decision"] = replace(types["decision"], required_fields=fields)
    return Schema(types=types)


def _schema_registering(*kinds: str) -> Schema:
    """`_schema()`, with a relation registry that lists exactly `kinds`."""
    return Schema(types=dict(_schema().types), relation_types=frozenset(kinds))


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

    def test_an_empty_collection_counts_as_missing(self) -> None:
        # Once the loader guaranteed a `required:` name is a real field
        # (issue-e3c4dfad4f7b), `required: [tags]` became expressible — and a
        # string-only emptiness test accepted a document with no tags at all,
        # so the rule loaded, read as enforced, and enforced nothing.
        schema = Schema(
            types={
                "decision": TypeSchema(
                    "decision",
                    "adr",
                    ("tags",),
                    ("proposed",),
                    "proposed",
                    {"proposed": frozenset()},
                )
            }
        )
        validator = Tier0Validator(schema)
        with pytest.raises(MissingRequiredFieldError):
            validator.validate_required_fields(_doc("adr-0001", tags=()))
        validator.validate_required_fields(_doc("adr-0001", tags=("auth",)))

    def test_a_false_boolean_is_a_value_not_an_absence(self) -> None:
        # `archived: false` is the normal state of a document, not a missing
        # field — falsiness alone would reject every unarchived document.
        schema = Schema(
            types={
                "decision": TypeSchema(
                    "decision",
                    "adr",
                    ("archived",),
                    ("proposed",),
                    "proposed",
                    {"proposed": frozenset()},
                )
            }
        )
        Tier0Validator(schema).validate_required_fields(_doc("adr-0001", archived=False))

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
        rels = [
            Relation("adr-0001", "adr-0002", "supersedes"),
            Relation("adr-0002", "adr-0001", "supersedes"),
        ]
        issues = GraphChecker(_schema()).check(docs, rels)
        assert any(i.kind == "cycle" for i in issues)

    def test_a_mutual_relates_to_pair_is_not_a_cycle(self) -> None:
        """Guards issue-44875a5a6ca6: the default kind is symmetric.

        "A relates to B" and "B relates to A" are one statement written twice,
        so a pair that references each other is modelled correctly. Counting
        every kind made that a permanent warning: converting this store's prose
        cross-references into edges proposed 260 `relates_to` edges and turned a
        clean `check` into 127 cycles, so 120 correct edges were dropped instead.
        """
        docs = [_doc("adr-0001"), _doc("adr-0002")]
        rels = [Relation("adr-0001", "adr-0002"), Relation("adr-0002", "adr-0001")]
        issues = GraphChecker(_schema()).check(docs, rels)
        assert [i for i in issues if i.kind == "cycle"] == []

    def test_a_mutual_contradicts_pair_is_not_a_cycle(self) -> None:
        """`contradicts` is symmetric too — if A contradicts B, B contradicts A."""
        docs = [_doc("adr-0001"), _doc("adr-0002")]
        rels = [
            Relation("adr-0001", "adr-0002", "contradicts"),
            Relation("adr-0002", "adr-0001", "contradicts"),
        ]
        issues = GraphChecker(_schema()).check(docs, rels)
        assert [i for i in issues if i.kind == "cycle"] == []

    def test_a_schema_declared_symmetric_kind_is_not_a_cycle(self) -> None:
        """The point of making this schema data: a custom kind can say so."""
        schema = Schema(
            types=_schema().types,
            relation_types=frozenset({"duplicates"}),
            relation_kinds={"duplicates": RelationKindSchema("duplicates", symmetric=True)},
        )
        docs = [_doc("adr-0001"), _doc("adr-0002")]
        rels = [
            Relation("adr-0001", "adr-0002", "duplicates"),
            Relation("adr-0002", "adr-0001", "duplicates"),
        ]
        assert [i for i in GraphChecker(schema).check(docs, rels) if i.kind == "cycle"] == []

    def test_an_undeclared_custom_kind_is_still_cycle_checked(self) -> None:
        """A `blocks` deadlock is real; silence here would be a coverage loss."""
        docs = [_doc("adr-0001"), _doc("adr-0002")]
        rels = [
            Relation("adr-0001", "adr-0002", "blocks"),
            Relation("adr-0002", "adr-0001", "blocks"),
        ]
        assert any(i.kind == "cycle" for i in GraphChecker(_schema()).check(docs, rels))

    def test_a_schema_declared_dependency_kind_is_layering_checked(self) -> None:
        schema = Schema(
            types=_schema().types,
            relation_types=frozenset({"governs"}),
            relation_kinds={"governs": RelationKindSchema("governs", dependency=True)},
        )
        docs = [_doc("arch-0001", "decision"), _doc("issue-0001", "issue")]
        rels = [Relation("arch-0001", "issue-0001", "governs")]
        assert any(i.kind == "layering" for i in GraphChecker(schema).check(docs, rels))

    def test_a_self_edge_is_a_cycle_whatever_its_kind(self) -> None:
        """Symmetry excuses a mutual pair; it is what makes a self-edge empty.

        Narrowing the kinds nearly took this with it — `check` is the only thing
        that sees a self-edge a merge or a hand-edit wrote (issue-2ebfc018f29a),
        and the default kind is the one such an edge will carry.
        """
        docs = [_doc("adr-0001")]
        rels = [Relation("adr-0001", "adr-0001")]
        issues = GraphChecker(_schema()).check(docs, rels)
        assert any(i.kind == "cycle" for i in issues)

    def test_a_longer_directed_loop_is_still_a_cycle(self) -> None:
        """Narrowing the kinds must not narrow the check to pairs."""
        docs = [_doc("adr-0001"), _doc("adr-0002"), _doc("adr-0003")]
        rels = [
            Relation("adr-0001", "adr-0002", "depends_on"),
            Relation("adr-0002", "adr-0003", "refines"),
            Relation("adr-0003", "adr-0001", "implements"),
        ]
        issues = GraphChecker(_schema()).check(docs, rels)
        assert any(i.kind == "cycle" for i in issues)

    def test_a_symmetric_edge_cannot_complete_a_directed_loop(self) -> None:
        """The `relates_to` hop is not a step the loop may be closed through."""
        docs = [_doc("adr-0001"), _doc("adr-0002"), _doc("adr-0003")]
        rels = [
            Relation("adr-0001", "adr-0002", "supersedes"),
            Relation("adr-0002", "adr-0003"),
            Relation("adr-0003", "adr-0001", "supersedes"),
        ]
        issues = GraphChecker(_schema()).check(docs, rels)
        assert [i for i in issues if i.kind == "cycle"] == []

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
        """Guards issue-40d1792bc9f9: the default kind is not a dependency claim.

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

    def test_unknown_relation_kind_flagged(self) -> None:
        # The third hand-edit rule (issue-0e3d1d9c81d3). Tier 0 refuses to write
        # the kind while the corpus keeps holding it, and `check` was the one
        # command that should have said so and did not.
        docs = [_doc("adr-0001"), _doc("issue-0001", "issue", status="open")]
        rels = [Relation("issue-0001", "adr-0001", "governs")]
        issues = GraphChecker(_schema_registering("relates_to")).check(docs, rels)
        found = [i for i in issues if i.kind == "unknown-relation-kind"]
        assert len(found) == 1
        assert found[0].doc_ids == ("issue-0001", "adr-0001")
        assert "'governs'" in found[0].message

    def test_a_registry_that_registers_nothing_is_permissive(self) -> None:
        # An empty `relation_types` means unconstrained — the backward-compatible
        # default for a schema predating typed edges. Reporting there would fire
        # on every edge in every such corpus.
        docs = [_doc("adr-0001"), _doc("issue-0001", "issue", status="open")]
        rels = [Relation("issue-0001", "adr-0001", "anything")]
        issues = GraphChecker(_schema()).check(docs, rels)
        assert not any(i.kind == "unknown-relation-kind" for i in issues)

    def test_a_registered_kind_is_not_flagged(self) -> None:
        # The quiet-on-correct-usage guard.
        docs = [_doc("adr-0001"), _doc("issue-0001", "issue", status="open")]
        rels = [Relation("issue-0001", "adr-0001", "depends_on")]
        issues = GraphChecker(_schema_registering("relates_to", "depends_on")).check(docs, rels)
        assert not any(i.kind == "unknown-relation-kind" for i in issues)

    def test_unknown_relation_kind_is_a_warning(self) -> None:
        # The edge still resolves and still behaves — core properties resolve for
        # a kind the registry has stopped listing — so nothing is broken.
        docs = [_doc("adr-0001"), _doc("issue-0001", "issue", status="open")]
        rels = [Relation("issue-0001", "adr-0001", "governs")]
        issues = GraphChecker(_schema_registering("relates_to")).check(docs, rels)
        assert all(i.severity == "warning" for i in issues if i.kind == "unknown-relation-kind")

    def test_missing_required_field_flagged(self) -> None:
        # The upgrade case (issue-8f6576cd7bc9): the type starts requiring a
        # field that documents written before it never carried. No hand-edit is
        # involved, and until this check existed nothing reported it — the first
        # report was an unrelated `update` being refused.
        issues = GraphChecker(_schema_requiring("owner")).check([_doc("adr-0001")], [])
        found = [i for i in issues if i.kind == "missing-required"]
        assert [i.doc_ids for i in found] == [("adr-0001",)]
        assert "'owner'" in found[0].message

    def test_missing_required_names_every_absent_field_in_one_finding(self) -> None:
        # One finding per document, not per field: a schema requiring three
        # fields must not triple the output on a corpus that predates them.
        issues = GraphChecker(_schema_requiring("owner", "tags")).check([_doc("adr-0001")], [])
        found = [i for i in issues if i.kind == "missing-required"]
        assert len(found) == 1
        assert "'owner'" in found[0].message
        assert "'tags'" in found[0].message

    def test_missing_required_uses_the_same_emptiness_rule_as_tier_0(self) -> None:
        # `is_absent` is shared with the validator on purpose. An empty
        # collection counts as missing (so `required: [tags]` means "at least
        # one"), and `False` is a value rather than an absence. A second
        # definition here would let `check` call a document conforming that the
        # next write refuses.
        empty = _doc("adr-0001", tags=())
        assert any(
            i.kind == "missing-required"
            for i in GraphChecker(_schema_requiring("tags")).check([empty], [])
        )
        unarchived = _doc("adr-0002", archived=False)
        assert not any(
            i.kind == "missing-required"
            for i in GraphChecker(_schema_requiring("archived")).check([unarchived], [])
        )

    def test_missing_required_is_quiet_when_the_field_is_present(self) -> None:
        # The guard every new check needs: silent on correct usage, or it
        # teaches people to ignore the whole of `check` (issue-9cb85759076d).
        docs = [_doc("adr-0001", owner="platform-team")]
        issues = GraphChecker(_schema_requiring("owner")).check(docs, [])
        assert not any(i.kind == "missing-required" for i in issues)

    def test_missing_required_is_not_reported_for_an_unknown_type(self) -> None:
        # Same rule as `unknown-status`: there is no type schema to read a
        # `required` list from, and the cause is already reported once.
        docs = [_doc("hyp-0001", "hypothesis")]
        kinds = {i.kind for i in GraphChecker(_schema_requiring("owner")).check(docs, [])}
        assert "unknown-type" in kinds
        assert "missing-required" not in kinds

    def test_missing_required_is_a_warning(self) -> None:
        # A schema change ships in the package, so a corpus that passed
        # yesterday can fail today with no commit to point at. An error kind
        # would red-build every repo on that release.
        issues = GraphChecker(_schema_requiring("owner")).check([_doc("adr-0001")], [])
        assert all(i.severity == "warning" for i in issues if i.kind == "missing-required")

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


class TestCodeCheck:
    """The Tier 1 half of code linkage: a governed glob that matches nothing."""

    def test_a_code_glob_matching_nothing_is_a_warning_naming_the_pattern(self) -> None:
        doc = _doc("adr-0001", code=("src/gone/**", "src/here/*.py"))
        issues = GraphChecker(_schema()).check(
            [doc], [], code_matches={"src/gone/**": False, "src/here/*.py": True}
        )
        found = [i for i in issues if i.kind == "unmatched-code"]
        assert len(found) == 1
        # The message names the pattern that missed and not the one that hit —
        # a finding that says only "a glob is stale" costs a second lookup.
        assert "'src/gone/**'" in found[0].message
        assert "src/here" not in found[0].message
        assert found[0].severity == "warning"  # the code moved; nothing is broken

    def test_no_resolution_skips_the_code_check(self) -> None:
        # ``None`` is "there is no repository to ask", which is the global
        # store. Treating it as "matched nothing" would report every pattern.
        doc = _doc("adr-0001", code=("src/gone/**",))
        assert not any(i.kind == "unmatched-code" for i in GraphChecker(_schema()).check([doc], []))

    def test_a_pattern_nobody_resolved_is_not_reported(self) -> None:
        # Absent from the map is *unresolved*, not *missing* — the rule
        # `similarity` follows on the read paths. Defaulting the other way
        # invents a finding for a question that was never asked.
        doc = _doc("adr-0001", code=("src/unknown/**",))
        issues = GraphChecker(_schema()).check([doc], [], code_matches={"src/other/**": False})
        assert not any(i.kind == "unmatched-code" for i in issues)

    def test_an_archived_document_is_not_reported(self) -> None:
        doc = _doc("adr-0001", code=("src/gone/**",), archived=True)
        issues = GraphChecker(_schema()).check([doc], [], code_matches={"src/gone/**": False})
        assert not any(i.kind == "unmatched-code" for i in issues)


class TestCodeGlobs:
    """The pattern grammar `code` uses, matched against a path as text.

    Deliberately not a filesystem walk: `query --code` has to answer for a file
    a branch just deleted, which is when its decisions most need re-reading.
    """

    @pytest.mark.parametrize(
        ("pattern", "path", "expected"),
        [
            ("src/auth/**", "src/auth/login.py", True),
            ("src/auth/**", "src/auth/deep/nested.py", True),
            ("src/auth/**", "src/auth", True),  # the directory itself
            ("src/auth/**", "src/authorize.py", False),  # not a segment prefix
            ("src/*.py", "src/a.py", True),
            ("src/*.py", "src/sub/a.py", False),  # `*` never crosses a separator
            ("**/*.py", "a/b/c.py", True),
            ("**/*.py", "c.py", True),  # `**` matches zero segments
            ("**", "anything/at/all.py", True),
            ("src/[ab]*.py", "src/apple.py", True),
            ("src/[!ab]*.py", "src/apple.py", False),
            ("src/a?.py", "src/ab.py", True),
            ("src/a?.py", "src/abc.py", False),
            ("src/auth", "src/auth/login.py", True),  # a directory governs its files
            ("src/auth", "src/auth", True),
            ("src/auth", "src/other.py", False),
            ("src/auth/**", "./src/auth/login.py", True),  # a `./` prefix is noise
            ("src/[unclosed", "src/[unclosed", True),  # a bad class is a literal
            ("src/**", "", False),
        ],
    )
    def test_grammar(self, pattern: str, path: str, expected: bool) -> None:
        assert code_globs.matches(pattern, path) is expected

    def test_governs_any_is_any_pattern_against_any_path(self) -> None:
        patterns = ("src/auth/**", "docs/*.md")
        assert code_globs.governs_any(patterns, ("README.md", "docs/guide.md"))
        assert not code_globs.governs_any(patterns, ("README.md", "src/api/routes.py"))
        assert not code_globs.governs_any((), ("src/auth/login.py",))


class TestSimilarityLinter:
    def test_duplicates_flagged(self) -> None:
        vectors = [("a", Embedding((1.0, 0.0))), ("b", Embedding((1.0, 0.0)))]
        findings = SimilarityLinter(similarity_threshold=0.9).find_duplicates(vectors)
        assert findings and findings[0].kind == "duplicate"

    def test_a_linked_pair_is_not_reported(self) -> None:
        """issue-08437ba704ff: the edge is the answer to "why are these two similar?".

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

    def test_a_section_within_the_window_is_not_flagged(self) -> None:
        body = "## Context\n\n" + "x" * (MAX_CHUNK_CHARS - 20) + "\n"
        assert SimilarityLinter().find_oversized_sections([_doc("adr-0001", body=body)]) == []

    def test_a_split_section_is_flagged_with_what_it_cost(self) -> None:
        # Not a taste threshold: the check runs the splitter and reports what
        # came out, so the number behind it is the measured model window.
        body = "## Context\n\n" + "\n\n".join(["y" * 900] * 3) + "\n"
        findings = SimilarityLinter().find_oversized_sections([_doc("adr-0001", body=body)])
        assert [f.kind for f in findings] == ["oversized-section"]
        assert "'Context'" in findings[0].message
        assert findings[0].doc_ids == ("adr-0001",)

    def test_the_count_it_reports_is_the_chunker_s_own(self) -> None:
        """A guard that recomputes the answer cannot drift from the thing it describes."""
        body = "## Context\n\n" + "\n\n".join(["y" * 900] * 5) + "\n"
        doc = _doc("adr-0001", body=body)
        findings = SimilarityLinter().find_oversized_sections([doc])
        unaddressable = sum(1 for c in split_body(doc.body) if not c.heading and c.ordinal > 0)
        assert unaddressable > 1, "the fixture stopped exercising a multi-way split"
        assert f"{unaddressable} of them" in findings[0].message

    def test_a_preamble_is_not_blamed_on_a_section(self) -> None:
        # Text before the first heading has no heading to lose, so splitting it
        # costs no address and must not be reported as if it did.
        body = "\n\n".join(["y" * 900] * 3) + "\n\n## Context\n\nshort.\n"
        assert SimilarityLinter().find_oversized_sections([_doc("adr-0001", body=body)]) == []

    def test_each_split_section_is_reported_separately(self) -> None:
        long_text = "\n\n".join(["y" * 900] * 2)
        body = f"## One\n\n{long_text}\n\n## Two\n\n{long_text}\n"
        findings = SimilarityLinter().find_oversized_sections([_doc("adr-0001", body=body)])
        assert len(findings) == 2
        assert "'One'" in findings[0].message and "'Two'" in findings[1].message

    def test_a_bodyless_document_is_silent(self) -> None:
        assert SimilarityLinter().find_oversized_sections([_doc("adr-0001", body="")]) == []

    def test_a_heading_used_twice_is_flagged(self) -> None:
        # issue-71555a89a73d: `--section` resolves to the first match, so the
        # second is reachable only by fetching the whole body — silently.
        body = "## Findings\n\nfirst pass.\n\n## Other\n\nx\n\n## Findings\n\nsecond pass.\n"
        findings = SimilarityLinter().find_ambiguous_headings([_doc("adr-0001", body=body)])
        assert [f.kind for f in findings] == ["ambiguous-heading"]
        assert "'Findings'" in findings[0].message and "2 times" in findings[0].message

    def test_distinct_headings_are_silent(self) -> None:
        body = "## One\n\na\n\n## Two\n\nb\n"
        assert SimilarityLinter().find_ambiguous_headings([_doc("adr-0001", body=body)]) == []

    def test_a_heading_repeated_inside_a_fence_is_not_ambiguous(self) -> None:
        # Shares the fence-aware scanner, so quoted markdown is not structure.
        body = "## Findings\n\n```markdown\n## Findings\n```\n"
        assert SimilarityLinter().find_ambiguous_headings([_doc("adr-0001", body=body)]) == []


class TestUnqualifiedSectionRefs:
    """Guards the failure a document split leaves behind, and its two false starts."""

    def _docs(self, *bodies: tuple[str, str]) -> list[Document]:
        return [_doc(doc_id, body=body) for doc_id, body in bodies]

    def test_a_reference_to_a_relocated_section_is_flagged(self) -> None:
        docs = self._docs(
            ("adr-0001", 'see "Archiving vs. deletion" below for the rest\n'),
            ("adr-0002", "## Archiving vs. deletion\n\nhow it works\n"),
        )
        findings = SimilarityLinter().find_unqualified_section_refs(docs)
        assert [f.kind for f in findings] == ["unqualified-section-ref"]
        assert "'adr-0002'" in findings[0].message
        assert findings[0].doc_ids == ("adr-0001", "adr-0002")

    def test_naming_the_owning_document_clears_it(self) -> None:
        # What the fix looks like — the check has to recognise its own remedy or
        # it reports the same line forever.
        docs = self._docs(
            ("adr-0001", 'see `adr-0002`, "Archiving vs. deletion" for the rest\n'),
            ("adr-0002", "## Archiving vs. deletion\n\nhow it works\n"),
        )
        assert SimilarityLinter().find_unqualified_section_refs(docs) == []

    def test_a_heading_many_documents_share_is_never_flagged(self) -> None:
        """The first run reported this and was wrong, twice over.

        `Resolution` is a heading in dozens of issues, so quoting the word was
        enough to trip it; and with several owners the "it lives in X" clause
        picked one arbitrarily and named the wrong document. A check that cannot
        say which document is not entitled to the sentence.
        """
        docs = self._docs(
            ("adr-0001", 'the "Resolution" section explains it\n'),
            ("issue-0002", "## Resolution\n\nfixed\n"),
            ("issue-0003", "## Resolution\n\nalso fixed\n"),
        )
        assert SimilarityLinter().find_unqualified_section_refs(docs) == []

    def test_a_quoted_phrase_that_is_nobody_s_heading_is_ignored(self) -> None:
        docs = self._docs(("adr-0001", 'he called it "Some Ordinary Phrase" once\n'))
        assert SimilarityLinter().find_unqualified_section_refs(docs) == []

    def test_quoting_your_own_heading_is_fine(self) -> None:
        docs = self._docs(("adr-0001", '## Context\n\nsee "Context" above\n'))
        assert SimilarityLinter().find_unqualified_section_refs(docs) == []

    def test_each_stale_reference_is_reported_once(self) -> None:
        docs = self._docs(
            ("adr-0001", 'both "Archiving vs. deletion" and again "Archiving vs. deletion"\n'),
            ("adr-0002", "## Archiving vs. deletion\n\nhow it works\n"),
        )
        assert len(SimilarityLinter().find_unqualified_section_refs(docs)) == 1


class TestSimilarityLinterSizes:
    def test_scope_creep_flagged(self) -> None:
        big = _doc("adr-0001", body="x" * 10)
        findings = SimilarityLinter(size_threshold_chars=5).find_scope_creep([big])
        assert findings and findings[0].kind == "scope-creep"

    def test_a_type_may_opt_out_of_the_size_check(self) -> None:
        """issue-5d6a5e854d11: one threshold for every type made a register always too long.

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


class TestSectionHeadingsAreNamedByTextAlone:
    """`--append-section "## X"` wrote `## ## X` and said nothing.

    The flag takes the heading *text* and writes the `##` itself, so passing the
    line as it appears in the file doubled it. Neither section-edit mode could
    repair a heading line — `replace_section` keeps it by contract and appending
    again adds a sibling — so the safest body edit reached a state only
    `--replace-body --force` could leave (issue-d5f68b44b1d9).
    """

    def test_append_refuses_a_heading_carrying_its_own_markers(self) -> None:
        with pytest.raises(ValidationError) as raised:
            append_section("", "## Resolution", "Fixed it")
        message = str(raised.value)
        assert "'## Resolution'" in message
        assert "'Resolution'" in message, "the error must name the argument that works"

    @pytest.mark.parametrize("heading", ["# Top", "### Deep", "  ## Padded", "#NoSpace"])
    def test_append_refuses_every_level_of_marker(self, heading: str) -> None:
        with pytest.raises(ValidationError):
            append_section("", heading, "x")

    def test_a_hash_inside_the_text_is_still_a_heading(self) -> None:
        # The guard is about a *leading* marker; "C# interop" is a real heading
        # and rejecting it would trade one silent failure for a loud wrong one.
        assert append_section("", "C# interop", "x").startswith("## C# interop\n")

    def test_the_mirror_mistake_on_replace_names_the_real_headings(self) -> None:
        # Passing "## A" to --replace-section answered "no matching heading
        # found" and left the caller to guess which spelling was wanted.
        with pytest.raises(ValidationError) as raised:
            replace_section("## A\n\ntext", "## A", "new")
        assert "'A'" in str(raised.value)

    def test_a_hand_written_doubled_heading_stays_readable(self) -> None:
        # Reading corrupts nothing and hand-editing markdown is permitted, so
        # the guard must not lock someone out of the file they need to repair.
        body = "## ## Resolution\n\nhello\n"
        assert extract_section(body, "## Resolution").startswith("## ## Resolution")
