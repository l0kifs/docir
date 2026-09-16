"""Parse ``docs-schema.yaml`` into the domain :class:`Schema`.

A schema file either lists ``profiles:`` (the frozen core is merged with the
named bundled profiles and the file's own inline overrides) or defines its
types inline the old way. Inline-only files stay fully backward compatible:
no core is injected and relation kinds are unconstrained unless the file opts in
with its own ``relation_types``.

Merging only ever *adds* types, so ``disable_types:`` is how a store subtracts
one it did not ask for — see :func:`_apply_disabled_types`.
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
    StoreCheck,
    TypeSchema,
)
from docir.modules.documents.domain.services import schema_shape
from docir.modules.documents.domain.services.expressions import compile_expression
from docir.modules.documents.domain.services.graph_checks import RESERVED_FINDING_KINDS
from docir.modules.documents.infra.default_schema import DEFAULT_SCHEMA_YAML
from docir.modules.documents.infra.profiles import (
    CORE_SCHEMA_YAML,
    PROFILE_NAMES,
    PROFILE_YAMLS,
)
from docir.platform.errors import SchemaError, ValidationError


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

    The rendering itself lives in ``domain.services.schema_shape``, because the
    drift check needs the identical payload and sits in ``application``, which
    may not import ``infra``. This stays the public name: it is what ``api``
    exports and what ``docir schema show`` and the ``docir_schema`` MCP tool
    call.
    """
    return schema_shape.describe(schema)


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
        types=_apply_disabled_types(
            _parse_types_mapping(types_raw, _parse_id_style(raw.get("id_style"))),
            raw.get("disable_types"),
            types_raw,
        ),
        relation_types=frozenset(_parse_relation_types(raw.get("relation_types"))),
        relation_kinds=_parse_relation_kinds(raw.get("relation_types")),
        embed_model=_parse_embed_model(raw.get("embed_model")),
        checks=_parse_checks(raw.get("checks")),
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
        types=_apply_disabled_types(merged_types, raw.get("disable_types"), raw.get("types")),
        relation_types=frozenset(merged_kinds),
        relation_kinds=merged_props,
        # From the file's own key, never a profile's: which model a corpus is
        # embedded with is the store's choice, and a package upgrade that could
        # move it would silently re-embed every document in every store.
        embed_model=_parse_embed_model(raw.get("embed_model")),
        checks=_parse_checks(raw.get("checks")),
    )


def _parse_checks(raw: object) -> tuple[StoreCheck, ...]:
    """Parse ``checks:`` — the rules a store states about its own corpus.

    Everything is validated here, where the author is looking at the file. An
    expression that does not compile, a name that collides with a finding docir
    defines, a missing message: each is reported at load rather than surviving
    until somebody runs ``check`` and reads a finding that is not theirs.

    The name-collision rule is the load-bearing one. A check called ``dangling``
    would make ``--strict``'s behaviour depend on whose schema is loaded, and a
    store's own rule must never be able to change what a docir finding means.
    """
    if raw is None:
        return ()
    if not isinstance(raw, dict):
        raise SchemaError("'checks' must be a mapping of name -> {expr, message}")
    parsed: list[StoreCheck] = []
    for name, spec in raw.items():
        key = str(name)
        if key in RESERVED_FINDING_KINDS:
            reserved = ", ".join(sorted(RESERVED_FINDING_KINDS))
            raise SchemaError(f"check {key!r} collides with a docir finding; reserved: {reserved}")
        if not isinstance(spec, dict):
            raise SchemaError(f"check {key!r} must be a mapping with 'expr' and 'message'")
        expression = spec.get("expr")
        if not isinstance(expression, str) or not expression.strip():
            raise SchemaError(f"check {key!r} needs a non-empty 'expr'")
        # Compiled at load so a typo fails the command that reads the schema,
        # not the first document that happens to reach it. Re-raised as a
        # SchemaError: the fault is in the file, and the CLI maps the two to
        # different exit codes.
        try:
            compile_expression(expression)
        except ValidationError as exc:
            raise SchemaError(f"check {key!r}: {exc}") from exc
        message = spec.get("message")
        if not isinstance(message, str) or not message.strip():
            raise SchemaError(f"check {key!r} needs a 'message' saying what the finding means")
        parsed.append(StoreCheck(name=key, expression=expression.strip(), message=message.strip()))
    return tuple(parsed)


