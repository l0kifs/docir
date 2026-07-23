"""Tests for the schema YAML loader and default schema."""

from __future__ import annotations

import pytest

from docir.modules.documents.infra.schema_loader import (
    ensure_schema_file,
    load_schema,
    parse_schema,
)
from docir.platform.errors import SchemaError


def test_default_schema_written_and_loaded(tmp_path) -> None:
    path = tmp_path / "docs-schema.yaml"
    schema = load_schema(path)
    assert path.exists()
    assert set(schema.types) == {"decision", "issue", "architecture"}
    assert schema.prefix_for("decision") == "adr"
    assert "resolved" in schema.inactive_statuses()


def test_ensure_schema_file_is_idempotent(tmp_path) -> None:
    path = tmp_path / "s.yaml"
    ensure_schema_file(path)
    path.write_text(
        "types:\n  decision:\n    prefix: adr\n    default_status: a\n    statuses:\n      a: []\n"
    )
    ensure_schema_file(path)  # must not overwrite
    assert "prefix: adr" in path.read_text()


@pytest.mark.parametrize(
    "raw",
    [
        "not a mapping",
        {"types": {}},
        {"types": {"x": "bad"}},
        {"types": {"x": {"statuses": {"a": []}, "default_status": "a"}}},  # no prefix
        {"types": {"x": {"prefix": "x", "default_status": "a"}}},  # no statuses
        {"types": {"x": {"prefix": "x", "statuses": {"a": []}}}},  # no default
        {"types": {"x": {"prefix": "x", "statuses": {"a": "bad"}, "default_status": "a"}}},
    ],
)
def test_parse_schema_rejects_bad_input(raw: object) -> None:
    with pytest.raises(SchemaError):
        parse_schema(raw)


def test_parse_schema_type_field_validation() -> None:
    with pytest.raises(SchemaError):
        parse_schema(
            {
                "types": {
                    "x": {
                        "prefix": "x",
                        "statuses": {"a": []},
                        "default_status": "a",
                        "level": "high",
                    }
                }
            }
        )


def test_parse_schema_id_style() -> None:
    schema = parse_schema(
        {
            "types": {
                "x": {
                    "prefix": "x",
                    "statuses": {"a": []},
                    "default_status": "a",
                    "id_style": "random",
                }
            }
        }
    )
    assert schema.get("x").id_style == "random"


def test_parse_schema_rejects_bad_id_style() -> None:
    with pytest.raises(SchemaError):
        parse_schema(
            {
                "types": {
                    "x": {
                        "prefix": "x",
                        "statuses": {"a": []},
                        "default_status": "a",
                        "id_style": "uuid",
                    }
                }
            }
        )


class TestProfilesAndCore:
    def test_default_includes_core_registry_and_cadence(self, tmp_path) -> None:
        schema = load_schema(tmp_path / "s.yaml")
        assert "supersedes" in schema.relation_types  # from the frozen core
        assert schema.review_days_for("decision") == 365

    def test_named_profile_merges_over_core(self, tmp_path) -> None:
        path = tmp_path / "s.yaml"
        path.write_text("profiles: [research]\n")
        schema = load_schema(path)
        # core `decision` plus the research profile's types.
        assert {"decision", "hypothesis", "experiment", "finding"} <= set(schema.types)

    def test_multiple_profiles_and_allowed_relations(self) -> None:
        schema = parse_schema({"profiles": ["software", "legal"]})
        assert {"issue", "architecture", "policy", "obligation"} <= set(schema.types)
        # allowed_relations from the legal profile parses into the type schema.
        assert schema.get("obligation").allowed_relations["implements"] == ("policy", "contract")

    def test_inline_types_override_profile(self) -> None:
        schema = parse_schema(
            {
                "profiles": ["software"],
                "types": {
                    "issue": {
                        "prefix": "bug",
                        "statuses": {"open": []},
                        "default_status": "open",
                    }
                },
            }
        )
        assert schema.prefix_for("issue") == "bug"  # inline wins over the profile

    def test_unknown_profile_rejected(self) -> None:
        with pytest.raises(SchemaError):
            parse_schema({"profiles": ["nonsense"]})

    def test_profiles_must_be_a_list(self) -> None:
        with pytest.raises(SchemaError):
            parse_schema({"profiles": "software"})


class TestRelationAndStalenessFields:
    def test_inline_relation_types_parsed(self) -> None:
        schema = parse_schema(
            {
                "types": {"x": {"prefix": "x", "statuses": {"a": []}, "default_status": "a"}},
                "relation_types": ["relates_to", "blocks"],
            }
        )
        assert schema.relation_types == frozenset({"relates_to", "blocks"})

    def test_review_days_parsed(self) -> None:
        schema = parse_schema(
            {
                "types": {
                    "x": {
                        "prefix": "x",
                        "statuses": {"a": []},
                        "default_status": "a",
                        "review_days": 42,
                    }
                }
            }
        )
        assert schema.review_days_for("x") == 42

    @pytest.mark.parametrize(
        "spec",
        [
            {"prefix": "x", "statuses": {"a": []}, "default_status": "a", "review_days": "soon"},
            {
                "prefix": "x",
                "statuses": {"a": []},
                "default_status": "a",
                "allowed_relations": "no",
            },
            {
                "prefix": "x",
                "statuses": {"a": []},
                "default_status": "a",
                "allowed_relations": {"implements": "not-a-list"},
            },
        ],
    )
    def test_bad_relation_or_staleness_fields_rejected(self, spec: dict) -> None:
        with pytest.raises(SchemaError):
            parse_schema({"types": {"x": spec}})

    def test_bad_relation_types_rejected(self) -> None:
        with pytest.raises(SchemaError):
            parse_schema(
                {
                    "types": {"x": {"prefix": "x", "statuses": {"a": []}, "default_status": "a"}},
                    "relation_types": "not-a-list",
                }
            )
