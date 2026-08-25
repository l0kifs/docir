"""Repository ports — the persistence contracts the use cases depend on.

Each is an abstract interface. Concrete implementations (SQLAlchemy-backed,
or in-memory fakes for tests) live in the infrastructure layer. Splitting the
index into focused repositories keeps each concern (metadata + graph, tags,
full-text, embeddings) independently substitutable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Collection, Sequence
from dataclasses import dataclass

from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.entities.relation import Relation
from docir.modules.documents.domain.value_objects.queries import DocumentFilter
from docir.modules.indexing.domain.results import SearchHit
from docir.modules.tags.domain.entities.tag import Tag
from docir.platform.embedding.vector import Embedding


@dataclass(frozen=True, slots=True)
class StoredChunk:
    """One section vector on its way into (or out of) storage."""

    ordinal: int
    heading: str
    vector: Embedding


class SchemaBaselineRepository(ABC):
    """Stores the resolved schema the index was last rebuilt against.

    Deliberately untyped in the domain's terms — a JSON-safe mapping in, the
    same mapping out. The shape is the rendering the documents module already
    publishes (`docir schema show`), and giving this port a schema type would
    add a `platform -> modules.domain` edge to a baseline that is only allowed
    to shrink (adr-d3e3616400bf), for no gain: nothing here reads a field.
    """

    @abstractmethod
    def get(self) -> dict[str, object] | None:
        """The recorded baseline, or ``None`` if the store has never had one.

        ``None`` means *unknown*, not *unchanged*: a store predating the table,
        or one that has not been reindexed since, has nothing to compare
        against, and inventing an empty baseline would report every type in the
        schema as newly added.
        """

    @abstractmethod
    def set(self, payload: dict[str, object]) -> None:
        """Replace the baseline with ``payload``."""


class IndexBuildRepository(ABC):
    """Stores the docir version that last rebuilt the index."""

    @abstractmethod
    def get(self) -> str | None:
        """The recorded version, or ``None`` if the store has never had one.

        ``None`` means *unknown*, not *current* — the same rule the schema
        baseline follows. A store predating the table, or one not reindexed
        since, has nothing to compare against, and reading absence as "built by
        the running version" would hide exactly the case this exists for.
        """

    @abstractmethod
    def set(self, version: str) -> None:
        """Record ``version`` as the build that produced the current index."""


class MentionRepository(ABC):
    """The derived mention graph: which document ids each body names.

    Separate from :class:`DocumentRepository` because it answers a different
    question about a different graph. ``related:`` is authored and typed, and
    the checks that police it — dangling, cycle, layering — plus the guard that
    blocks a delete all read it. Mentions are inferred from prose, so none of
    those may see them: a cycle nobody wrote is noise, and refusing a delete
    because a paragraph quotes an id would make the corpus unmaintainable.

    Every method resolves against the indexed documents, so a body naming an id
    that does not exist is stored and simply not returned. Absent means
    *unresolved*, and it starts resolving the moment the target is written.
    """

    @abstractmethod
    def replace(self, source: str, targets: Sequence[str]) -> None:
        """Set ``source``'s outgoing mentions, discarding what was there."""

    @abstractmethod
    def outgoing(self, source: str) -> list[str]:
        """Ids ``source`` names that exist, sorted."""

    @abstractmethod
    def incoming(self, target: str) -> list[str]:
        """Ids of the documents that name ``target``, sorted."""

    @abstractmethod
    def unresolved(self) -> list[tuple[str, str]]:
        """Every ``(source, target)`` pair whose target is not indexed.

        The complement of :meth:`all_resolved`, and read by exactly one caller:
        the Tier 2 advisory report. It is deliberately **not** a Tier 1 finding
        — measured on this project's own corpus, all 47 unresolved mentions were
        documentation examples (`adr-0007` and friends, in the documents that
        explain the id format), so a warning would fire only on correct usage.
        """

    @abstractmethod
    def all_resolved(self) -> list[tuple[str, str]]:
        """Every ``(source, target)`` pair where both documents are indexed.

        The bulk read `docir check` needs: asking per document would be one
        query per document, and the orphan check reads the whole graph anyway.
        """


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
    def count(self) -> int:
        """How many documents the index holds.

        Its own query rather than ``len(all())``: the callers that want a size
        (``docir doctor``) do not want the corpus hydrated into entities to
        learn it, and on a large store that is the whole cost of the command.
        """

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
    def usage_counts(self, keys: Collection[str]) -> dict[str, int]:
        """How many indexed documents carry each of ``keys``.

        Keys nobody uses are absent from the mapping rather than mapped to 0 —
        the caller supplies the zero, so a missing row cannot be confused with a
        tag that was not asked about.

        Counts every indexed document, archived included, because that is what
        ``tag rm`` blocks on: a tag reported as unused that then refuses to be
        removed would be worse than no count at all.
        """

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


class ChunkEmbeddingRepository(ABC):
    """Stores per-section vectors — one row per ``(doc_id, ordinal)``.

    Separate from :class:`EmbeddingRepository` because the two answer different
    questions. The document vector says what a document is *about*; a chunk
    vector says what one section of it *says*, and only the chunks put the tail
    of a long document into the semantic index at all (adr-927aa43d9635).

    There is no dirty flag here: a chunk set is derived from a body, so it is
    invalidated by exactly the thing that invalidates the document vector.
    :meth:`EmbeddingRepository.dirty_ids` remains the single queue, and chunks
    are rewritten wholesale in the same transaction.
    """

    @abstractmethod
    def replace(self, doc_id: str, chunks: Sequence[StoredChunk], model_id: str) -> None:
        """Replace every chunk for a document with ``chunks``, atomically.

        Wholesale rather than incremental: an edit renumbers the sections after
        it, so a diff would have to rewrite most of them anyway, and a partial
        failure would leave chunks describing two different bodies.
        """

    @abstractmethod
    def remove(self, doc_id: str) -> None:
        """Drop every chunk for a document."""

    @abstractmethod
    def active_vectors(self, model_id: str) -> list[tuple[str, str, Embedding]]:
        """``(doc_id, heading, vector)`` for every chunk of an active document.

        Returns one entry per *chunk*, so a document appears many times; pooling
        to a per-document score is the caller's job (adr-927aa43d9635 keeps that in the
        scorer, where the ranking rule lives).

        The heading rides along because the ranking is where the winning chunk
        is known, and it is what ``docir get --section`` needs next
        (issue-afd25273ff1f). A chunk with no heading — a preamble, or the
        continuation of an over-long section — carries the empty string.
        """

    @abstractmethod
    def headings(self, doc_id: str) -> list[str]:
        """The stored section headings for a document, in body order."""
