"""The document schema — the per-type grammar of the system.

Required fields, valid status enums, allowed status transitions, and layering
levels are configuration (loaded from ``docs-schema.yaml``), not hardcoded in
the CLI, so new document types can be added without changing code. This module
models that configuration as immutable domain objects and answers the Tier 0
questions the validator asks of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from docir.platform.errors import (
    InvalidStatusError,
    InvalidStatusTransitionError,
    SchemaError,
    UnknownDocumentTypeError,
)

# Frontmatter fields every document has regardless of type. Type-specific
# ``required`` lists in the schema are checked in addition to these.
CORE_REQUIRED_FIELDS: tuple[str, ...] = (
    "id",
    "title",
    "description",
    "type",
    "status",
    "created",
    "updated",
)

#: How a type's ids are minted. ``sequential`` reads a per-prefix counter in the
#: index (``adr-0007``): human-friendly, and unique only within one store, so two
#: git branches can each mint the same number. ``random`` mints a hex token
#: (``adr-3f9a2b1c7d4e``): unique across independent clones with no shared state.
SEQUENTIAL_ID_STYLE = "sequential"
RANDOM_ID_STYLE = "random"
ID_STYLES: tuple[str, ...] = (SEQUENTIAL_ID_STYLE, RANDOM_ID_STYLE)

#: The style a type falls back to when neither it nor the schema says otherwise.
#: Stays ``sequential`` so an existing ``docs-schema.yaml`` keeps minting the ids
#: it always did; ``docir init`` writes an explicit style for new stores.
DEFAULT_ID_STYLE = SEQUENTIAL_ID_STYLE


@dataclass(frozen=True, slots=True)
class TypeSchema:
    """The grammar for a single document type."""

    name: str
    prefix: str
    required_fields: tuple[str, ...]
    statuses: tuple[str, ...]
    default_status: str
    # Map of ``status`` -> the statuses it may transition to.
    transitions: dict[str, frozenset[str]]
    # Layering level: a higher-level type depending on a lower-level one is a
    # Tier 1 warning (e.g. an ``architecture`` doc coupled to an ``issue``).
    level: int = 0
    # Statuses treated as "closed" and hidden from the default read path
    # (e.g. ``issue``: resolved). Widened back in with ``--include-resolved``.
    inactive_statuses: tuple[str, ...] = ()
    # How ids are allocated: ``sequential`` (human-friendly ``adr-0007``, safe
    # only within one shared index) or ``random`` (collision-resistant across
    # independent clones/branches). See DocId and ID_STYLES.
    id_style: str = DEFAULT_ID_STYLE
    # Per-type relation whitelist: ``kind -> allowed target types`` (an empty
    # target list means "any type"). An *empty* mapping means the type is
    # unconstrained (any registered kind, any target) — the permissive default.
    allowed_relations: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # Review cadence in days for staleness. ``0`` means the type is never
    # considered stale (no human re-verification is expected).
    review_days: int = 0

    def is_valid_status(self, status: str) -> bool:
        return status in self.statuses

    def can_transition(self, current: str, target: str) -> bool:
        """Whether ``current -> target`` is allowed (a self-loop is always ok)."""
        if current == target:
            return True
        return target in self.transitions.get(current, frozenset())

    def allows_relation(self, kind: str, target_type: str) -> bool:
        """Whether this source type may declare a ``kind`` edge to ``target_type``.

        An empty ``allowed_relations`` mapping is permissive (any kind, any
        target). Otherwise it is a whitelist: the kind must be listed, and the
        target's type must be in that kind's allowed set (empty set = any type).
        """
        if not self.allowed_relations:
            return True
        if kind not in self.allowed_relations:
            return False
        targets = self.allowed_relations[kind]
        return not targets or target_type in targets


@dataclass(frozen=True, slots=True)
class Schema:
    """The full set of document-type grammars."""

    types: dict[str, TypeSchema] = field(default_factory=dict)
    # The registry of valid relation kinds (``supersedes``, ``depends_on`` ...).
    # An *empty* set means relation kinds are unconstrained — the permissive
    # backward-compatible default for schemas that predate typed edges.
    relation_types: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        prefixes: dict[str, str] = {}
        for type_schema in self.types.values():
            if type_schema.default_status not in type_schema.statuses:
                raise SchemaError(
                    f"type {type_schema.name!r}: default status "
                    f"{type_schema.default_status!r} not in its status enum"
                )
            if type_schema.prefix in prefixes:
                raise SchemaError(
                    f"prefix {type_schema.prefix!r} used by both "
                    f"{prefixes[type_schema.prefix]!r} and {type_schema.name!r}"
                )
            prefixes[type_schema.prefix] = type_schema.name
            if self.relation_types:
                for kind in type_schema.allowed_relations:
                    if kind not in self.relation_types:
                        raise SchemaError(
                            f"type {type_schema.name!r} allows unknown relation "
                            f"kind {kind!r}; add it to 'relation_types'"
                        )

    def is_known_relation_kind(self, kind: str) -> bool:
        """Whether ``kind`` is a registered relation kind (always true if unconfigured)."""
        return not self.relation_types or kind in self.relation_types

    def review_days_for(self, doc_type: str) -> int:
        """The review cadence in days for a type (``0`` = never stale)."""
        return self.get(doc_type).review_days

    def get(self, doc_type: str) -> TypeSchema:
        try:
            return self.types[doc_type]
        except KeyError:
            known = ", ".join(sorted(self.types)) or "<none>"
            raise UnknownDocumentTypeError(
                f"unknown document type {doc_type!r}; known types: {known}"
            ) from None

    def prefix_for(self, doc_type: str) -> str:
        return self.get(doc_type).prefix

    def default_status_for(self, doc_type: str) -> str:
        return self.get(doc_type).default_status

    def inactive_statuses(self) -> frozenset[str]:
        """Union of all types' closed statuses (default read-path exclusion)."""
        result: set[str] = set()
        for type_schema in self.types.values():
            result.update(type_schema.inactive_statuses)
        return frozenset(result)

    def validate_status(self, doc_type: str, status: str) -> None:
        type_schema = self.get(doc_type)
        if not type_schema.is_valid_status(status):
            valid = ", ".join(type_schema.statuses)
            raise InvalidStatusError(
                f"invalid status {status!r} for type {doc_type!r}; valid statuses: {valid}"
            )

    def validate_transition(self, doc_type: str, current: str, target: str) -> None:
        self.validate_status(doc_type, target)
        type_schema = self.get(doc_type)
        if not type_schema.can_transition(current, target):
            raise InvalidStatusTransitionError(
                f"invalid transition {current!r} -> {target!r} for type {doc_type!r}"
            )
