"""The resolved schema as plain data, and the difference between two of them.

``describe`` renders a :class:`Schema` as JSON-safe data — the *merged* result
(core + profiles + inline overrides), which is what validation actually
enforces; the raw file only shows the ingredients. ``diff`` says how two such
renderings differ, in the terms a person edits: types, their fields, and the
relation-kind registry.

Both live in ``domain`` rather than beside the loader in ``infra`` because two
callers need them and only one of them may reach ``infra``: ``docir schema
show`` (an entry point, through ``api``) and the drift check in
``MaintenanceService`` (``application``, which the module rules forbid from
importing ``infra`` at all). A second renderer for the second caller is the
failure this module exists to avoid — the baseline recorded by one and the
payload compared by the other have to be the same shape or the diff is noise.
"""

from __future__ import annotations

from docir.modules.documents.domain.schema import (
    CORE_RELATION_KINDS,
    RELATION_KIND_PROPERTIES,
    Schema,
)

#: The per-type keys ``describe`` emits, in the order a diff reports them.
#: Derived from the rendering below rather than restated, so a new type field
#: joins the drift report by being rendered.
_TYPE_FIELDS: tuple[str, ...] = (
    "prefix",
    "default_status",
    "statuses",
    "transitions",
    "inactive_statuses",
    "required",
    "level",
    "review_days",
    "max_body_chars",
    "id_style",
    "allowed_relations",
)


def describe(schema: Schema) -> dict[str, object]:
    """Render a :class:`Schema` as plain data (``docir schema show``)."""
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


def diff(before: dict[str, object], after: dict[str, object]) -> list[str]:
    """How ``after`` differs from ``before``, one short line per change.

    The lines are the report, not a data structure: they say what moved in the
    vocabulary of the file a person edits — ``+type test_plan``,
    ``type decision: required [] -> ['owner']``. Anything a reader would have to
    decode is worse than nothing here, because the whole point is that the
    change arrived without a diff to read.

    Deterministic and total: every difference produces a line, and the same pair
    always produces the same lines in the same order, so a caller can compare
    two runs.
    """
    lines: list[str] = []
    lines.extend(_diff_types(_by_name(before, "types"), _by_name(after, "types")))
    lines.extend(_diff_kinds(_by_name(before, "relation_kinds"), _by_name(after, "relation_kinds")))
    return lines


def _by_name(payload: dict[str, object], key: str) -> dict[str, dict[str, object]]:
    """The ``key`` list of ``{"name": ...}`` entries, keyed by name.

    Tolerant of a payload that is not shaped as expected: a baseline is read
    back from storage, and a row written by a different version of this code
    must degrade to "nothing known about that section" rather than raise inside
    a check.
    """
    entries = payload.get(key)
    if not isinstance(entries, list):
        return {}
    named: dict[str, dict[str, object]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        fields = {str(key): value for key, value in entry.items()}
        name = fields.get("name")
        if name is not None:
            named[str(name)] = fields
    return named


def _diff_types(
    before: dict[str, dict[str, object]], after: dict[str, dict[str, object]]
) -> list[str]:
    lines = [f"-type {name}" for name in sorted(set(before) - set(after))]
    lines.extend(f"+type {name}" for name in sorted(set(after) - set(before)))
    for name in sorted(set(before) & set(after)):
        for field in _TYPE_FIELDS:
            was, now = before[name].get(field), after[name].get(field)
            if was != now:
                lines.append(f"type {name}: {field} {was!r} -> {now!r}")
    return lines


def _diff_kinds(
    before: dict[str, dict[str, object]], after: dict[str, dict[str, object]]
) -> list[str]:
    lines = [f"-relation kind {name}" for name in sorted(set(before) - set(after))]
    lines.extend(f"+relation kind {name}" for name in sorted(set(after) - set(before)))
    for name in sorted(set(before) & set(after)):
        for prop in RELATION_KIND_PROPERTIES:
            was, now = before[name].get(prop), after[name].get(prop)
            if was != now:
                lines.append(f"relation kind {name}: {prop} {was!r} -> {now!r}")
    return lines
