"""The document use cases: the single write path and the read paths.

All writes go through here — never by editing markdown directly — which is
what guarantees frontmatter/schema consistency. Each method opens a unit of
work, mutates the file (source of truth) and the derived index atomically, and
schedules the deferred embedding recompute off the critical path.
"""

from __future__ import annotations

from collections.abc import Callable

from docir.modules.documents.application.dto import (
    AddDocumentRequest,
    ContextRequest,
    DocumentSummary,
    DocumentView,
    QueryRequest,
    SearchRequest,
    UpdateDocumentRequest,
)
from docir.modules.documents.application.services.id_generator import IdGenerator
from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.schema import Schema
from docir.modules.documents.domain.services.markdown_sections import (
    append_section,
    replace_section,
)
from docir.modules.documents.domain.services.validation import Tier0Validator
from docir.modules.documents.domain.value_objects.queries import DocumentFilter
from docir.modules.documents.domain.value_objects.relations import RelatedRef
from docir.modules.indexing.api import EmbeddingScheduler, FusedScore, HybridScorer
from docir.platform.clock import Clock
from docir.platform.embedding import Embedder
from docir.platform.errors import (
    DanglingReferenceError,
    DocumentNotFoundError,
    StaleWriteError,
    ValidationError,
)
from docir.platform.filesystem.ports import DocumentFileStore
from docir.platform.persistence.unit_of_work import UnitOfWork

UnitOfWorkFactory = Callable[[], UnitOfWork]

# How many FTS candidates to pull before hybrid fusion in ``docs context``.
_CONTEXT_CANDIDATES = 25

#: Relation kinds whose *incoming* direction answers "is this still current?".
#: Followed backwards during ``context`` expansion so a document reached by the
#: ranker carries its own replacement with it. Kept deliberately separate from
#: the layering check's kind set (`graph_checks._DEPENDENCY_KINDS`), which held
#: these same two kinds for an unrelated reason until it was inverted into a
#: dependency allowlist — they have since diverged completely.
_SUCCESSOR_KINDS = frozenset({"supersedes", "contradicts"})


def _parse_refs(tokens: tuple[str, ...]) -> tuple[RelatedRef, ...]:
    """Parse ``<id>`` / ``<id>:<kind>`` CLI tokens into typed edges."""
    return tuple(RelatedRef.parse(token) for token in tokens if token.strip())


