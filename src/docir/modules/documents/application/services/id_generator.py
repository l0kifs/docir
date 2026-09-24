"""Allocate document ids as ``<type-prefix>-NNNN`` or ``<type-prefix>-<hex token>``.

The next number comes from the index (via the repository), never from scanning
files — this avoids collisions between parallel agents allocating ids at the
same time.
"""

from __future__ import annotations

from functools import partial

from docir.modules.documents.domain.schema import (
    CHRONOLOGICAL_ID_STYLE,
    RANDOM_ID_STYLE,
    Schema,
)
from docir.modules.documents.domain.value_objects.identifiers import DocId
from docir.platform.clock import Clock
from docir.platform.persistence.ports import DocumentRepository

# Retry budget for random-id allocation; each attempt has ~1-in-2^48 odds of
# colliding, so this is never realistically exhausted. A chronological attempt
# shares it: only its 16-bit tail is random, but a collision also needs the
# same second, so the budget is still never reached.
_MAX_RANDOM_ATTEMPTS = 1000

# Retry budget for sequential allocation. Each attempt burns one counter value,
# so this only runs when the counter lags behind the indexed ids; a healthy
# store returns on the first attempt.
_MAX_SEQUENTIAL_ATTEMPTS = 1000


class IdGenerator:
    """Generates fresh :class:`DocId` values for a document type."""

    def __init__(self, schema: Schema, documents: DocumentRepository, clock: Clock) -> None:
        self._schema = schema
        self._documents = documents
        self._clock = clock

    def next_id(self, doc_type: str, *, replacing: DocId | None = None) -> DocId:
        """Allocate the next free id for ``doc_type``.

        ``sequential`` types draw from the index counter; ``random`` and
        ``chronological`` types mint a hex token, retrying on the (astronomically
        unlikely) local collision.

        ``replacing`` is the id a re-issue gives up. A chronological type keeps
        its leading second, so the re-issued file stays where it sorted instead of
        moving to the moment of the repair.
        """
        type_schema = self._schema.get(doc_type)
        style = type_schema.id_style
        if style in (RANDOM_ID_STYLE, CHRONOLOGICAL_ID_STYLE):
            prefix = type_schema.prefix
            if style == CHRONOLOGICAL_ID_STYLE:
                kept = replacing.leading_second if replacing is not None else None
                second = kept if kept is not None else int(self._clock.now().timestamp())
                mint = partial(DocId.build_chronological, prefix, second)
            else:
                mint = partial(DocId.build_random, prefix)
            for _ in range(_MAX_RANDOM_ATTEMPTS):
                candidate = mint()
                if not self._documents.exists(candidate.value):
                    return candidate
            raise RuntimeError(f"could not allocate a unique {style} id for {doc_type!r}")
        # The counter alone is not proof that an id is free: it lives in the
        # derived index, so a store rebuilt by an older docir (or seeded by hand)
        # can still point at a live id. Skip past anything already indexed.
        prefix = type_schema.prefix
        for _ in range(_MAX_SEQUENTIAL_ATTEMPTS):
            candidate = DocId.build(prefix, self._documents.next_number(prefix))
            if not self._documents.exists(candidate.value):
                return candidate
        raise RuntimeError(f"could not allocate a free sequential id for prefix {prefix!r}")
