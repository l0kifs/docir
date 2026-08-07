"""Unit tests for the schema rendering and the drift between two renderings."""

from __future__ import annotations

from dataclasses import replace

from docir.modules.documents.domain.schema import Schema, TypeSchema
from docir.modules.documents.domain.services import schema_shape
from docir.modules.documents.infra.schema_loader import describe_schema


def _schema(**type_overrides: object) -> Schema:
    decision = TypeSchema(
        "decision",
        "adr",
        (),
        ("proposed", "accepted"),
        "proposed",
        {"proposed": frozenset({"accepted"}), "accepted": frozenset()},
        level=3,
    )
    return Schema(types={"decision": replace(decision, **type_overrides)})  # type: ignore[arg-type]


class TestDescribeIsTheOnlyRendering:
    def test_the_public_name_delegates_to_the_domain_one(self) -> None:
        # `describe_schema` (infra, exported by `api`) and the drift check
        # (application, which may not import infra) must render the identical
        # payload — a baseline written by one and compared by the other is only
        # meaningful if there is one definition of the shape.
        schema = _schema()
        assert describe_schema(schema) == schema_shape.describe(schema)


class TestDiff:
    def test_no_change_is_no_lines(self) -> None:
        payload = schema_shape.describe(_schema())
        assert schema_shape.diff(payload, payload) == []

    def test_a_new_requirement_is_named_in_the_terms_of_the_file(self) -> None:
        before = schema_shape.describe(_schema())
        after = schema_shape.describe(_schema(required_fields=("owner",)))
        assert schema_shape.diff(before, after) == ["type decision: required [] -> ['owner']"]

    def test_an_added_and_a_removed_type(self) -> None:
        before = schema_shape.describe(_schema())
        after = schema_shape.describe(
            Schema(
                types={
                    "issue": TypeSchema(
                        "issue", "issue", (), ("open",), "open", {"open": frozenset()}
                    )
                }
            )
        )
        assert schema_shape.diff(before, after) == ["-type decision", "+type issue"]

    def test_a_changed_prefix(self) -> None:
        before = schema_shape.describe(_schema())
        after = schema_shape.describe(_schema(prefix="bug"))
        assert schema_shape.diff(before, after) == ["type decision: prefix 'adr' -> 'bug'"]

    def test_a_removed_status_shows_both_lists(self) -> None:
        # Statuses and transitions are separate keys, so a removal moves both —
        # and both belong in the report, since `inactive_statuses` silently
        # un-hides documents while `transitions` is what strands them.
        before = schema_shape.describe(_schema())
        after = schema_shape.describe(
            _schema(statuses=("proposed",), transitions={"proposed": frozenset()})
        )
        lines = schema_shape.diff(before, after)
        assert any(line.startswith("type decision: statuses") for line in lines)
        assert any(line.startswith("type decision: transitions") for line in lines)

    def test_a_registered_relation_kind_that_disappears(self) -> None:
        before = schema_shape.describe(
            Schema(types=_schema().types, relation_types=frozenset({"relates_to", "depends_on"}))
        )
        after = schema_shape.describe(
            Schema(types=_schema().types, relation_types=frozenset({"relates_to"}))
        )
        assert schema_shape.diff(before, after) == ["-relation kind depends_on"]

    def test_the_same_pair_always_diffs_the_same_way(self) -> None:
        # The lines are compared across runs (a stored baseline against a live
        # schema), so set iteration order must never reach the output.
        before = schema_shape.describe(_schema())
        after = schema_shape.describe(_schema(required_fields=("owner",), prefix="bug", level=1))
        assert schema_shape.diff(before, after) == schema_shape.diff(before, after)
        assert len(schema_shape.diff(before, after)) == 3

    def test_a_baseline_of_the_wrong_shape_degrades_instead_of_raising(self) -> None:
        # The baseline is read back from storage and may have been written by
        # another version of this code. A check must not raise on it.
        after = schema_shape.describe(_schema())
        # Everything in `after` reads as new, which is the honest answer for a
        # baseline that says nothing — and it does not raise.
        assert "+type decision" in schema_shape.diff({"types": "not-a-list"}, after)
        assert schema_shape.diff({}, {}) == []