def _require_positive_limit(limit: int) -> None:
    """Reject a non-positive result limit before it reaches a slice/SQL bound.

    A negative ``limit`` reaches ``documents[:limit]`` (drops the tail) or a
    SQLite ``LIMIT -1`` (unbounded); zero is silently empty. All three read
    paths must agree, so a non-positive limit is a Tier 0 validation error.
    """
    if limit <= 0:
        raise ValidationError(f"limit must be a positive integer, got {limit}")


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
        refs = _parse_refs(request.related)

        with self._uow_factory() as uow:
            self._validator.validate_tags(request.tags, [tag.key for tag in uow.tags.all()])
            id_to_type = {doc.id: doc.type for doc in uow.documents.all()}
            self._validator.validate_related([ref.target for ref in refs], id_to_type)
            self._validator.validate_relation_kinds(request.type, refs, id_to_type)
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
                related=refs,
                archived=False,
                body=request.body,
                owner=request.owner or "",
            )
            self._validator.validate_required_fields(document)
            path = self._file_store.write(document, create=True)
            document = document.with_updates(path=path)
            uow.documents.save(document)
            uow.search.index(document)
            uow.embeddings.mark_dirty(document.id)
            uow.commit()

        self._schedule_embedding(document.id, wait=request.wait_embeddings)
        return DocumentView.from_document(document, stale=self._is_stale(document))

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
                return DocumentView.from_document(base, stale=self._is_stale(base))

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
        return DocumentView.from_document(updated, stale=self._is_stale(updated))

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
        return DocumentView.from_document(updated, stale=self._is_stale(updated))

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
        return DocumentView.from_document(updated, stale=self._is_stale(updated))

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
            return DocumentView.from_document(document, stale=self._is_stale(document))

    def query(self, request: QueryRequest) -> list[DocumentSummary]:
        """Structured metadata filtering (``docs query``) — skeleton results."""
        _require_positive_limit(request.limit)
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
        return [self._summary(doc) for doc in documents[: request.limit]]

    def search(self, request: SearchRequest) -> list[DocumentSummary]:
        """Full-text search over active documents (``docs search``) — skeletons."""
        _require_positive_limit(request.limit)
        inactive = self._schema.inactive_statuses()
        with self._uow_factory() as uow:
            hits = uow.search.search(request.text, limit=request.limit * 2)
            views: list[DocumentSummary] = []
            for hit in hits:
                document = uow.documents.get(hit.doc_id)
                if document is None:
                    continue
                if not request.include_inactive and document.status in inactive:
                    continue
                views.append(self._summary(document, score=-hit.bm25))
                if len(views) >= request.limit:
                    break
        return views

    def context(self, request: ContextRequest) -> list[DocumentSummary]:
        """Ranked, minimal relevant document set (``docs context``) — skeletons.

        ``limit`` is a hard ceiling on the response. Graph expansion runs inside
        it, not on top of it: ``expand`` slots are held back for neighbours, and
        any the graph does not fill are given back to the ranked hits, so the
        result is always ``min(limit, what exists)``.
        """
        _require_positive_limit(request.limit)
        # Always leave room for at least one ranked hit — a result made purely of
        # neighbours would have nothing to be a neighbour of.
        expand = min(max(request.expand, 0), request.limit - 1)
        query_vector = self._embedder.embed(request.task)

        with self._uow_factory() as uow:
            hits = uow.search.search(request.task, limit=_CONTEXT_CANDIDATES)
            semantic = self._scorer.semantic_ranking(
                query_vector, uow.embeddings.active_vectors(self._embedder.model_id)
            )
            fused = self._scorer.fuse(hits, semantic)

            # Rank order, visible only, capped at what could ever be returned.
            ranked = self._visible_ranked(uow, fused, request, limit=request.limit)

            seed_budget = request.limit - expand
            selected: dict[str, DocumentSummary] = {
                document.id: self._summary(document, score=score)
                for document, score in ranked[:seed_budget]
            }
            if expand:
                self._augment_with_related(
                    uow, selected, budget=expand, include_inactive=request.include_inactive
                )
            # Give back neighbour slots the graph did not use.
            for document, score in ranked[seed_budget:]:
                if len(selected) >= request.limit:
                    break
                selected.setdefault(document.id, self._summary(document, score=score))

        return list(selected.values())

    def _visible_ranked(
        self,
        uow: UnitOfWork,
        fused: list[FusedScore],
        request: ContextRequest,
        *,
        limit: int,
    ) -> list[tuple[Document, float]]:
        """Resolve fused scores to visible documents, best first, at most ``limit``."""
        resolved: list[tuple[Document, float]] = []
        for fscore in fused:
            if len(resolved) >= limit:
                break
            document = uow.documents.get(fscore.doc_id)
            if document is None:
                continue
            if not self._is_visible(document, include_inactive=request.include_inactive):
                continue
            resolved.append((document, fscore.score))
        return resolved

    # -- helpers ------------------------------------------------------------

    def _summary(
        self,
        document: Document,
        *,
        score: float | None = None,
        via_graph: bool = False,
    ) -> DocumentSummary:
        return DocumentSummary.from_document(
            document, stale=self._is_stale(document), score=score, via_graph=via_graph
        )

    def _is_stale(self, document: Document) -> bool:
        """Whether the document is past its type's review cadence (staleness)."""
        if document.type not in self._schema.types:
            return False
        cadence = self._schema.review_days_for(document.type)
        if cadence <= 0:
            return False
        return (self._clock.today() - document.stale_reference_date()).days > cadence

    def _augment_with_related(
        self,
        uow: UnitOfWork,
        selected: dict[str, DocumentSummary],
        *,
        budget: int,
        include_inactive: bool,
    ) -> None:
        """Pull up to ``budget`` of the selected documents' neighbours one hop out.

        Breadth-first across the seeds rather than depth-first through one seed's
        edge list, so a densely linked top hit cannot spend the whole budget
        before the other seeds contribute anything.

        Successors come first in each seed's edge list: "what supersedes this?"
        outranks an ordinary link when the budget is tight, because it is the
        one neighbour that can invalidate the seed the agent is about to act on.
        """
        edges = {seed: self._neighbours_of(uow, seed) for seed in selected}
        added = 0
        for depth in range(max((len(targets) for targets in edges.values()), default=0)):
            for targets in edges.values():
                if added >= budget:
                    return
                if depth >= len(targets):
                    continue
                neighbour_id = targets[depth]
                if neighbour_id in selected:
                    continue
                neighbour = uow.documents.get(neighbour_id)
                if neighbour is None:
                    continue
                if not self._is_visible(neighbour, include_inactive=include_inactive):
                    continue
                selected[neighbour_id] = self._summary(neighbour, via_graph=True)
                added += 1

    @staticmethod
    def _neighbours_of(uow: UnitOfWork, seed: str) -> list[str]:
        """One-hop neighbours of ``seed``: successors first, then outgoing links.

        Expansion used to follow outgoing edges only, which left the graph unable
        to answer the question it exists for — *is this decision still current?*
        A ``supersedes`` edge points from the new document to the old one, so the
        replacement sits one hop away *backwards* and was never reachable from
        the document it replaces.
        """
        successors = uow.documents.incoming(seed, kinds=_SUCCESSOR_KINDS)
        outgoing = uow.documents.outgoing(seed)
        return [*successors, *(t for t in outgoing if t not in set(successors))]

    def _is_visible(self, document: Document, *, include_inactive: bool) -> bool:
        """The single visibility predicate every ``context`` path must apply.

        Ranked hits and graph-reached neighbours used to filter differently: the
        fusion loop checked archived *and* inactive status, expansion checked
        only archived. A ``resolved`` issue the caller had excluded therefore
        came back through a neighbour edge, and nothing in the response said
        which results had honoured the filter. One predicate, both callers.
        """
        if document.archived:
            return False
        return include_inactive or document.status not in self._schema.inactive_statuses()

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
            refs = _parse_refs(request.set_related)
            id_to_type = {doc.id: doc.type for doc in uow.documents.all()}
            self._validator.validate_related([ref.target for ref in refs], id_to_type)
            self._validator.validate_relation_kinds(base.type, refs, id_to_type)
            changes["related"] = refs
        if request.set_owner is not None:
            changes["owner"] = request.set_owner
        if request.mark_verified:
            changes["verified"] = self._clock.today()
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
