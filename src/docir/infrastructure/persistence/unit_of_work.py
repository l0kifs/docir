"""The SQLAlchemy-backed :class:`UnitOfWork`.

Opening a unit of work starts a session/transaction; ``commit`` persists all
staged repository work atomically, and exiting the context always closes the
session (rolling back anything uncommitted). Because the daemon serializes
requests, one write transaction runs at a time, which resolves most
write-conflict races without extra file locking.
"""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.orm import Session, sessionmaker

from docir.domain.ports.unit_of_work import UnitOfWork
from docir.infrastructure.persistence.repositories import (
    SqlAlchemyDocumentRepository,
    SqlAlchemyEmbeddingRepository,
    SqlAlchemySearchIndex,
    SqlAlchemyTagRepository,
)


class SqlAlchemyUnitOfWork(UnitOfWork):
    """A unit of work bound to a fresh session per ``with`` block."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> SqlAlchemyUnitOfWork:
        session = self._session_factory()
        self._session = session
        self.documents = SqlAlchemyDocumentRepository(session)
        self.tags = SqlAlchemyTagRepository(session)
        self.search = SqlAlchemySearchIndex(session)
        self.embeddings = SqlAlchemyEmbeddingRepository(session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _tb: TracebackType | None,
    ) -> None:
        try:
            if exc_type is not None and self._session is not None:
                self._session.rollback()
        finally:
            if self._session is not None:
                self._session.close()
                self._session = None

    def commit(self) -> None:
        assert self._session is not None, "unit of work is not active"
        self._session.commit()

    def rollback(self) -> None:
        if self._session is not None:
            self._session.rollback()
