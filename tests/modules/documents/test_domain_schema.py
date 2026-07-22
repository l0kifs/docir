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
