"""The :class:`UnitOfWork` port — a transactional boundary.

A unit of work groups the repositories that must commit together (metadata,
tags, full-text, embeddings) into a single atomic transaction. Use cases open
one, mutate through its repositories, and ``commit()`` — or let ``__exit__``
roll back on error. This is where the architecture's "write operations are
serialized, resolving most write-conflict races" guarantee is enforced.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from types import TracebackType

from docir.platform.persistence.ports import (
    ChunkEmbeddingRepository,
    DocumentRepository,
    EmbeddingRepository,
    SearchIndex,
    TagRepository,
)


class UnitOfWork(ABC):
    """A context-managed atomic transaction exposing the repositories."""

    documents: DocumentRepository
    tags: TagRepository
    search: SearchIndex
    embeddings: EmbeddingRepository
    chunks: ChunkEmbeddingRepository

    def __enter__(self) -> UnitOfWork:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            self.rollback()
        else:
            self.rollback()  # no-op if already committed; discards uncommitted work

    @abstractmethod
    def commit(self) -> None:
        """Flush and durably persist everything staged in this unit of work."""

    @abstractmethod
    def rollback(self) -> None:
        """Discard everything staged since the last commit."""
