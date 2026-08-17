"""Concrete SQLAlchemy implementations of the domain repository ports.

Each repository is bound to a single :class:`~sqlalchemy.orm.Session` (owned by
the unit of work) and translates between ORM rows and domain entities.
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection, Sequence
from datetime import date

from sqlalchemy import delete, func, select
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.entities.relation import Relation
from docir.modules.documents.domain.value_objects.queries import DocumentFilter
from docir.modules.documents.domain.value_objects.relations import RelatedRef
from docir.modules.indexing.domain.results import SearchHit
from docir.modules.tags.domain.entities.tag import Tag
from docir.platform.embedding.vector import Embedding
from docir.platform.persistence.models import (
    ChunkEmbeddingRow,
    DocumentCodeRow,
    DocumentRow,
    DocumentTagRow,
    EmbeddingRow,
    IndexBuildRow,
    RelationRow,
    SchemaBaselineRow,
    TagRow,
)
from docir.platform.persistence.ports import (
    ChunkEmbeddingRepository,
    DocumentRepository,
    EmbeddingRepository,
    IndexBuildRepository,
    SchemaBaselineRepository,
    SearchIndex,
    StoredChunk,
    TagRepository,
)

# Tokens for a safe FTS5 MATCH query (letters/digits, optionally with '_' / '-').
_TOKEN_RE = re.compile(r"[\w-]+", re.UNICODE)


class SqlAlchemyDocumentRepository(DocumentRepository):
    """Document metadata + relation graph, backed by SQLAlchemy."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def next_number(self, prefix: str) -> int:
        """Atomically claim the next number for ``prefix``.

        One statement, deliberately: read-modify-write in Python let two
        concurrent processes read the same value and both return it, so N
        parallel ``docir --no-daemon add`` calls all minted the same id. Inside a
        single upsert the increment happens under SQLite's write lock, so a
        second transaction blocks and then reads the *committed* value.
        """
        value = self._session.execute(
            sql_text(
                "INSERT INTO id_sequences (prefix, next_value) VALUES (:prefix, 2) "
                "ON CONFLICT(prefix) DO UPDATE SET next_value = next_value + 1 "
                "RETURNING next_value - 1"
            ),
            {"prefix": prefix},
        ).scalar_one()
        return int(value)

    def raise_next_number(self, prefix: str, minimum: int) -> None:
        self._session.execute(
            sql_text(
                "INSERT INTO id_sequences (prefix, next_value) VALUES (:prefix, :minimum) "
                "ON CONFLICT(prefix) DO UPDATE SET next_value = MAX(next_value, :minimum)"
            ),
            {"prefix": prefix, "minimum": minimum},
        )

    def save(self, document: Document) -> None:
        row = self._session.get(DocumentRow, document.id)
        if row is None:
            row = DocumentRow(id=document.id)
            self._session.add(row)
        row.title = document.title
        row.description = document.description
        row.type = document.type
        row.status = document.status
        row.created = document.created.isoformat()
        row.updated = document.updated.isoformat()
        row.archived = document.archived
        row.body = document.body
        row.path = document.path
        row.content_hash = document.content_hash()
        row.owner = document.owner
        row.verified = None if document.verified is None else document.verified.isoformat()

        self._session.execute(delete(DocumentTagRow).where(DocumentTagRow.doc_id == document.id))
        self._session.execute(delete(RelationRow).where(RelationRow.source == document.id))
        self._session.execute(delete(DocumentCodeRow).where(DocumentCodeRow.doc_id == document.id))
        self._session.flush()
        for key in document.tags:
            self._session.add(DocumentTagRow(doc_id=document.id, tag_key=key))
        # Deduped: the pattern is half the primary key, so a document listing
        # one glob twice would otherwise fail the insert rather than the write.
        for pattern in dict.fromkeys(document.code):
            self._session.add(
                DocumentCodeRow(
                    doc_id=document.id,
                    pattern=pattern,
                    digest=document.verified_code.get(pattern),
                )
            )
        # At most one edge per ordered pair (kind is not in the primary key);
        # if the source lists a target twice, the last kind wins.
        edges: dict[str, str] = {ref.target: ref.kind for ref in document.related}
        for target, kind in edges.items():
            self._session.add(RelationRow(source=document.id, target=target, kind=kind))
        self._session.flush()

    def get(self, doc_id: str) -> Document | None:
        row = self._session.get(DocumentRow, doc_id)
        if row is None:
            return None
        tags = self._tags_for(doc_id)
        related = self._related_for(doc_id)
        return _to_document(row, tags, related, self._code_for(doc_id))

    def exists(self, doc_id: str) -> bool:
        return self._session.get(DocumentRow, doc_id) is not None

    def delete(self, doc_id: str) -> None:
        row = self._session.get(DocumentRow, doc_id)
        if row is not None:
            self._session.delete(row)
            self._session.flush()

    def all(self) -> list[Document]:
        rows = self._session.scalars(select(DocumentRow)).all()
        return self._hydrate(list(rows))

    def query(self, spec: DocumentFilter) -> list[Document]:
        stmt = select(DocumentRow)
        if spec.types:
            stmt = stmt.where(DocumentRow.type.in_(spec.types))
        if spec.statuses:
            stmt = stmt.where(DocumentRow.status.in_(spec.statuses))
        if not spec.include_archived:
            stmt = stmt.where(DocumentRow.archived.is_(False))
        if spec.inactive_statuses and not spec.include_inactive:
            stmt = stmt.where(DocumentRow.status.notin_(spec.inactive_statuses))
        if spec.owner is not None:
            stmt = stmt.where(DocumentRow.owner == spec.owner)
        if spec.tags:
            for key in spec.tags:
                stmt = stmt.where(
                    DocumentRow.id.in_(
                        select(DocumentTagRow.doc_id).where(DocumentTagRow.tag_key == key)
                    )
                )
        # Ordered before the window, so a page is stable across calls.
        stmt = stmt.order_by(DocumentRow.created.desc(), DocumentRow.id)
        if spec.offset:
            stmt = stmt.offset(spec.offset)
        if spec.limit is not None:
            stmt = stmt.limit(spec.limit)
        rows = self._session.scalars(stmt).all()
        return self._hydrate(list(rows))

    def outgoing(self, doc_id: str) -> list[str]:
        return self._outgoing_for(doc_id)

    def incoming(self, doc_id: str, kinds: Collection[str] | None = None) -> list[str]:
        stmt = select(RelationRow.source).where(RelationRow.target == doc_id)
        if kinds is not None:
            stmt = stmt.where(RelationRow.kind.in_(tuple(kinds)))
        return sorted(self._session.scalars(stmt).all())

    def relations(self) -> list[Relation]:
        rows = self._session.execute(
            select(RelationRow.source, RelationRow.target, RelationRow.kind)
        ).all()
        return [Relation(source=src, target=tgt, kind=kind) for src, tgt, kind in rows]

    # -- helpers ------------------------------------------------------------

    def _tags_for(self, doc_id: str) -> tuple[str, ...]:
        stmt = (
            select(DocumentTagRow.tag_key)
            .where(DocumentTagRow.doc_id == doc_id)
            .order_by(DocumentTagRow.tag_key)
        )
        return tuple(self._session.scalars(stmt).all())

    def _code_for(self, doc_id: str) -> list[tuple[str, str | None]]:
        """The document's globs with the digest each was last verified against.

        Read together because they are stored together: the digest belongs to
        the pattern, and a query that returned one without the other would let
        the caller pair them up itself — the mistake keying the map by pattern
        exists to prevent.
        """
        stmt = (
            select(DocumentCodeRow.pattern, DocumentCodeRow.digest)
            .where(DocumentCodeRow.doc_id == doc_id)
            .order_by(DocumentCodeRow.pattern)
        )
        return [(pattern, digest) for pattern, digest in self._session.execute(stmt).all()]

    def _outgoing_for(self, doc_id: str) -> list[str]:
        stmt = (
            select(RelationRow.target)
            .where(RelationRow.source == doc_id)
            .order_by(RelationRow.target)
        )
        return list(self._session.scalars(stmt).all())

    def _related_for(self, doc_id: str) -> list[RelatedRef]:
        stmt = (
            select(RelationRow.target, RelationRow.kind)
            .where(RelationRow.source == doc_id)
            .order_by(RelationRow.target)
        )
        return [
            RelatedRef(target=tgt, kind=kind) for tgt, kind in self._session.execute(stmt).all()
        ]

    def _hydrate(self, rows: list[DocumentRow]) -> list[Document]:
        if not rows:
            return []
        ids = [row.id for row in rows]
        tag_map: dict[str, list[str]] = {row.id: [] for row in rows}
        rel_map: dict[str, list[RelatedRef]] = {row.id: [] for row in rows}
        code_map: dict[str, list[tuple[str, str | None]]] = {row.id: [] for row in rows}
        for doc_id, key in self._session.execute(
            select(DocumentTagRow.doc_id, DocumentTagRow.tag_key)
            .where(DocumentTagRow.doc_id.in_(ids))
            .order_by(DocumentTagRow.tag_key)
        ).all():
            tag_map[doc_id].append(key)
        for source, target, kind in self._session.execute(
            select(RelationRow.source, RelationRow.target, RelationRow.kind)
            .where(RelationRow.source.in_(ids))
            .order_by(RelationRow.target)
        ).all():
            rel_map[source].append(RelatedRef(target=target, kind=kind))
        for doc_id, pattern, digest in self._session.execute(
            select(DocumentCodeRow.doc_id, DocumentCodeRow.pattern, DocumentCodeRow.digest)
            .where(DocumentCodeRow.doc_id.in_(ids))
            .order_by(DocumentCodeRow.pattern)
        ).all():
            code_map[doc_id].append((pattern, digest))
        return [
            _to_document(row, tuple(tag_map[row.id]), rel_map[row.id], code_map[row.id])
            for row in rows
        ]


