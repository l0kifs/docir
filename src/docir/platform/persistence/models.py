"""SQLAlchemy 2.0 declarative models for the derived index.

The FTS5 virtual table (``documents_fts``) is *not* an ORM model — it is
created by the Alembic migration as raw DDL and queried through SQLAlchemy Core
text() in the search repository.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base carrying the index metadata."""


class DocumentRow(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    created: Mapped[str] = mapped_column(String, nullable=False)
    updated: Mapped[str] = mapped_column(String, nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    path: Mapped[str | None] = mapped_column(String, nullable=True)
    content_hash: Mapped[str] = mapped_column(String, nullable=False, default="")
    # Stewardship metadata for staleness (both optional).
    owner: Mapped[str] = mapped_column(String, nullable=False, default="")
    verified: Mapped[str | None] = mapped_column(String, nullable=True)

    tags: Mapped[list[DocumentTagRow]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )
    outgoing: Mapped[list[RelationRow]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="RelationRow.source",
    )


class RelationRow(Base):
    __tablename__ = "relations"

    source: Mapped[str] = mapped_column(
        String, ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    target: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    # The typed edge kind (``relates_to``, ``supersedes``, ``depends_on`` ...).
    # Not part of the primary key: at most one edge kind per ordered pair.
    kind: Mapped[str] = mapped_column(String, nullable=False, default="relates_to")


class TagRow(Base):
    __tablename__ = "tags"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")


class DocumentTagRow(Base):
    __tablename__ = "document_tags"

    doc_id: Mapped[str] = mapped_column(
        String, ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    tag_key: Mapped[str] = mapped_column(String, primary_key=True, index=True)


class EmbeddingRow(Base):
    __tablename__ = "embeddings"

    doc_id: Mapped[str] = mapped_column(
        String, ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    vector: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    dirty: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    model_id: Mapped[str | None] = mapped_column(String, nullable=True)


class SequenceRow(Base):
    __tablename__ = "id_sequences"

    prefix: Mapped[str] = mapped_column(String, primary_key=True)
    next_value: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
