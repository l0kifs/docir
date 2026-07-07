"""Tests for the schema YAML loader and default schema."""

from __future__ import annotations

import pytest

from docir.domain.errors import SchemaError
from docir.infrastructure.schema.loader import (
    ensure_schema_file,
    load_schema,
    parse_schema,
)


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
