"""Parse ``docs-schema.yaml`` into the domain :class:`Schema`.

A schema file either lists ``profiles:`` (the frozen core is merged with the
named bundled profiles and the file's own inline overrides) or defines its
types inline the old way. Inline-only files stay fully backward compatible:
no core is injected and relation kinds are unconstrained unless the file opts in
with its own ``relation_types``.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from docir.modules.documents.domain.schema import (
    CORE_RELATION_KINDS,
    DEFAULT_ID_STYLE,
    ID_STYLES,
    RELATION_KIND_PROPERTIES,
    REQUIRABLE_FIELDS,
    RelationKindSchema,
    Schema,
    TypeSchema,
)
from docir.modules.documents.infra.default_schema import DEFAULT_SCHEMA_YAML
from docir.modules.documents.infra.profiles import (
    CORE_SCHEMA_YAML,
    PROFILE_NAMES,
    PROFILE_YAMLS,
)
from docir.platform.errors import SchemaError


def ensure_schema_file(path: Path) -> None:
    """Write the bundled default schema to ``path`` if it does not exist yet."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_SCHEMA_YAML, encoding="utf-8")


def load_schema(path: Path) -> Schema:
    """Load and validate a schema file into a :class:`Schema` domain object.

    A YAML *syntax* error is reported as a :class:`SchemaError` like every
    semantic one. The parser's own exception is not a ``DocirError``, so it
    escaped the CLI's error mapping as a raw traceback — on the one file the
    docs tell you to edit by hand.
    """
    ensure_schema_file(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise SchemaError(f"{path} is not valid YAML: {exc}") from exc
    return parse_schema(raw)


def describe_schema(schema: Schema) -> dict[str, object]:
    """Render a :class:`Schema` as plain data for ``docir schema show``.

    Reports the *merged* result (core + profiles + inline overrides), which is
    what validation actually enforces — the raw file only shows the ingredients.
    """
    return {
        "relation_types": sorted(schema.relation_types),
        # The resolved properties, not the declared ones: what a kind *means* is
        # the thing a reader cannot work out from the file, since an undeclared
        # core kind still carries the core's flags.
        "relation_kinds": [
            {
                "name": kind,
                **{
                    prop: getattr(schema.relation_kind(kind), prop)
                    for prop in RELATION_KIND_PROPERTIES
                },
            }
            for kind in sorted(schema.relation_types or CORE_RELATION_KINDS)
        ],
        "types": [
            {
                "name": type_schema.name,
                "prefix": type_schema.prefix,
                "default_status": type_schema.default_status,
                "statuses": list(type_schema.statuses),
                "transitions": {
                    status: sorted(targets) for status, targets in type_schema.transitions.items()
                },
                "inactive_statuses": list(type_schema.inactive_statuses),
                "required": list(type_schema.required_fields),
                "level": type_schema.level,
                "review_days": type_schema.review_days,
                "max_body_chars": type_schema.max_body_chars,
                "id_style": type_schema.id_style,
                "allowed_relations": {
                    kind: list(targets)
                    for kind, targets in sorted(type_schema.allowed_relations.items())
                },
            }
            for _, type_schema in sorted(schema.types.items())
        ],
    }


def parse_schema(raw: object) -> Schema:
    """Turn a parsed YAML mapping into a validated :class:`Schema`."""
    if not isinstance(raw, dict):
        raise SchemaError("schema root must be a mapping")
    if "profiles" in raw:
        return _merge_profiled(raw)

    types_raw = raw.get("types")
    if not isinstance(types_raw, dict) or not types_raw:
        raise SchemaError("schema must define a non-empty 'types' mapping (or 'profiles')")
    return Schema(
        types=_parse_types_mapping(types_raw, _parse_id_style(raw.get("id_style"))),
        relation_types=frozenset(_parse_relation_types(raw.get("relation_types"))),
        relation_kinds=_parse_relation_kinds(raw.get("relation_types")),
    )


def _merge_profiled(raw: object) -> Schema:
    """Merge ``core -> named profiles -> the file's inline overrides``."""
    if not isinstance(raw, dict):
        raise SchemaError("schema root must be a mapping")
    profiles = raw.get("profiles")
    if not isinstance(profiles, list):
        raise SchemaError("'profiles' must be a list of profile names")

    fragments: list[object] = [yaml.safe_load(CORE_SCHEMA_YAML)]
    for name in profiles:
        key = str(name)
        if key not in PROFILE_YAMLS:
            known = ", ".join(PROFILE_NAMES)
            raise SchemaError(f"unknown profile {key!r}; available profiles: {known}")
        fragments.append(yaml.safe_load(PROFILE_YAMLS[key]))
    fragments.append({k: v for k, v in raw.items() if k != "profiles"})

    # Resolve the schema-wide ``id_style`` first, so it applies to the types the
    # core and the profiles contribute too -- not just to inline ones. Later
    # fragments win, which puts the file's own setting on top.
    default_id_style = DEFAULT_ID_STYLE
    for fragment in fragments:
        if isinstance(fragment, dict) and fragment.get("id_style") is not None:
            default_id_style = _parse_id_style(fragment.get("id_style"))

    merged_types: dict[str, TypeSchema] = {}
    merged_kinds: set[str] = set()
    merged_props: dict[str, RelationKindSchema] = {}
    for fragment in fragments:
        if not isinstance(fragment, dict):
            continue
        merged_kinds.update(_parse_relation_types(fragment.get("relation_types")))
        # Per key, not wholesale: a profile registering a kind must not drop the
        # properties the core declared for the ones it did not mention.
        merged_props.update(_parse_relation_kinds(fragment.get("relation_types")))
        types_raw = fragment.get("types")
        if isinstance(types_raw, dict):
            merged_types.update(_parse_types_mapping(types_raw, default_id_style))

    if not merged_types:
        raise SchemaError("resolved schema has no types after merging profiles")
    return Schema(
        types=merged_types,
        relation_types=frozenset(merged_kinds),
        relation_kinds=merged_props,
    )


def _parse_relation_types(value: object) -> set[str]:
    """The registered kind *names*, from either the list or the mapping form."""
    if value is None:
        return set()
    if isinstance(value, dict):
        return {str(key) for key in value}
    if not isinstance(value, list):
        raise SchemaError(
            "'relation_types' must be a list of kind names, or a mapping of "
            "kind name to its properties"
        )
    return {str(item) for item in value}


def _parse_relation_kinds(value: object) -> dict[str, RelationKindSchema]:
    """The *declared* per-kind properties — only the mapping form carries any.

    The list form stays valid and means "every kind takes its defaults", which is
    what every schema written before this said and must keep meaning. A mapping
    entry may give a subset of the properties or nothing at all (``blocks:``),
    and whatever it omits falls back to the core default for that name — so
    naming a core kind to set one flag cannot silently reset the others.
    """
    if not isinstance(value, dict):
        return {}
    kinds: dict[str, RelationKindSchema] = {}
    for raw_name, raw_props in value.items():
        name = str(raw_name)
        base = CORE_RELATION_KINDS.get(name, RelationKindSchema(name))
        if raw_props is None:
            kinds[name] = base
            continue
        if not isinstance(raw_props, dict):
            raise SchemaError(
                f"relation kind {name!r}: properties must be a mapping, got "
                f"{type(raw_props).__name__}"
            )
        given = {str(key): val for key, val in raw_props.items()}
        unknown = set(given) - set(RELATION_KIND_PROPERTIES)
        if unknown:
            allowed = ", ".join(RELATION_KIND_PROPERTIES)
            raise SchemaError(
                f"relation kind {name!r}: unknown propert"
                f"{'y' if len(unknown) == 1 else 'ies'} "
                f"{', '.join(sorted(repr(u) for u in unknown))}; allowed: {allowed}"
            )
        props = {
            prop: bool(given[prop]) if prop in given else getattr(base, prop)
            for prop in RELATION_KIND_PROPERTIES
        }
        kinds[name] = RelationKindSchema(name, **props)
    return kinds


def _parse_id_style(value: object, *, where: str = "schema") -> str:
    """Validate an ``id_style`` value, defaulting when it is absent."""
    if value is None:
        return DEFAULT_ID_STYLE
    style = str(value)
    if style not in ID_STYLES:
        allowed = ", ".join(ID_STYLES)
        raise SchemaError(f"{where} 'id_style' must be one of: {allowed} (got {style!r})")
    return style


def _parse_types_mapping(types_raw: object, default_id_style: str) -> dict[str, TypeSchema]:
    if not isinstance(types_raw, dict):
        return {}
    return {
        str(name): _parse_type(str(name), spec, default_id_style)
        for name, spec in types_raw.items()
    }


def _parse_type(name: str, spec: object, default_id_style: str) -> TypeSchema:
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
    declared = set(statuses)

    # Every status name referenced anywhere must be one this type declares.
    # Without this, `statuses: {open: [closd]}` loaded happily and the typo only
    # surfaced much later as "invalid transition 'open' -> 'closed'" — a message
    # naming a status that IS declared, pointing the reader at their write
    # instead of at the schema. `schema validate` exists to catch exactly this
    # and passed it.
    for status, targets in transitions.items():
        unknown = sorted(targets - declared)
        if unknown:
            known = ", ".join(sorted(declared))
            raise SchemaError(
                f"type {name!r} status {status!r} transitions to undeclared "
                f"status(es) {', '.join(repr(u) for u in unknown)}; declared: {known}"
            )

    default_status = spec.get("default_status")
    if not isinstance(default_status, str):
        raise SchemaError(f"type {name!r} must define a string 'default_status'")
    if default_status not in declared:
        known = ", ".join(sorted(declared))
        raise SchemaError(
            f"type {name!r} 'default_status' {default_status!r} is not a declared "
            f"status; declared: {known}"
        )

    required = spec.get("required", []) or []
    if not isinstance(required, list):
        raise SchemaError(f"type {name!r} 'required' must be a list")
    # Every name must be a field a document can actually carry. Tier 0 reads a
    # required field off the document, so a name that is not one is not an
    # unknown key — it is unsatisfiable, and every write of the type fails
    # forever with a message naming the write instead of the schema. The same
    # class of defect as an undeclared status target above, and reported the
    # same way: at load, naming what would have worked (issue-e3c4dfad4f7b).
    unknown_required = sorted({str(f) for f in required} - REQUIRABLE_FIELDS)
    if unknown_required:
        known = ", ".join(sorted(REQUIRABLE_FIELDS))
        raise SchemaError(
            f"type {name!r} 'required' names field(s) no document can carry: "
            f"{', '.join(repr(f) for f in unknown_required)}; a document's fields are: {known}"
        )

    inactive = spec.get("inactive_statuses", []) or []
    if not isinstance(inactive, list):
        raise SchemaError(f"type {name!r} 'inactive_statuses' must be a list")
    unknown_inactive = sorted({str(s) for s in inactive} - declared)
    if unknown_inactive:
        known = ", ".join(sorted(declared))
        raise SchemaError(
            f"type {name!r} 'inactive_statuses' names undeclared status(es) "
            f"{', '.join(repr(u) for u in unknown_inactive)}; declared: {known}"
        )

    level = spec.get("level", 0)
    if not isinstance(level, int) or isinstance(level, bool):
        raise SchemaError(f"type {name!r} 'level' must be an integer")

    review_days = spec.get("review_days", 0)
    if not isinstance(review_days, int) or isinstance(review_days, bool):
        raise SchemaError(f"type {name!r} 'review_days' must be an integer")

    # Absent inherits the linter's default; 0 means "never too long".
    max_body_chars = spec.get("max_body_chars")
    if max_body_chars is not None and (
        not isinstance(max_body_chars, int) or isinstance(max_body_chars, bool)
    ):
        raise SchemaError(f"type {name!r} 'max_body_chars' must be an integer")

    # A type without its own ``id_style`` inherits the schema-wide default.
    id_style = (
        default_id_style
        if spec.get("id_style") is None
        else _parse_id_style(spec.get("id_style"), where=f"type {name!r}")
    )

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
        allowed_relations=_parse_allowed_relations(name, spec.get("allowed_relations")),
        review_days=review_days,
        max_body_chars=max_body_chars,
    )


def _parse_allowed_relations(name: str, value: object) -> dict[str, tuple[str, ...]]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise SchemaError(f"type {name!r} 'allowed_relations' must be a mapping")
    allowed: dict[str, tuple[str, ...]] = {}
    for kind, targets in value.items():
        if targets is None:
            targets = []
        if not isinstance(targets, list):
            raise SchemaError(
                f"type {name!r} allowed_relations {kind!r} must be a list of target types"
            )
        allowed[str(kind)] = tuple(str(t) for t in targets)
    return allowed
