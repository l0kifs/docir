"""Unit tests for the schema domain object and its validation."""

from __future__ import annotations

import pytest

from docir.modules.documents.domain.schema import Schema, TypeSchema
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