def _parse_embed_model(raw: object) -> str | None:
    """The store's embedding model, or ``None`` for the default.

    Shape only. Membership is checked in :class:`Schema`, beside every other
    rule a schema must satisfy, so a store whose model was removed from the
    supported set fails the same way an unknown status does — at load, naming
    what would have worked.
    """
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        raise SchemaError("'embed_model' must be a non-empty string naming a supported model")
    return raw.strip()


def _apply_disabled_types(
    merged: dict[str, TypeSchema], names: object, inline: object
) -> dict[str, TypeSchema]:
    """Remove the types named by ``disable_types:`` from the resolved set.

    Merging is additive — the core is injected whenever a ``profiles:`` key is
    present, and an inline block can only *override a type by its own name*. So
    a store had no way to say "this corpus has no ``decision``": the name stayed
    addable and, worse, its ``prefix`` stayed claimed, which made a differently
    named type with the same prefix unexpressible. Renaming a corpus's types
    while keeping its ids (``adr-...``) is exactly that shape
    (issue-ab138501abfd).

    Two rules keep it from being a quiet way to break a store:

    * the name must be in the resolved set. A typo'd entry that silently did
      nothing forever is the failure mode ``required:`` and the status targets
      already have loader checks for — reported here, naming what would work.
    * it may not name a type the *same file* declares inline. Declaring and
      disabling one name in one file is a contradiction with no reading worth
      guessing at; the fix is to delete the block, which the message says.

    What it deliberately does not do is consult the corpus: schema resolution
    knows nothing about documents, and disabling a type still in use is a
    supported (if pointed) move — ``docir check`` reports those documents as
    ``unknown-type`` and ``schema-drift`` names the change that caused it, the
    same way disabling a profile already behaves. ``docir update <id> --type``
    is the way out, and works *from* an unknown type for that reason.
    """
    if names is None:
        return merged
    if not isinstance(names, list):
        raise SchemaError("'disable_types' must be a list of type names")
    disabled = {str(name) for name in names}

    unknown = sorted(disabled - set(merged))
    if unknown:
        known = ", ".join(sorted(merged)) or "<none>"
        raise SchemaError(
            f"'disable_types' names type(s) this schema does not define: "
            f"{', '.join(repr(name) for name in unknown)}; defined types: {known}"
        )

    declared_here = sorted(disabled & {str(k) for k in inline}) if isinstance(inline, dict) else []
    if declared_here:
        raise SchemaError(
            f"type(s) {', '.join(repr(name) for name in declared_here)} are both declared "
            f"in this file's 'types:' block and listed in 'disable_types'; delete the "
            f"block instead of disabling it"
        )

    remaining = {name: spec for name, spec in merged.items() if name not in disabled}
    if not remaining:
        raise SchemaError("'disable_types' would leave the schema with no types at all")
    return remaining


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


def _parse_statuses(name: str, spec: dict) -> tuple[tuple[str, ...], dict[str, frozenset[str]]]:
    """The declared statuses and the transitions between them.

    Every status name referenced anywhere must be one this type declares.
    Without this, `statuses: {open: [closd]}` loaded happily and the typo only
    surfaced much later as "invalid transition 'open' -> 'closed'" — a message
    naming a status that IS declared, pointing the reader at their write
    instead of at the schema. `schema validate` exists to catch exactly this
    and passed it.
    """
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
    for status, targets in transitions.items():
        unknown = sorted(targets - declared)
        if unknown:
            known = ", ".join(sorted(declared))
            raise SchemaError(
                f"type {name!r} status {status!r} transitions to undeclared "
                f"status(es) {', '.join(repr(u) for u in unknown)}; declared: {known}"
            )
    return statuses, transitions


def _parse_default_status(name: str, spec: dict, declared: set[str]) -> str:
    """The status a new document of this type starts in; must be declared."""
    default_status = spec.get("default_status")
    if not isinstance(default_status, str):
        raise SchemaError(f"type {name!r} must define a string 'default_status'")
    if default_status not in declared:
        known = ", ".join(sorted(declared))
        raise SchemaError(
            f"type {name!r} 'default_status' {default_status!r} is not a declared "
            f"status; declared: {known}"
        )
    return default_status