class SqlAlchemyTagRepository(TagRepository):
    """The tag registry, backed by SQLAlchemy."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, tag: Tag) -> None:
        row = self._session.get(TagRow, tag.key)
        if row is None:
            row = TagRow(key=tag.key)
            self._session.add(row)
        row.description = tag.description
        self._session.flush()

    def get(self, key: str) -> Tag | None:
        row = self._session.get(TagRow, key)
        return None if row is None else Tag(key=row.key, description=row.description)

    def exists(self, key: str) -> bool:
        return self._session.get(TagRow, key) is not None

    def all(self) -> list[Tag]:
        rows = self._session.scalars(select(TagRow).order_by(TagRow.key)).all()
        return [Tag(key=row.key, description=row.description) for row in rows]

    def page(self, *, limit: int, offset: int) -> list[Tag]:
        stmt = select(TagRow).order_by(TagRow.key).offset(offset).limit(limit)
        rows = self._session.scalars(stmt).all()
        return [Tag(key=row.key, description=row.description) for row in rows]

    def usage_counts(self, keys: Collection[str]) -> dict[str, int]:
        if not keys:
            return {}
        stmt = (
            select(DocumentTagRow.tag_key, func.count())
            .where(DocumentTagRow.tag_key.in_(list(keys)))
            .group_by(DocumentTagRow.tag_key)
        )
        return {str(key): int(count) for key, count in self._session.execute(stmt).all()}

    def delete(self, key: str) -> None:
        row = self._session.get(TagRow, key)
        if row is not None:
            self._session.delete(row)
            self._session.flush()


class SqlAlchemySearchIndex(SearchIndex):
    """The FTS5 full-text projection, driven via SQLAlchemy Core."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def index(self, document: Document) -> None:
        self.remove(document.id)
        self._session.execute(
            sql_text(
                "INSERT INTO documents_fts (doc_id, title, description, body) "
                "VALUES (:doc_id, :title, :description, :body)"
            ),
            {
                "doc_id": document.id,
                "title": document.title,
                "description": document.description,
                "body": document.body,
            },
        )

    def remove(self, doc_id: str) -> None:
        self._session.execute(
            sql_text("DELETE FROM documents_fts WHERE doc_id = :doc_id"),
            {"doc_id": doc_id},
        )

    def search(self, text: str, limit: int) -> list[SearchHit]:
        match = _to_match_query(text)
        if not match:
            return []
        rows = self._session.execute(
            sql_text(
                "SELECT doc_id, bm25(documents_fts) AS score "
                "FROM documents_fts WHERE documents_fts MATCH :q "
                "ORDER BY score LIMIT :limit"
            ),
            {"q": match, "limit": limit},
        ).all()
        return [SearchHit(doc_id=doc_id, bm25=score) for doc_id, score in rows]


