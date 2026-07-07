"""The document use cases: the single write path and the read paths.

All writes go through here — never by editing markdown directly — which is
what guarantees frontmatter/schema consistency. Each method opens a unit of
work, mutates the file (source of truth) and the derived index atomically, and
schedules the deferred embedding recompute off the critical path.
"""

from __future__ import annotations

from collections.abc import Callable

from docir.application.dto import (
    AddDocumentRequest,
    ContextRequest,
    DocumentView,
    QueryRequest,
    SearchRequest,
    UpdateDocumentRequest,
)
from docir.domain.entities.document import Document
from docir.domain.errors import (
    DanglingReferenceError,
    DocumentNotFoundError,
    StaleWriteError,
    ValidationError,
)
from docir.domain.ports.clock import Clock
from docir.domain.ports.embedder import Embedder
from docir.domain.ports.files import DocumentFileStore
from docir.domain.ports.scheduler import EmbeddingScheduler
from docir.domain.ports.unit_of_work import UnitOfWork
from docir.domain.schema import Schema
from docir.domain.services.id_generator import IdGenerator
from docir.domain.services.markdown_sections import append_section, replace_section
from docir.domain.services.scoring import HybridScorer
from docir.domain.services.validation import Tier0Validator
from docir.domain.value_objects.queries import DocumentFilter

UnitOfWorkFactory = Callable[[], UnitOfWork]

# How many FTS candidates to pull before hybrid fusion in ``docs context``.
_CONTEXT_CANDIDATES = 25