def _parse_required(name: str, spec: dict) -> list:
    """The fields a document of this type must carry.

    Every name must be a field a document can actually carry. Tier 0 reads a
    required field off the document, so a name that is not one is not an
    unknown key — it is unsatisfiable, and every write of the type fails
    forever with a message naming the write instead of the schema. The same
    class of defect as an undeclared status target in :func:`_parse_statuses`,
    and reported the same way: at load, naming what would have worked
    (issue-e3c4dfad4f7b).
    """
    required = spec.get("required", []) or []
    if not isinstance(required, list):
        raise SchemaError(f"type {name!r} 'required' must be a list")
    unknown_required = sorted({str(f) for f in required} - REQUIRABLE_FIELDS)
    if unknown_required:
        known = ", ".join(sorted(REQUIRABLE_FIELDS))
        raise SchemaError(
            f"type {name!r} 'required' names field(s) no document can carry: "
            f"{', '.join(repr(f) for f in unknown_required)}; a document's fields are: {known}"
        )
    return required


def _parse_inactive_statuses(name: str, spec: dict, declared: set[str]) -> list:
    """The statuses that take a document out of the default read paths."""
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
    return inactive


def _require_integer(name: str, key: str, value: object) -> int:
    """One integer check for the three numeric type fields.

    ``bool`` is excluded explicitly: it is a subclass of ``int``, so
    ``level: true`` would otherwise load as ``level: 1``.
    """
    if not isinstance(value, int) or isinstance(value, bool):
        raise SchemaError(f"type {name!r} {key!r} must be an integer")
    return value


def _parse_type(name: str, spec: object, default_id_style: str) -> TypeSchema:
    if not isinstance(spec, dict):
        raise SchemaError(f"type {name!r} must be a mapping")

    prefix = spec.get("prefix")
    if not isinstance(prefix, str) or not prefix:
        raise SchemaError(f"type {name!r} must define a string 'prefix'")

    statuses, transitions = _parse_statuses(name, spec)
    declared = set(statuses)

    default_status = _parse_default_status(name, spec, declared)

    required = _parse_required(name, spec)
    inactive = _parse_inactive_statuses(name, spec, declared)
    level = _require_integer(name, "level", spec.get("level", 0))
    review_days = _require_integer(name, "review_days", spec.get("review_days", 0))
    # One number for both tiers. Absent inherits the linter's default and sets
    # no ceiling; 0 means neither. A negative would be a ceiling every body is
    # over, so it is refused here rather than refusing every write afterwards.
    max_body_chars = _parse_body_chars(name, "max_body_chars", spec)
    max_body_chars_enforce = _parse_enforce(name, spec, max_body_chars)

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
        max_body_chars_enforce=max_body_chars_enforce,
    )


def _parse_body_chars(name: str, key: str, spec: dict) -> int | None:
    """Parse the body-size limit; ``None`` means the key is absent."""
    raw = spec.get(key)
    if raw is None:
        return None
    value = _require_integer(name, key, raw)
    if value < 0:
        raise SchemaError(f"type {name!r} {key!r} must not be negative (0 disables it)")
    return value


def _parse_enforce(name: str, spec: dict, max_body_chars: int | None) -> bool:
    """Parse ``max_body_chars_enforce``, refusing one with nothing to demote.

    ``false`` without a positive ``max_body_chars`` reads as "the ceiling is
    advisory here" and means nothing at all — there is no ceiling. The loader
    names what it can name at load time rather than letting the store believe a
    limit is configured.
    """
    raw = spec.get("max_body_chars_enforce")
    if raw is None:
        return True
    if not isinstance(raw, bool):
        raise SchemaError(f"type {name!r} 'max_body_chars_enforce' must be true or false")
    if not raw and not max_body_chars:
        raise SchemaError(
            f"type {name!r} sets 'max_body_chars_enforce: false' with no 'max_body_chars' to "
            f"relax; set a limit, or drop the key"
        )
    return raw


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