class SqlAlchemyEmbeddingRepository(EmbeddingRepository):
    """Embedding vectors and the dirty-flag queue, backed by SQLAlchemy."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def mark_dirty(self, doc_id: str) -> None:
        row = self._get_or_create(doc_id)
        row.dirty = True
        self._session.flush()

    def clear_dirty(self, doc_id: str) -> None:
        row = self._session.get(EmbeddingRow, doc_id)
        if row is not None:
            row.dirty = False
            self._session.flush()

    def dirty_ids(self, model_id: str) -> list[str]:
        # A vector from another model counts as dirty: it is not comparable with
        # the current one, so it has to be recomputed rather than reused.
        stmt = (
            select(EmbeddingRow.doc_id)
            .where(
                EmbeddingRow.dirty.is_(True)
                | EmbeddingRow.model_id.is_(None)
                | (EmbeddingRow.model_id != model_id)
            )
            .order_by(EmbeddingRow.doc_id)
        )
        return list(self._session.scalars(stmt).all())

    def set_vector(self, doc_id: str, embedding: Embedding, model_id: str) -> None:
        row = self._get_or_create(doc_id)
        row.vector = embedding.to_bytes()
        row.model_id = model_id
        row.dirty = False
        self._session.flush()

    def get_vector(self, doc_id: str) -> Embedding | None:
        row = self._session.get(EmbeddingRow, doc_id)
        if row is None or row.vector is None:
            return None
        return Embedding.from_bytes(row.vector)

    def remove(self, doc_id: str) -> None:
        row = self._session.get(EmbeddingRow, doc_id)
        if row is not None:
            self._session.delete(row)
            self._session.flush()

    def active_vectors(self, model_id: str) -> list[tuple[str, Embedding]]:
        stmt = (
            select(EmbeddingRow.doc_id, EmbeddingRow.vector)
            .join(DocumentRow, DocumentRow.id == EmbeddingRow.doc_id)
            .where(DocumentRow.archived.is_(False))
            .where(EmbeddingRow.vector.is_not(None))
            .where(EmbeddingRow.model_id == model_id)
            .order_by(EmbeddingRow.doc_id)
        )
        result: list[tuple[str, Embedding]] = []
        for doc_id, blob in self._session.execute(stmt).all():
            result.append((doc_id, Embedding.from_bytes(blob)))
        return result

    def _get_or_create(self, doc_id: str) -> EmbeddingRow:
        row = self._session.get(EmbeddingRow, doc_id)
        if row is None:
            row = EmbeddingRow(doc_id=doc_id, vector=None, dirty=True)
            self._session.add(row)
        return row


class SqlAlchemyChunkEmbeddingRepository(ChunkEmbeddingRepository):
    """Per-section vectors, backed by SQLAlchemy."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def replace(self, doc_id: str, chunks: Sequence[StoredChunk], model_id: str) -> None:
        self._session.execute(delete(ChunkEmbeddingRow).where(ChunkEmbeddingRow.doc_id == doc_id))
        for chunk in chunks:
            self._session.add(
                ChunkEmbeddingRow(
                    doc_id=doc_id,
                    ordinal=chunk.ordinal,
                    heading=chunk.heading,
                    vector=chunk.vector.to_bytes(),
                    model_id=model_id,
                )
            )
        self._session.flush()

    def remove(self, doc_id: str) -> None:
        self._session.execute(delete(ChunkEmbeddingRow).where(ChunkEmbeddingRow.doc_id == doc_id))
        self._session.flush()

    def active_vectors(self, model_id: str) -> list[tuple[str, str, Embedding]]:
        stmt = (
            select(ChunkEmbeddingRow.doc_id, ChunkEmbeddingRow.heading, ChunkEmbeddingRow.vector)
            .join(DocumentRow, DocumentRow.id == ChunkEmbeddingRow.doc_id)
            .where(DocumentRow.archived.is_(False))
            .where(ChunkEmbeddingRow.vector.is_not(None))
            .where(ChunkEmbeddingRow.model_id == model_id)
            .order_by(ChunkEmbeddingRow.doc_id, ChunkEmbeddingRow.ordinal)
        )
        return [
            (doc_id, heading, Embedding.from_bytes(blob))
            for doc_id, heading, blob in self._session.execute(stmt).all()
        ]

    def headings(self, doc_id: str) -> list[str]:
        stmt = (
            select(ChunkEmbeddingRow.heading)
            .where(ChunkEmbeddingRow.doc_id == doc_id)
            .order_by(ChunkEmbeddingRow.ordinal)
        )
        return list(self._session.scalars(stmt).all())


