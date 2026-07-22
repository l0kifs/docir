"""Allocate document ids as ``<type-prefix>-NNNN``.

The next number comes from the index (via the repository), never from scanning
files — this avoids collisions between parallel agents allocating ids at the
same time.
"""

from __future__ import annotations

from docir.modules.documents.domain.schema import Schema
from docir.modules.documents.domain.value_objects.identifiers import DocId
from docir.platform.persistence.ports import DocumentRepository

# Retry budget for random-id allocation; each attempt has ~1-in-2^48 odds of
# colliding, so this is never realistically exhausted.
_MAX_RANDOM_ATTEMPTS = 1000


class IdGenerator:
    """Generates fresh :class:`DocId` values for a document type."""

    def __init__(self, schema: Schema, documents: DocumentRepository) -> None:
        self._schema = schema
        self._documents = documents

    def next_id(self, doc_type: str) -> DocId:
        """Allocate the next free id for ``doc_type``.

        ``sequential`` types draw from the index counter; ``random`` types mint
        a hex token, retrying on the (astronomically unlikely) local collision.
        """
        type_schema = self._schema.get(doc_type)
        if type_schema.id_style == "random":
            for _ in range(_MAX_RANDOM_ATTEMPTS):
                candidate = DocId.build_random(type_schema.prefix)
                if not self._documents.exists(candidate.value):
                    return candidate
            raise RuntimeError(f"could not allocate a unique random id for {doc_type!r}")
        number = self._documents.next_number(type_schema.prefix)
        return DocId.build(type_schema.prefix, number)
