"""Parse ``docs-schema.yaml`` into the domain :class:`Schema`."""

from __future__ import annotations

from pathlib import Path

import yaml

from docir.modules.documents.domain.schema import Schema, TypeSchema
from docir.modules.documents.infra.default_schema import DEFAULT_SCHEMA_YAML
from docir.platform.errors import SchemaError


def ensure_schema_file(path: Path) -> None:
    """Write the bundled default schema to ``path`` if it does not exist yet."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_SCHEMA_YAML, encoding="utf-8")


def load_schema(path: Path) -> Schema:
    """Load and validate a schema file into a :class:`Schema` domain object."""
    ensure_schema_file(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return parse_schema(raw)


def parse_schema(raw: object) -> Schema:
    """Turn a parsed YAML mapping into a validated :class:`Schema`."""
    if not isinstance(raw, dict):
        raise SchemaError("schema root must be a mapping")
    types_raw = raw.get("types")
    if not isinstance(types_raw, dict) or not types_raw:
        raise SchemaError("schema must define a non-empty 'types' mapping")

    types: dict[str, TypeSchema] = {}
    for name, spec in types_raw.items():
        types[str(name)] = _parse_type(str(name), spec)
    return Schema(types=types)


def _parse_type(name: str, spec: object) -> TypeSchema:
    if not isinstance(spec, dict):
        raise SchemaError(f"type {name!r} must be a mapping")

    prefix = spec.get("prefix")
    if not isinstance(prefix, str) or not prefix:
        raise SchemaError(f"type {name!r} must define a string 'prefix'")

    statuses_raw = spec.get("statuses")
    if not isinstance(statuses_raw, dict) or not statuses_raw:
        raise SchemaError(f"type {name!r} must define a non-empty 'statuses' mapping")

    transitions: dict[str, frozenset[str]] = {}
    for status, targets in statuses_raw.items():
        if targets is None:
            targets = []
        if not isinstance(targets, list):
            raise SchemaError(f"type {name!r} status {status!r} transitions must be a list")
        transitions[str(status)] = frozenset(str(t) for t in targets)

    statuses = tuple(str(s) for s in statuses_raw)

    default_status = spec.get("default_status")
    if not isinstance(default_status, str):
        raise SchemaError(f"type {name!r} must define a string 'default_status'")

    required = spec.get("required", []) or []
    if not isinstance(required, list):
        raise SchemaError(f"type {name!r} 'required' must be a list")

    inactive = spec.get("inactive_statuses", []) or []
    if not isinstance(inactive, list):
        raise SchemaError(f"type {name!r} 'inactive_statuses' must be a list")

    level = spec.get("level", 0)
    if not isinstance(level, int):
        raise SchemaError(f"type {name!r} 'level' must be an integer")

    id_style = str(spec.get("id_style", "sequential"))
    if id_style not in ("sequential", "random"):
        raise SchemaError(f"type {name!r} 'id_style' must be 'sequential' or 'random'")

    return TypeSchema(
        name=name,
        prefix=prefix,
        required_fields=tuple(str(field) for field in required),
        statuses=statuses,
        default_status=default_status,
        transitions=transitions,
        level=level,
        inactive_statuses=tuple(str(s) for s in inactive),
        id_style=id_style,
    )
