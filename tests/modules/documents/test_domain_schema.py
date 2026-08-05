"""Unit tests for the schema domain object and its validation."""

from __future__ import annotations

import pytest

from docir.modules.documents.domain.schema import RelationKindSchema, Schema, TypeSchema
from docir.platform.errors import (
    InvalidStatusError,
    InvalidStatusTransitionError,
    SchemaError,
    UnknownDocumentTypeError,
)


def _decision_type() -> TypeSchema:
    return TypeSchema(
        name="decision",
        prefix="adr",
        required_fields=(),
        statuses=("proposed", "accepted", "rejected"),
        default_status="proposed",
        transitions={
            "proposed": frozenset({"accepted", "rejected"}),
            "accepted": frozenset(),
            "rejected": frozenset(),
        },
        level=3,
        inactive_statuses=("rejected",),
    )


def _schema() -> Schema:
    return Schema(types={"decision": _decision_type()})


class TestSchema:
    def test_prefix_and_default(self) -> None:
        schema = _schema()
        assert schema.prefix_for("decision") == "adr"
        assert schema.default_status_for("decision") == "proposed"

    def test_unknown_type_raises(self) -> None:
        with pytest.raises(UnknownDocumentTypeError):
            _schema().get("nope")

    def test_validate_status_ok_and_bad(self) -> None:
        schema = _schema()
        schema.validate_status("decision", "accepted")
        with pytest.raises(InvalidStatusError):
            schema.validate_status("decision", "bogus")

    def test_valid_transition(self) -> None:
        _schema().validate_transition("decision", "proposed", "accepted")

    def test_self_transition_allowed(self) -> None:
        _schema().validate_transition("decision", "accepted", "accepted")

    def test_invalid_transition(self) -> None:
        with pytest.raises(InvalidStatusTransitionError):
            _schema().validate_transition("decision", "accepted", "proposed")

    def test_inactive_statuses_union(self) -> None:
        assert _schema().inactive_statuses() == frozenset({"rejected"})

    def test_default_status_not_in_enum_raises(self) -> None:
        with pytest.raises(SchemaError):
            Schema(
                types={
                    "x": TypeSchema(
                        name="x",
                        prefix="x",
                        required_fields=(),
                        statuses=("a",),
                        default_status="b",
                        transitions={"a": frozenset()},
                    )
                }
            )

    def test_duplicate_prefix_raises(self) -> None:
        with pytest.raises(SchemaError):
            Schema(
                types={
                    "a": TypeSchema("a", "p", (), ("s",), "s", {"s": frozenset()}),
                    "b": TypeSchema("b", "p", (), ("s",), "s", {"s": frozenset()}),
                }
            )


def _obligation_type() -> TypeSchema:
    return TypeSchema(
        name="obligation",
        prefix="obl",
        required_fields=(),
        statuses=("open", "fulfilled"),
        default_status="open",
        transitions={"open": frozenset({"fulfilled"}), "fulfilled": frozenset()},
        allowed_relations={"implements": ("policy",), "relates_to": ()},
        review_days=90,
    )


class TestRelationConstraints:
    def test_allows_relation_permissive_without_whitelist(self) -> None:
        # A type with no allowed_relations mapping permits any kind to any target.
        assert _decision_type().allows_relation("supersedes", "decision")

    def test_allows_listed_kind_to_listed_target(self) -> None:
        assert _obligation_type().allows_relation("implements", "policy")

    def test_rejects_listed_kind_to_unlisted_target(self) -> None:
        assert not _obligation_type().allows_relation("implements", "obligation")

    def test_rejects_unlisted_kind(self) -> None:
        assert not _obligation_type().allows_relation("supersedes", "policy")

    def test_empty_target_list_allows_any_target(self) -> None:
        assert _obligation_type().allows_relation("relates_to", "anything")

    def test_is_known_relation_kind(self) -> None:
        schema = Schema(
            types={"decision": _decision_type()},
            relation_types=frozenset({"relates_to", "supersedes"}),
        )
        assert schema.is_known_relation_kind("supersedes")
        assert not schema.is_known_relation_kind("bogus")

    def test_unconfigured_registry_accepts_any_kind(self) -> None:
        # An empty relation_types set means kinds are unconstrained (legacy).
        assert _schema().is_known_relation_kind("whatever")

    def test_review_days_for(self) -> None:
        schema = Schema(types={"obligation": _obligation_type()})
        assert schema.review_days_for("obligation") == 90

    def test_allowed_relation_kind_must_be_registered(self) -> None:
        with pytest.raises(SchemaError):
            Schema(
                types={"obligation": _obligation_type()},
                relation_types=frozenset({"relates_to"}),  # 'implements' missing
            )


class TestRelationKindProperties:
    """What a relation kind *means* is schema data, not a hardcoded name set.

    Before this, three frozensets in three modules decided whether a kind was
    cycle-checked, layering-checked and followed backwards. A kind a custom
    schema added could join none of them, so it was silently exempt from all
    three and nothing said so.
    """

    def test_core_kinds_carry_their_properties_without_being_declared(self) -> None:
        """A bare `relation_types:` list is what every existing schema says.

        The properties cannot live only in the core YAML: an inline-only schema
        never merges it, and a non-symmetric `relates_to` is the 127-false-cycles
        bug (issue-44875a5a6ca6) back again.
        """
        schema = Schema(types={}, relation_types=frozenset({"relates_to", "supersedes"}))
        assert schema.is_symmetric_relation("relates_to")
        assert not schema.is_symmetric_relation("supersedes")
        assert schema.is_dependency_relation("depends_on")
        assert schema.successor_relation_kinds() == frozenset({"supersedes", "contradicts"})

    def test_an_undeclared_custom_kind_is_directed_and_otherwise_silent(self) -> None:
        """Keep the check it already had; add no warning it never had."""
        schema = Schema(types={}, relation_types=frozenset({"blocks"}))
        assert not schema.is_symmetric_relation("blocks"), "so a `blocks` loop is a cycle"
        assert not schema.is_dependency_relation("blocks"), "no new layering warning"
        assert "blocks" not in schema.successor_relation_kinds(), "no new traversal"

    def test_a_declared_property_wins_over_the_core_default(self) -> None:
        schema = Schema(
            types={},
            relation_types=frozenset({"relates_to"}),
            relation_kinds={"relates_to": RelationKindSchema("relates_to", symmetric=False)},
        )
        assert not schema.is_symmetric_relation("relates_to")

    def test_a_custom_kind_can_be_declared_a_successor(self) -> None:
        """The reason this is configurable: `replaced_by` had no way in."""
        schema = Schema(
            types={},
            relation_types=frozenset({"revokes"}),
            relation_kinds={"revokes": RelationKindSchema("revokes", successor=True)},
        )
        assert schema.successor_relation_kinds() == frozenset(
            {"revokes", "supersedes", "contradicts"}
        )

    def test_properties_resolve_for_a_kind_no_schema_registers(self) -> None:
        """An unconfigured schema accepts any kind, so lookups must still answer."""
        schema = Schema(types={})
        assert schema.is_symmetric_relation("relates_to")
        assert not schema.is_symmetric_relation("whatever")
