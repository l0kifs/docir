"""Tier 0 validation — the synchronous, blocking hard checks.

These run inline in every ``docs add`` / ``docs update`` call, like a compiler.
They are deterministic and essentially free of false positives: missing
required fields, invalid status values/transitions, and dangling ``tags`` /
``related`` references. Graph-shape and content heuristics deliberately live in
Tier 1/2, not here.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.schema import CORE_REQUIRED_FIELDS, Schema
from docir.modules.documents.domain.value_objects.relations import RelatedRef
from docir.platform.errors import (
    DisallowedRelationError,
    MissingRequiredFieldError,
    UnknownRelatedError,
    UnknownRelationKindError,
    UnknownTagError,
)


class Tier0Validator:
    """Runs the hard, write-blocking validation rules against the schema."""

    def __init__(self, schema: Schema) -> None:
        self._schema = schema

    def validate_required_fields(self, document: Document) -> None:
        """Ensure core and type-specific required fields are non-empty."""
        type_schema = self._schema.get(document.type)
        required = set(CORE_REQUIRED_FIELDS) | set(type_schema.required_fields)
        for name in sorted(required):
            value = getattr(document, name, None)
            if value is None or (isinstance(value, str) and not value.strip()):
                raise MissingRequiredFieldError(
                    f"required field {name!r} is missing or empty for type {document.type!r}"
                )

    def validate_status(self, doc_type: str, status: str) -> None:
        """Ensure a status value is part of the type's enum."""
        self._schema.validate_status(doc_type, status)

    def validate_transition(self, doc_type: str, current: str, target: str) -> None:
        """Ensure a status transition is permitted by the type's schema."""
        self._schema.validate_transition(doc_type, current, target)

    def validate_tags(self, tags: Iterable[str], known_keys: Iterable[str]) -> None:
        """Every tag key must already exist in the registry."""
        registry = set(known_keys)
        for key in tags:
            if key not in registry:
                raise UnknownTagError(
                    f"unknown tag {key!r}; register it first with "
                    f"`docir tag add {key} --description ...`"
                )

    def validate_related(self, related: Iterable[str], known_ids: Iterable[str]) -> None:
        """Every ``related`` id must already exist in the index."""
        existing = set(known_ids)
        for ref in related:
            if ref not in existing:
                raise UnknownRelatedError(f"related document {ref!r} does not exist in the index")

    def validate_relation_kinds(
        self,
        source_type: str,
        refs: Iterable[RelatedRef],
        id_to_type: Mapping[str, str],
    ) -> None:
        """Each edge's kind must be registered and permitted by the source type.

        Runs *after* :meth:`validate_related` has confirmed the targets exist, so
        an unknown target (absent from ``id_to_type``) is left to that check.
        """
        source_schema = self._schema.get(source_type)
        for ref in refs:
            if not self._schema.is_known_relation_kind(ref.kind):
                known = ", ".join(sorted(self._schema.relation_types)) or "<none>"
                raise UnknownRelationKindError(
                    f"unknown relation kind {ref.kind!r}; known kinds: {known}"
                )
            target_type = id_to_type.get(ref.target)
            if target_type is None:
                continue
            if not source_schema.allows_relation(ref.kind, target_type):
                raise DisallowedRelationError(
                    f"type {source_type!r} may not declare a {ref.kind!r} relation "
                    f"to a {target_type!r} document ({ref.target!r})"
                )