# -- module helpers ---------------------------------------------------------


def _to_document(
    row: DocumentRow,
    tags: tuple[str, ...],
    related: list[RelatedRef],
    code: list[tuple[str, str | None]] | None = None,
) -> Document:
    code = code or []
    return Document(
        id=row.id,
        title=row.title,
        description=row.description,
        type=row.type,
        status=row.status,
        created=date.fromisoformat(row.created),
        updated=date.fromisoformat(row.updated),
        tags=tuple(tags),
        related=tuple(related),
        archived=row.archived,
        body=row.body,
        path=row.path,
        owner=row.owner,
        verified=None if row.verified is None else date.fromisoformat(row.verified),
        code=tuple(pattern for pattern, _ in code),
        verified_code={pattern: digest for pattern, digest in code if digest is not None},
    )


def _to_match_query(raw: str) -> str:
    """Turn free text into a safe FTS5 OR-of-terms MATCH expression."""
    tokens = _TOKEN_RE.findall(raw.lower())
    if not tokens:
        return ""
    return " OR ".join(f'"{token}"' for token in tokens)


def count_documents(session: Session) -> int:
    """Convenience count used by health checks and tests."""
    return session.scalar(select(func.count()).select_from(DocumentRow)) or 0


class SqlAlchemySchemaBaselineRepository(SchemaBaselineRepository):
    """The single-row schema baseline, stored as JSON text.

    JSON rather than a column per field: the payload is the documents module's
    own rendering of a schema, so anything structural here would be a second
    definition of that shape — kept in a table, migrated separately, and free to
    fall behind. The drift check compares two payloads and never reads a field,
    which is exactly the access pattern a blob suits.
    """

    _ROW_ID = 1

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self) -> dict[str, object] | None:
        row = self._session.get(SchemaBaselineRow, self._ROW_ID)
        if row is None:
            return None
        try:
            payload = json.loads(row.payload)
        except json.JSONDecodeError:
            # Derived state: an unreadable baseline is a baseline we do not
            # have. Raising here would break `check` over a row nothing but
            # `reindex` can repair — and `reindex` overwrites it anyway.
            return None
        return payload if isinstance(payload, dict) else None

    def set(self, payload: dict[str, object]) -> None:
        encoded = json.dumps(payload, sort_keys=True)
        row = self._session.get(SchemaBaselineRow, self._ROW_ID)
        if row is None:
            self._session.add(SchemaBaselineRow(id=self._ROW_ID, payload=encoded))
        else:
            row.payload = encoded


class SqlAlchemyIndexBuildRepository(IndexBuildRepository):
    """The single-row record of which docir version last rebuilt the index."""

    _ROW_ID = 1

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self) -> str | None:
        row = self._session.get(IndexBuildRow, self._ROW_ID)
        return row.docir_version if row is not None else None

    def set(self, version: str) -> None:
        row = self._session.get(IndexBuildRow, self._ROW_ID)
        if row is None:
            self._session.add(IndexBuildRow(id=self._ROW_ID, docir_version=version))
        else:
            row.docir_version = version