class DocumentService:
    """Use cases for the document aggregate."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        file_store: DocumentFileStore,
        scheduler: EmbeddingScheduler,
        embedder: Embedder,
        clock: Clock,
        schema: Schema,
        scorer: HybridScorer | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._file_store = file_store
        self._scheduler = scheduler
        self._embedder = embedder
        self._clock = clock
        self._schema = schema
        self._validator = Tier0Validator(schema)
        self._scorer = scorer or HybridScorer()

    # -- write path ---------------------------------------------------------

    def add(self, request: AddDocumentRequest) -> DocumentView:
        """Create a new document (``docs add``)."""
        status = request.status or self._schema.default_status_for(request.type)
        self._validator.validate_status(request.type, status)
        today = self._clock.today()

        with self._uow_factory() as uow:
            self._validator.validate_tags(request.tags, [tag.key for tag in uow.tags.all()])
            self._validator.validate_related(
                request.related, [doc.id for doc in uow.documents.all()]
            )
            doc_id = IdGenerator(self._schema, uow.documents).next_id(request.type)
            document = Document(
                id=str(doc_id),
                title=request.title,
                description=request.description,
                type=request.type,
                status=status,
                created=today,
                updated=today,
                tags=tuple(request.tags),
                related=tuple(request.related),
                archived=False,
                body=request.body,
            )
            self._validator.validate_required_fields(document)
            path = self._file_store.write(document)
            document = document.with_updates(path=path)
            uow.documents.save(document)
            uow.search.index(document)
            uow.embeddings.mark_dirty(document.id)
            uow.commit()

        self._schedule_embedding(document.id, wait=request.wait_embeddings)
        return DocumentView.from_document(document)

    def update(self, request: UpdateDocumentRequest) -> DocumentView:
        """Patch metadata and/or edit the body (``docs update``)."""
        with self._uow_factory() as uow:
            indexed = uow.documents.get(request.doc_id)
            if indexed is None:
                raise DocumentNotFoundError(f"no document with id {request.doc_id!r}")

            base = self._read_current(indexed)
            stale = indexed.content_hash() != base.content_hash()

            changes: dict[str, object] = {}
            content_changed = self._apply_metadata(request, base, changes, uow)
            content_changed |= self._apply_body(request, base, changes, stale)

            if not changes:
                return DocumentView.from_document(base)

            changes["updated"] = self._clock.today()
            updated = base.with_updates(**changes)
            self._validator.validate_required_fields(updated)
            path = self._file_store.write(updated)
            updated = updated.with_updates(path=path)

            uow.documents.save(updated)
            uow.search.index(updated)
            if content_changed:
                uow.embeddings.mark_dirty(updated.id)
            uow.commit()

        if content_changed:
            self._schedule_embedding(updated.id, wait=request.wait_embeddings)
        return DocumentView.from_document(updated)

    def archive(self, doc_id: str) -> DocumentView:
        """Soft-remove a document from active search (``docs archive``)."""
        with self._uow_factory() as uow:
            document = self._require(uow, doc_id)
            if document.archived:
                return DocumentView.from_document(document)
            updated = document.with_updates(archived=True, updated=self._clock.today())
            self._file_store.write(updated)
            uow.documents.save(updated)
            uow.search.remove(doc_id)
            uow.embeddings.remove(doc_id)
            uow.commit()
        return DocumentView.from_document(updated)

    def unarchive(self, doc_id: str) -> DocumentView:
        """Restore a document to active search (``docs unarchive``)."""
        with self._uow_factory() as uow:
            document = self._require(uow, doc_id)
            if not document.archived:
                return DocumentView.from_document(document)
            updated = document.with_updates(archived=False, updated=self._clock.today())
            self._file_store.write(updated)
            uow.documents.save(updated)
            uow.search.index(updated)
            uow.embeddings.mark_dirty(doc_id)
            uow.commit()
        self._schedule_embedding(doc_id, wait=False)
        return DocumentView.from_document(updated)

    def delete(self, doc_id: str, *, force: bool = False) -> None:
        """Hard-delete the file and all index rows (``docs delete``)."""
        with self._uow_factory() as uow:
            document = self._require(uow, doc_id)
            incoming = uow.documents.incoming(doc_id)
            if incoming and not force:
                joined = ", ".join(sorted(incoming))
                raise DanglingReferenceError(
                    f"cannot delete {doc_id!r}: still referenced by {joined} "
                    f"(use --force to override)"
                )
            if document.path:
                self._file_store.delete(document.path)
            uow.documents.delete(doc_id)
            uow.search.remove(doc_id)
            uow.embeddings.remove(doc_id)
            uow.commit()

    # -- read path ----------------------------------------------------------

    def get(self, doc_id: str) -> DocumentView:
        """Return one document in full, regardless of status (``docs get``)."""
        with self._uow_factory() as uow:
            document = self._require(uow, doc_id)
            return DocumentView.from_document(document)

    def query(self, request: QueryRequest) -> list[DocumentView]:
        """Structured metadata filtering (``docs query``)."""
        spec = DocumentFilter(
            types=request.types,
            statuses=request.statuses,
            tags=request.tags,
            include_archived=request.include_archived,
            inactive_statuses=tuple(sorted(self._schema.inactive_statuses())),
            include_inactive=request.include_inactive,
        )
        with self._uow_factory() as uow:
            documents = uow.documents.query(spec)
        return [DocumentView.from_document(doc) for doc in documents[: request.limit]]

    def search(self, request: SearchRequest) -> list[DocumentView]:
        """Full-text search over active documents (``docs search``)."""
        inactive = self._schema.inactive_statuses()
        with self._uow_factory() as uow:
            hits = uow.search.search(request.text, limit=request.limit * 2)
            views: list[DocumentView] = []
            for hit in hits:
                document = uow.documents.get(hit.doc_id)
                if document is None:
                    continue
                if not request.include_inactive and document.status in inactive:
                    continue
                views.append(DocumentView.from_document(document, score=-hit.bm25))
                if len(views) >= request.limit:
                    break
        return views

    def context(self, request: ContextRequest) -> list[DocumentView]:
        """Ranked, minimal relevant document set (``docs context``)."""
        query_vector = self._embedder.embed(request.task)
        inactive = self._schema.inactive_statuses()

        with self._uow_factory() as uow:
            hits = uow.search.search(request.task, limit=_CONTEXT_CANDIDATES)
            semantic = self._scorer.semantic_ranking(query_vector, uow.embeddings.active_vectors())
            fused = self._scorer.fuse(hits, semantic)

            selected: dict[str, DocumentView] = {}
            for fscore in fused:
                if len(selected) >= request.limit:
                    break
                document = uow.documents.get(fscore.doc_id)
                if document is None or document.archived:
                    continue
                if not request.include_inactive and document.status in inactive:
                    continue
                selected[document.id] = DocumentView.from_document(document, score=fscore.score)

            self._augment_with_related(uow, selected)

        return list(selected.values())

    # -- helpers ------------------------------------------------------------

    def _augment_with_related(self, uow: UnitOfWork, selected: dict[str, DocumentView]) -> None:
        """Pull each selected document's ``related`` neighbours one hop out."""
        seeds = list(selected)
        for seed in seeds:
            for neighbour_id in uow.documents.outgoing(seed):
                if neighbour_id in selected:
                    continue
                neighbour = uow.documents.get(neighbour_id)
                if neighbour is None or neighbour.archived:
                    continue
                selected[neighbour_id] = DocumentView.from_document(neighbour, via_graph=True)

    def _apply_metadata(
        self,
        request: UpdateDocumentRequest,
        base: Document,
        changes: dict[str, object],
        uow: UnitOfWork,
    ) -> bool:
        """Stage metadata changes; return whether embedding-relevant text moved."""
        content_changed = False
        if request.set_title is not None:
            changes["title"] = request.set_title
            content_changed = True
        if request.set_description is not None:
            changes["description"] = request.set_description
            content_changed = True
        if request.status is not None and request.status != base.status:
            if request.allow_transition_override:
                self._validator.validate_status(base.type, request.status)
            else:
                self._validator.validate_transition(base.type, base.status, request.status)
            changes["status"] = request.status
        if request.set_tags is not None:
            self._validator.validate_tags(request.set_tags, [tag.key for tag in uow.tags.all()])
            changes["tags"] = tuple(request.set_tags)
        if request.set_related is not None:
            self._validator.validate_related(
                request.set_related, [doc.id for doc in uow.documents.all()]
            )
            changes["related"] = tuple(request.set_related)
        return content_changed

    def _apply_body(
        self,
        request: UpdateDocumentRequest,
        base: Document,
        changes: dict[str, object],
        stale: bool,
    ) -> bool:
        """Stage a body edit (at most one mode); return whether the body moved."""
        modes = [
            request.append_section,
            request.replace_section,
            request.replace_body,
        ]
        if sum(mode is not None for mode in modes) > 1:
            raise ValidationError("only one body edit mode may be used per call")

        if request.append_section is not None:
            heading, body = request.append_section
            changes["body"] = append_section(base.body, heading, body)
            return True
        if request.replace_section is not None:
            heading, body = request.replace_section
            changes["body"] = replace_section(base.body, heading, body)
            return True
        if request.replace_body is not None:
            if not request.force:
                raise ValidationError(
                    "--replace-body requires --force (it overwrites the whole body)"
                )
            if stale:
                raise StaleWriteError(
                    f"{base.id!r} changed on disk since it was indexed; "
                    f"refetch with `docir get {base.id}` before replacing the body"
                )
            changes["body"] = request.replace_body
            return True
        return False

    def _read_current(self, indexed: Document) -> Document:
        """The current on-disk document (source of truth) for an update base."""
        if indexed.path is None:
            return indexed
        return self._file_store.read(indexed.path)

    def _require(self, uow: UnitOfWork, doc_id: str) -> Document:
        document = uow.documents.get(doc_id)
        if document is None:
            raise DocumentNotFoundError(f"no document with id {doc_id!r}")
        return document

    def _schedule_embedding(self, doc_id: str, *, wait: bool) -> None:
        self._scheduler.schedule(doc_id)
        if wait:
            self._scheduler.flush()
