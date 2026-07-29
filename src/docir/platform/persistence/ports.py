"""Repository ports — the persistence contracts the use cases depend on.

Each is an abstract interface. Concrete implementations (SQLAlchemy-backed,
or in-memory fakes for tests) live in the infrastructure layer. Splitting the
index into focused repositories keeps each concern (metadata + graph, tags,
full-text, embeddings) independently substitutable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Collection

from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.entities.relation import Relation
from docir.modules.documents.domain.value_objects.queries import DocumentFilter
from docir.modules.indexing.domain.results import SearchHit
from docir.modules.tags.domain.entities.tag import Tag
from docir.platform.embedding.vector import Embedding


class DocumentRepository(ABC):
    """Stores document metadata and the relation graph derived from it."""

    @abstractmethod
    def next_number(self, prefix: str) -> int:
        """Return the next free integer for ``<prefix>-NNNN`` id allocation."""

    @abstractmethod
    def raise_next_number(self, prefix: str, minimum: int) -> None:
        """Raise the ``prefix`` counter to at least ``minimum`` (never lower it).

        The id counter lives in the derived index, so a rebuild from the files
        must restore it — otherwise the next allocation re-mints an id the files
        already use. Monotonic on purpose: deleting the highest-numbered
        document must not make its id available again.
        """

    @abstractmethod
    def save(self, document: Document) -> None:
        """Insert or update a document's metadata rows and relation edges."""

    @abstractmethod
    def get(self, doc_id: str) -> Document | None:
        """Return the document, or ``None`` if it is not indexed."""

    @abstractmethod
    def exists(self, doc_id: str) -> bool:
        """Whether a document with this id is indexed."""

    @abstractmethod
    def delete(self, doc_id: str) -> None:
        """Remove a document's metadata rows and its outgoing relation edges."""

    @abstractmethod
    def all(self) -> list[Document]:
        """Return every indexed document."""

    @abstractmethod
    def query(self, spec: DocumentFilter) -> list[Document]:
        """Return documents matching the structured filter."""

    @abstractmethod
    def outgoing(self, doc_id: str) -> list[str]:
        """Ids this document links to via ``related``."""

    @abstractmethod
    def incoming(self, doc_id: str, kinds: Collection[str] | None = None) -> list[str]:
        """Ids that link *to* this document, optionally only via ``kinds``.

        Unfiltered for delete integrity checks; filtered to the successor kinds
        by ``context`` expansion, which needs "what supersedes this?" — the one
        direction the graph answers and forward traversal cannot reach.
        """

    @abstractmethod
    def relations(self) -> list[Relation]:
        """Every directed edge in the relation graph (for Tier 1 checks)."""


class TagRepository(ABC):
    """Stores the tag registry (``docs/tags.yaml`` projected into the index)."""

    @abstractmethod
    def save(self, tag: Tag) -> None:
        """Insert or update a tag by key."""

    @abstractmethod
    def get(self, key: str) -> Tag | None:
        """Return the tag, or ``None`` if it is not registered."""

    @abstractmethod
    def page(self, *, limit: int, offset: int) -> list[Tag]:
        """A window over the registry, key-ordered.

        Separate from :meth:`all`, which the write paths need in full (a rename
        rewrites every referencing document). Listing is the path that grows
        with the vocabulary, so it is the one that pages.
        """

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Whether a tag with this key is registered."""

    @abstractmethod
    def all(self) -> list[Tag]:
        """Return every registered tag."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Remove a tag from the registry."""


class SearchIndex(ABC):
    """The FTS5 full-text projection of active (non-archived) documents."""

    @abstractmethod
    def index(self, document: Document) -> None:
        """Insert or update the full-text row for a document."""

    @abstractmethod
    def remove(self, doc_id: str) -> None:
        """Remove a document from the full-text index."""

    @abstractmethod
    def search(self, text: str, limit: int) -> list[SearchHit]:
        """Return BM25-ranked hits for a free-text query."""


class EmbeddingRepository(ABC):
    """Stores per-document embedding vectors and the dirty-flag queue."""

    @abstractmethod
    def mark_dirty(self, doc_id: str) -> None:
        """Flag a document as needing its vector recomputed."""

    @abstractmethod
    def clear_dirty(self, doc_id: str) -> None:
        """Clear the dirty flag once a vector has been recomputed."""

    @abstractmethod
    def dirty_ids(self, model_id: str) -> list[str]:
        """Ids needing a recompute: flagged dirty, or embedded by another model.

        Switching embedders (the default moved from the hashing embedder to a
        real model) leaves vectors from the old one in the index. They are a
        different width, so comparing them raises rather than degrading — the
        index has to notice and recompute rather than trust them.
        """

    @abstractmethod
    def set_vector(self, doc_id: str, embedding: Embedding, model_id: str) -> None:
        """Persist a computed vector, record which model made it, clear the flag."""

    @abstractmethod
    def get_vector(self, doc_id: str) -> Embedding | None:
        """Return the stored vector, or ``None`` if none is stored yet."""

    @abstractmethod
    def remove(self, doc_id: str) -> None:
        """Remove a document's vector and dirty flag entirely."""

    @abstractmethod
    def active_vectors(self, model_id: str) -> list[tuple[str, Embedding]]:
        """``(doc_id, vector)`` for active documents embedded by ``model_id``.

        Vectors from another model are omitted rather than compared: they live in
        a different space, and a different width would raise outright.
        """
