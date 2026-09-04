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
    # Why this document is meant to carry no relations; empty means not exempt.
    # Indexed because `orphan` reads it for every document in the corpus and
    # `query --expr "isolated"` is how the exemptions are audited.
    isolated: Mapped[str] = mapped_column(String, nullable=False, default="")

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


class DocumentCodeRow(Base):
    """One repo-relative glob a document governs. See issue-90aea6d1b891.

    A child table rather than a column, following ``document_tags``: the value
    is a set of patterns, and the question asked of it — "which documents
    govern this path?" — reads the patterns, not the document.
    """

    __tablename__ = "document_code"

    doc_id: Mapped[str] = mapped_column(
        String, ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    pattern: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    # The digest of what this pattern matched when the document was last
    # verified. Nullable and non-key: a pattern is declared long before anyone
    # verifies against it, and NULL is the unknown answer `check` skips.
    digest: Mapped[str | None] = mapped_column(String, nullable=True)


class MentionRow(Base):
    """One document id named in another document's body. See adr-<mentions>.

    Derived, like the FTS index and the vectors: recomputed from the body on
    every save, never written back to frontmatter. Kept out of ``relations``
    deliberately — that table is the *authored* graph, and the checks that read
    it (dangling, cycle, layering) and the delete guard must not start seeing
    edges nobody wrote.

    ``target`` carries no foreign key: a body may name an id that does not
    exist yet, and resolution is a read-time join, so a forward reference starts
    resolving when its target is written rather than when the mentioning
    document is next saved.
    """

    __tablename__ = "mentions"

    source: Mapped[str] = mapped_column(
        String, ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    target: Mapped[str] = mapped_column(String, primary_key=True, index=True)


class EmbeddingRow(Base):
    __tablename__ = "embeddings"

    doc_id: Mapped[str] = mapped_column(
        String, ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    vector: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    dirty: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    model_id: Mapped[str | None] = mapped_column(String, nullable=True)


class ChunkEmbeddingRow(Base):
    """One section's vector. See adr-927aa43d9635 and migration ``0003``.

    Keyed ``(doc_id, ordinal)``: a chunk has no identity beyond its position in
    a body, and the whole set for a document is replaced together whenever that
    body changes.
    """

    __tablename__ = "chunk_embeddings"

    doc_id: Mapped[str] = mapped_column(
        String, ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    heading: Mapped[str] = mapped_column(String, nullable=False, default="")
    vector: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    model_id: Mapped[str | None] = mapped_column(String, nullable=True)


class SequenceRow(Base):
    __tablename__ = "id_sequences"

    prefix: Mapped[str] = mapped_column(String, primary_key=True)
    next_value: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class SchemaBaselineRow(Base):
    """The resolved schema the index was last rebuilt against (one row)."""

    __tablename__ = "schema_baseline"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)


class IndexBuildRow(Base):
    """The docir version that last rebuilt the index (one row).

    Beside the schema baseline rather than inside it: that payload is diffed and
    printed, so a version key in it would report every upgrade as a schema
    change.
    """

    __tablename__ = "index_build"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    docir_version: Mapped[str] = mapped_column(Text, nullable=False)
