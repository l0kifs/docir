"""The document use cases: the single write path and the read paths.

All writes go through here — never by editing markdown directly — which is
what guarantees frontmatter/schema consistency. Each method opens a unit of
work, mutates the file (source of truth) and the derived index atomically, and
schedules the deferred embedding recompute off the critical path.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

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
from docir.modules.documents.domain.schema import SEQUENTIAL_ID_STYLE, Schema
from docir.modules.documents.domain.services.code_globs import governs_any
from docir.modules.documents.domain.services.markdown_sections import (
    append_section,
    extract_section,
    replace_section,
)
from docir.modules.documents.domain.services.validation import Tier0Validator
from docir.modules.documents.domain.value_objects.identifiers import DocId
from docir.modules.documents.domain.value_objects.queries import DocumentFilter
from docir.modules.documents.domain.value_objects.relations import RelatedRef
from docir.modules.indexing.api import (
    EmbeddingScheduler,
    FusedScore,
    HybridScorer,
    VectorCandidate,
)
from docir.platform.clock import Clock
from docir.platform.embedding import Embedder
from docir.platform.errors import (
    DanglingReferenceError,
    DocumentNotFoundError,
    DuplicateDocumentIdError,
    InvalidStatusError,
    StaleWriteError,
    ValidationError,
)
from docir.platform.filesystem.ports import CodeMatcher, DocumentFileStore
from docir.platform.persistence.unit_of_work import UnitOfWork

UnitOfWorkFactory = Callable[[], UnitOfWork]

# How many FTS candidates to pull before hybrid fusion in ``docir context``.
_CONTEXT_CANDIDATES = 25

#: How many extra FTS candidates to request per result wanted, before filtering
#: out closed documents. Two is a starting point, not a bound: the pool doubles
#: until the limit is met or the index runs out, so a corpus where most top hits
#: are closed still fills the response.
_SEARCH_OVERFETCH = 2

#: Which kinds answer "is this still current?" is now a schema property
#: (``RelationKindSchema.successor``), read per call from
#: ``Schema.successor_relation_kinds()``. It was a frozenset of two names here,
#: which meant a custom kind with exactly this shape — `replaced_by`, `revokes` —
#: could not be followed backwards at all, and nothing said so.


def _parse_refs(tokens: tuple[str, ...]) -> tuple[RelatedRef, ...]:
    """Parse ``<id>`` / ``<id>:<kind>`` CLI tokens into typed edges."""
    return tuple(RelatedRef.parse(token) for token in tokens if token.strip())


#: Rows per scan when `--stale` or `--code` forces post-filtering. Large enough
#: that a normal corpus resolves in one round trip, small enough that a page of
#: a huge one does not pull it all into memory.
_SCAN_PAGE = 500


def _require_non_negative_offset(offset: int) -> None:
    """Reject a negative offset before it reaches SQL, where it is ignored."""
    if offset < 0:
        raise ValidationError(f"offset must be zero or greater, got {offset}")


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
        code_matcher: CodeMatcher | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._file_store = file_store
        self._scheduler = scheduler
        self._embedder = embedder
        self._clock = clock
        self._schema = schema
        self._validator = Tier0Validator(schema)
        self._scorer = scorer or HybridScorer()
        # Optional for the same reason `check` treats it as optional: a global
        # store has no repository above it, so there is no tree to fingerprint.
        # Absent means the verification records a date and no evidence.
        self._code_matcher = code_matcher

    # -- write path ---------------------------------------------------------

    def add(self, request: AddDocumentRequest) -> DocumentView:
        """Create a new document (``docir add``)."""
        status = request.status or self._schema.default_status_for(request.type)
        self._validator.validate_status(request.type, status)
        today = self._clock.today()
        refs = _parse_refs(request.related)

        with self._uow_factory() as uow:
            self._validator.validate_tags(request.tags, [tag.key for tag in uow.tags.all()])
            id_to_type = {doc.id: doc.type for doc in uow.documents.all()}
            # `request.doc_id` only on the adoption path: an allocated id is not
            # known until below, and cannot be referenced by a caller who does
            # not know it yet.
            self._validator.validate_related(
                [ref.target for ref in refs], id_to_type, source_id=request.doc_id
            )
            self._validator.validate_relation_kinds(request.type, refs, id_to_type)
            self._validator.validate_code(request.code)
            doc_id = self._allocate_id(request, uow)
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
                code=tuple(request.code),
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
        """Patch metadata and/or edit the body (``docir update``).

        Every edit is applied to ``base`` — the document as it is **on disk**,
        not as the index remembers it — because the files are the source of
        truth. ``disk_diverged`` records that the two disagree: the file was
        hand-edited or merged since it was last indexed. Note this is a
        divergence check, not optimistic concurrency control; no caller supplies
        a version token, so it cannot detect a competing writer.

        **Only ``--replace-body`` is blocked when the disk has diverged, and
        that asymmetry is deliberate.** Every other mode composes with whatever
        is on disk: a metadata patch or a section edit builds on ``base``, so an
        out-of-band edit survives it untouched. ``--replace-body`` is the one
        mode that throws ``base.body`` away, so it is the one mode where a
        divergence means data loss. Extending the guard to the others would
        reject writes that were never going to lose anything — failing
        ``--set-title`` because somebody fixed a typo in the file by hand.
        """
        with self._uow_factory() as uow:
            indexed = uow.documents.get(request.doc_id)
            if indexed is None:
                raise DocumentNotFoundError(f"no document with id {request.doc_id!r}")

            base = self._read_current(indexed)
            disk_diverged = indexed.content_hash() != base.content_hash()

            forced = self._forced_transition(request, base)
            changes: dict[str, object] = {}
            content_changed = self._apply_metadata(request, base, changes, uow)
            content_changed |= self._apply_body(request, base, changes, disk_diverged)

            if not changes:
                return DocumentView.from_document(base, stale=self._is_stale(base))

            changes["updated"] = self._clock.today()
            updated = base.with_updates(**changes)
            self._validator.validate_required_fields(updated)
            # A retype moves the file: the directory names the type, so leaving
            # it where it was makes the layout disagree with the frontmatter on
            # every document a corpus-wide rename touches.
            if "type" in changes and base.path:
                path = self._file_store.relocate(updated, from_path=base.path)
            else:
                path = self._file_store.write(updated)
            updated = updated.with_updates(path=path)

            uow.documents.save(updated)
            uow.search.index(updated)
            if content_changed:
                uow.embeddings.mark_dirty(updated.id)
            uow.commit()

        if content_changed:
            self._schedule_embedding(updated.id, wait=request.wait_embeddings)
        return DocumentView.from_document(
            updated, stale=self._is_stale(updated), forced_transition=forced
        )

    def archive(self, doc_id: str) -> DocumentView:
        """Soft-remove a document from active search (``docir archive``)."""
        with self._uow_factory() as uow:
            document = self._require(uow, doc_id)
            if document.archived:
                # Staleness must be computed on the no-op path too: `get` said
                # `stale: true` for a document this returned as `stale: false`,
                # and the field exists to be trusted.
                return DocumentView.from_document(document, stale=self._is_stale(document))
            updated = document.with_updates(archived=True, updated=self._clock.today())
            self._file_store.write(updated)
            uow.documents.save(updated)
            uow.search.remove(doc_id)
            uow.embeddings.remove(doc_id)
            uow.commit()
        return DocumentView.from_document(updated, stale=self._is_stale(updated))

    def unarchive(self, doc_id: str) -> DocumentView:
        """Restore a document to active search (``docir unarchive``)."""
        with self._uow_factory() as uow:
            document = self._require(uow, doc_id)
            if not document.archived:
                return DocumentView.from_document(document, stale=self._is_stale(document))
            updated = document.with_updates(archived=False, updated=self._clock.today())
            self._file_store.write(updated)
            uow.documents.save(updated)
            uow.search.index(updated)
            uow.embeddings.mark_dirty(doc_id)
            uow.commit()
        self._schedule_embedding(doc_id, wait=False)
        return DocumentView.from_document(updated, stale=self._is_stale(updated))

    def delete(self, doc_id: str, *, force: bool = False) -> tuple[str, ...]:
        """Hard-delete the file and all index rows (``docir delete``).

        A forced delete **strips the edge from every document that referenced
        it**, in the same transaction, and returns their ids. Without that the
        delete left the corpus in a state it could detect and not exit: the
        referencing file kept `related: [<deleted id>]`, `docir check` reported
        it forever, and because Tier 0 only validates the edges supplied in the
        *current* call, any later `update` re-persisted the dead edge to the
        canonical file. The compensating write is the same one `tag rm --force`
        already performs for tags.

        `updated` is deliberately not advanced on the referencing documents —
        the same rule `check --fix` and the tag paths follow (issue-9ed4905e0db8
        moved the tag side here). Staleness records when somebody last vouched
        for the content, and having a link removed from underneath you is not
        that. A fourth mechanical rewrite does not set `updated` either.
        """
        with self._uow_factory() as uow:
            document = self._require(uow, doc_id)
            incoming = uow.documents.incoming(doc_id)
            if incoming and not force:
                joined = ", ".join(sorted(incoming))
                raise DanglingReferenceError(
                    f"cannot delete {doc_id!r}: still referenced by {joined} "
                    f"(use --force to override)"
                )
            for referrer_id in incoming:
                referrer = uow.documents.get(referrer_id)
                if referrer is None:
                    continue
                kept = tuple(ref for ref in referrer.related if ref.target != doc_id)
                stripped = referrer.with_updates(related=kept)
                self._file_store.write(stripped)
                uow.documents.save(stripped)
                uow.search.index(stripped)
            if document.path:
                self._file_store.delete(document.path)
            uow.documents.delete(doc_id)
            uow.search.remove(doc_id)
            uow.embeddings.remove(doc_id)
            uow.commit()
        return tuple(sorted(incoming))

    # -- read path ----------------------------------------------------------

    def get(self, doc_id: str, section: str | None = None) -> DocumentView:
        """Return one document in full, regardless of status (``docir get``).

        With ``section``, ``body`` carries only that heading and the text under
        it, and ``section`` names what was returned. Same span
        ``--replace-section`` would overwrite, so read and write agree about
        what a section is.

        This is the paired read for chunked retrieval: `context` can now rank a
        document on one of its sections, and this is how that section gets read
        without paying for a body that is frequently ten times its size. A
        heading that does not exist raises, listing the ones that do — an agent
        should not have to fetch the whole body to discover the names.
        """
        with self._uow_factory() as uow:
            document = self._require(uow, doc_id)
            view = DocumentView.from_document(document, stale=self._is_stale(document))
            if section is None:
                return view
            return replace(view, body=extract_section(document.body, section), section=section)

    def query(self, request: QueryRequest) -> list[DocumentSummary]:
        """Structured metadata filtering (``docir query``) — skeleton results.

        Two predicates are applied here rather than in SQL, and both *before*
        the limit, so ``--stale --limit 10`` means "ten stale documents" rather
        than "the stale ones among the first ten":

        * ``stale_only`` — staleness derives from the clock and the type's
          review cadence, neither of which the index stores.
        * ``code_paths`` — "which documents govern this file" is a glob match
          against each document's patterns, which SQL cannot express either.
        """
        _require_positive_limit(request.limit)
        _require_non_negative_offset(request.offset)

        def spec(*, limit: int | None, offset: int) -> DocumentFilter:
            return DocumentFilter(
                types=request.types,
                statuses=request.statuses,
                tags=request.tags,
                include_archived=request.include_archived,
                inactive_statuses=tuple(sorted(self._schema.inactive_statuses())),
                include_inactive=request.include_inactive,
                owner=request.owner,
                limit=limit,
                offset=offset,
            )

        predicate = self._post_sql_predicate(request)
        with self._uow_factory() as uow:
            if predicate is None:
                # The common path: the window is a LIMIT/OFFSET, so the cost of
                # a page does not grow with the corpus behind it.
                documents = uow.documents.query(spec(limit=request.limit, offset=request.offset))
            else:
                documents = self._scanned_page(uow, spec, request, predicate)
        return [self._summary(doc) for doc in documents]

    def _post_sql_predicate(self, request: QueryRequest) -> Callable[[Document], bool] | None:
        """The filters the index cannot express, as one test, or ``None``.

        Combined into a single predicate so the paging scan below stays one
        loop: two post-SQL filters that each walked the corpus their own way
        would give ``--owner X --stale --code src/a.py`` a different window
        depending on which ran first.
        """
        tests: list[Callable[[Document], bool]] = []
        if request.stale_only:
            tests.append(self._is_stale)
        if request.code_paths:
            paths = request.code_paths
            tests.append(lambda document: governs_any(document.code, paths))
        if not tests:
            return None
        return lambda document: all(test(document) for test in tests)

    def _scanned_page(
        self,
        uow: UnitOfWork,
        spec: Callable[..., DocumentFilter],
        request: QueryRequest,
        predicate: Callable[[Document], bool],
    ) -> list[Document]:
        """The window for a predicate SQL cannot express (`--stale`, `--code`).

        Staleness derives from the clock and the type's review cadence, and
        governance from a glob match — none of which the index stores, so both
        are filtered after the query. A SQL window would then count *rows
        scanned* rather than matching documents, which is the ordering bug
        issue-b4f441c7210f already fixed once.

        So scan in pages and stop as soon as the window is filled: bounded by
        how far in you have to read, not by the corpus. A corpus with no
        matches still walks it once, which is the honest cost of a predicate
        the database cannot see.
        """
        wanted = request.offset + request.limit
        matched: list[Document] = []
        scanned = 0
        while len(matched) < wanted:
            page = uow.documents.query(spec(limit=_SCAN_PAGE, offset=scanned))
            if not page:
                break
            scanned += len(page)
            matched.extend(doc for doc in page if predicate(doc))
        return matched[request.offset : request.offset + request.limit]

    def search(self, request: SearchRequest) -> list[DocumentSummary]:
        """Full-text search over active documents (``docir search``) — skeletons.

        Closed documents are filtered *after* the index returns, because FTS5
        does not know a document's status. A fixed over-fetch of ``limit * 2``
        therefore under-returned whenever more than half the top hits were
        closed — and an agent cannot tell a short result caused by filtering
        from one caused by a small corpus. The pool now widens until the limit
        is met or the index is exhausted, so short means short.
        """
        _require_positive_limit(request.limit)
        _require_non_negative_offset(request.offset)
        inactive = self._schema.inactive_statuses()
        # The window is applied after filtering, for the same reason `--stale`
        # is: FTS5 cannot see a document's status, so an index-level OFFSET
        # would skip rows that were never going to be returned.
        wanted = request.offset + request.limit
        with self._uow_factory() as uow:
            candidates = wanted * _SEARCH_OVERFETCH
            while True:
                hits = uow.search.search(request.text, limit=candidates)
                views: list[DocumentSummary] = []
                for hit in hits:
                    document = uow.documents.get(hit.doc_id)
                    if document is None:
                        continue
                    if not request.include_inactive and document.status in inactive:
                        continue
                    views.append(self._summary(document, score=-hit.bm25))
                    if len(views) >= wanted:
                        break
                # Enough, or the index had fewer matches than we asked for and
                # widening again would return the same rows.
                if len(views) >= wanted or len(hits) < candidates:
                    return views[request.offset :]
                candidates *= 2

    def context(self, request: ContextRequest) -> list[DocumentSummary]:
        """Ranked, minimal relevant document set (``docir context``) — skeletons.

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
            # Document vectors *and* section vectors, ranked together. The
            # scorer keeps each document's best, so a long document is reachable
            # by any one of its sections — for a body over ~1,900 characters the
            # document vector covers only the head, and the rest of it is in the
            # index only as chunks (adr-927aa43d9635).
            model_id = self._embedder.model_id
            candidates = [
                VectorCandidate(doc_id=doc_id, vector=vector)
                for doc_id, vector in uow.embeddings.active_vectors(model_id)
            ]
            candidates += [
                # An empty heading is a preamble or a continuation piece: it
                # ranks like any other chunk and simply cannot be named, so it
                # arrives as "no addressable section" rather than as "".
                VectorCandidate(doc_id=doc_id, vector=vector, section=heading or None)
                for doc_id, heading, vector in uow.chunks.active_vectors(model_id)
            ]
            semantic = self._scorer.semantic_ranking(query_vector, candidates)
            fused = self._scorer.fuse(hits, semantic)

            # Rank order, visible only, capped at what could ever be returned.
            ranked = self._visible_ranked(uow, fused, request, limit=request.limit)

            seed_budget = request.limit - expand
            selected: dict[str, DocumentSummary] = {
                document.id: self._ranked_summary(document, fscore)
                for document, fscore in ranked[:seed_budget]
            }
            if expand:
                self._augment_with_related(
                    uow, selected, budget=expand, include_inactive=request.include_inactive
                )
            # Give back neighbour slots the graph did not use.
            for document, fscore in ranked[seed_budget:]:
                if len(selected) >= request.limit:
                    break
                selected.setdefault(document.id, self._ranked_summary(document, fscore))

        return list(selected.values())

    def _visible_ranked(
        self,
        uow: UnitOfWork,
        fused: list[FusedScore],
        request: ContextRequest,
        *,
        limit: int,
    ) -> list[tuple[Document, FusedScore]]:
        """Resolve fused scores to visible documents, best first, at most ``limit``.

        The whole :class:`FusedScore` travels with its document rather than the
        two numbers the summary used to take: the ranking also knows *which
        section* matched, and threading each new field through as another tuple
        slot is how that kind of thing gets dropped.

        ``min_score`` is applied here, against the raw cosine rather than the
        fused score, and only where a cosine exists: a document with no current
        vector was retrieved lexically, and dropping a real full-text match for
        an *unknown* similarity would filter on staleness of the embedding
        queue rather than on relevance. `docir embed --flush` closes that gap.
        """
        resolved: list[tuple[Document, FusedScore]] = []
        for fscore in fused:
            if len(resolved) >= limit:
                break
            if (
                request.min_score is not None
                and fscore.similarity is not None
                and fscore.similarity < request.min_score
            ):
                continue
            document = uow.documents.get(fscore.doc_id)
            if document is None:
                continue
            if not self._is_visible(document, include_inactive=request.include_inactive):
                continue
            resolved.append((document, fscore))
        return resolved

    # -- helpers ------------------------------------------------------------

    def _summary(
        self,
        document: Document,
        *,
        score: float | None = None,
        similarity: float | None = None,
        matched_section: str | None = None,
        via_graph: bool = False,
    ) -> DocumentSummary:
        return DocumentSummary.from_document(
            document,
            stale=self._is_stale(document),
            score=score,
            similarity=similarity,
            matched_section=matched_section,
            via_graph=via_graph,
        )

    def _ranked_summary(self, document: Document, fscore: FusedScore) -> DocumentSummary:
        """The skeleton for a ranked hit, carrying everything the ranking knew."""
        return self._summary(
            document,
            score=fscore.score,
            similarity=fscore.similarity,
            matched_section=fscore.section,
        )

    def _allocate_id(self, request: AddDocumentRequest, uow: UnitOfWork) -> DocId:
        """Mint a fresh id, or adopt the one the caller supplied.

        Adoption exists for one case: a repository migrating an existing
        numbered corpus, where dropping `adr-0007` breaks every historical
        cross-reference. It is deliberately *not* inference — the caller reads
        the id off the file and states it, which is why this does not reopen the
        reasoning that killed a bulk `import` (a guess reported as a success).

        The invariant it appears to bypass is collision-freedom, and that
        survives: the id is checked against the index here, against the files by
        the create-time guard in the file store, and `reindex` raises the
        counter above anything on disk, so the next allocation lands past it.
        """
        if request.doc_id is None:
            return IdGenerator(self._schema, uow.documents).next_id(request.type)
        adopted = DocId(request.doc_id)
        expected = self._schema.get(request.type).prefix
        if adopted.prefix != expected:
            raise ValidationError(
                f"id {request.doc_id!r} does not match type {request.type!r}: "
                f"expected the {expected!r} prefix"
            )
        if uow.documents.exists(adopted.value):
            raise DuplicateDocumentIdError(f"cannot adopt {adopted.value!r}: it is already in use")
        self._raise_counter_past(adopted, request.type, uow)
        return adopted

    def _raise_counter_past(self, adopted: DocId, doc_type: str, uow: UnitOfWork) -> None:
        """Push the sequential counter above an adopted id.

        Without this, adopting `adr-0007` still left the counter at 1, so the
        next `add` minted `adr-0001` — safe (the generator skips ids already
        indexed) but not what "adopt an existing corpus" implies, and only
        corrected on the next `reindex`. The same guards as
        `_restore_id_sequences`: counter-backed types only, and never from a
        random-looking token, since hex digits include the decimal ones and
        about one token in 281 is all-digits.
        """
        type_schema = self._schema.get(doc_type)
        if type_schema.id_style != SEQUENTIAL_ID_STYLE or adopted.looks_random:
            return
        try:
            number = adopted.number
        except ValidationError:
            return
        uow.documents.raise_next_number(type_schema.prefix, number + 1)

    def _forced_transition(self, request: UpdateDocumentRequest, base: Document) -> str | None:
        """Describe the rule ``--override`` is about to break, if it breaks one.

        ``--override`` is narrower than it sounds: it still validates that the
        target status is one the type declares, so it only permits an illegal
        *jump* between legal statuses. Passing it on a transition that was legal
        anyway is not an override and must not warn.

        The result is not written to the file. docir has no actors (adr-90e994d931cc),
        so "who overrode this" has no answer worth storing, and git already
        records the status change; what was missing was only that the operator
        was told a rule had been bypassed, at the moment they bypassed it.
        """
        if not request.allow_transition_override or request.status is None:
            return None
        if request.status == base.status:
            return None
        if request.set_type is not None and request.set_type != base.type:
            # A retype is not a transition — there is no edge between two types'
            # status graphs to break, so nothing was overridden.
            return None
        type_schema = self._schema.types.get(base.type)
        if type_schema is None or type_schema.can_transition(base.status, request.status):
            return None
        legal = ", ".join(sorted(type_schema.transitions.get(base.status, frozenset()))) or "none"
        return (
            f"{base.status!r} -> {request.status!r} for type {base.type!r} "
            f"(legal from {base.status!r}: {legal})"
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

    def _neighbours_of(self, uow: UnitOfWork, seed: str) -> list[str]:
        """One-hop neighbours of ``seed``: successors first, then outgoing links.

        Expansion used to follow outgoing edges only, which left the graph unable
        to answer the question it exists for — *is this decision still current?*
        A ``supersedes`` edge points from the new document to the old one, so the
        replacement sits one hop away *backwards* and was never reachable from
        the document it replaces.
        """
        successors = uow.documents.incoming(seed, kinds=self._schema.successor_relation_kinds())
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
        """Stage metadata changes; return whether embedding-relevant text moved.

        The type is resolved first, because it selects the grammar every other
        field is checked against — the status enum, the relation whitelist, the
        required fields. On a retype those are all checked against the *target*
        type, never the one the document is leaving, which is also what lets a
        retype run on a document whose current type the schema no longer
        declares (adr-f8cce745d0d5).
        """
        content_changed = False
        target_type = self._apply_type(request, base, changes)
        if request.set_title is not None:
            changes["title"] = request.set_title
            content_changed = True
        if request.set_description is not None:
            changes["description"] = request.set_description
            content_changed = True
        self._apply_status(request, base, changes, target_type)
        if request.set_tags is not None:
            self._validator.validate_tags(request.set_tags, [tag.key for tag in uow.tags.all()])
            changes["tags"] = tuple(request.set_tags)
        self._apply_related(request, base, changes, uow, target_type)
        if request.set_owner is not None:
            changes["owner"] = request.set_owner
        if request.set_code is not None:
            self._validator.validate_code(request.set_code)
            changes["code"] = tuple(request.set_code)
        if request.mark_verified:
            changes["verified"] = self._clock.today()
        self._apply_code_digests(request, base, changes)
        return content_changed

    def _apply_code_digests(
        self, request: UpdateDocumentRequest, base: Document, changes: dict[str, object]
    ) -> None:
        """Stage the per-pattern evidence that goes with a verification.

        Runs after the code patterns are staged, and fingerprints the *resulting*
        set: `--set-code` and `--verified` in one call means the human read the
        document against the globs they just wrote, not the ones being replaced.

        Two rules, both instances of "absent means unknown":

        * With no matcher the digests are **dropped**, not carried over. A stale
          digest under a fresh ``verified`` date is the one combination that
          lies in the dangerous direction — it would report code as changed that
          the verification already covered, or hold evidence from a review two
          reviews ago.
        * Changing the globs without verifying **prunes** the digests of the
          patterns that went away and keeps the rest. Each surviving pattern was
          genuinely verified on the recorded date; a pattern just added was not,
          and gets no entry until someone verifies it.

        This is a mechanical field, so nothing here touches ``updated`` — the
        rule ``check --fix`` and the tag rewrites follow. It is deliberately not
        an embedding-relevant change either: no vector reads a digest.
        """
        patterns = base.code if request.set_code is None else tuple(request.set_code)
        if request.mark_verified:
            changes["verified_code"] = self._fingerprint_all(patterns)
        elif request.set_code is not None:
            kept = set(patterns)
            changes["verified_code"] = {
                pattern: digest for pattern, digest in base.verified_code.items() if pattern in kept
            }

    def _fingerprint_all(self, patterns: tuple[str, ...]) -> dict[str, str]:
        """Digest each pattern, dropping the ones that cannot be resolved."""
        if self._code_matcher is None:
            return {}
        digests = {}
        for pattern in patterns:
            digest = self._code_matcher.fingerprint(pattern)
            if digest is not None:
                digests[pattern] = digest
        return digests

    def _apply_type(
        self, request: UpdateDocumentRequest, base: Document, changes: dict[str, object]
    ) -> str:
        """Stage a retype and return the type the rest of the write is checked against.

        The id is deliberately untouched. It is the corpus's only address —
        every ``related`` edge that points here spells it out, as does anything
        outside the store — so a document retyped from ``decision`` keeps its
        ``adr-`` prefix under a type whose prefix is something else. The prefix
        records which type *minted* the id, not which type owns it now.

        A retype is not marked as a content change: ``type`` is in
        ``content_hash`` (a write must not silently lose one) but not in
        ``embedding_text``, so the vectors are unaffected and re-embedding the
        corpus to rename it would be pure cost.
        """
        if request.set_type is None or request.set_type == base.type:
            return base.type
        # Unknown target: raises naming the types that exist. The *source* type
        # is never looked up, which is what keeps the retype available as the
        # exit from a type `disable_types` has just removed.
        self._schema.get(request.set_type)
        changes["type"] = request.set_type
        return request.set_type

    def _apply_status(
        self,
        request: UpdateDocumentRequest,
        base: Document,
        changes: dict[str, object],
        target_type: str,
    ) -> None:
        """Stage the status, validated against ``target_type``.

        On a retype the check is *membership*, not transition: the type the
        document is leaving has its own transition graph, and that graph says
        nothing about a different type's. The current status is carried over
        when the new type declares it and the write is refused when it does
        not — never quietly reset to the new type's ``default_status``, which
        across a corpus rewrites every ``accepted`` to ``draft`` and reports
        success.
        """
        if target_type != base.type:
            status = base.status if request.status is None else request.status
            if request.status is None and not self._schema.get(target_type).is_valid_status(status):
                valid = ", ".join(self._schema.get(target_type).statuses)
                raise InvalidStatusError(
                    f"cannot retype {base.id!r} to {target_type!r}: its status {status!r} "
                    f"is not one that type declares. Pass --status with one of: {valid}"
                )
            self._validator.validate_status(target_type, status)
            if status != base.status:
                changes["status"] = status
            return
        if request.status is not None and request.status != base.status:
            if request.allow_transition_override:
                self._validator.validate_status(base.type, request.status)
            else:
                self._validator.validate_transition(base.type, base.status, request.status)
            changes["status"] = request.status

    def _apply_related(
        self,
        request: UpdateDocumentRequest,
        base: Document,
        changes: dict[str, object],
        uow: UnitOfWork,
        target_type: str,
    ) -> None:
        """Stage the edges, and re-check the existing ones when the type moved.

        ``allowed_relations`` is a property of the *source* type, so a retype can
        carry a document under a whitelist its untouched edges do not satisfy.
        They are validated even though this call did not supply them, because
        this is the write that would persist them.
        """
        retyped = target_type != base.type
        if request.set_related is None and not (retyped and base.related):
            return
        id_to_type = {doc.id: doc.type for doc in uow.documents.all()}
        if request.set_related is None:
            self._validator.validate_relation_kinds(target_type, base.related, id_to_type)
            return
        refs = _parse_refs(request.set_related)
        targets = [ref.target for ref in refs]
        self._validator.validate_related(targets, id_to_type, source_id=base.id)
        self._validator.validate_relation_kinds(target_type, refs, id_to_type)
        changes["related"] = refs

    def _apply_body(
        self,
        request: UpdateDocumentRequest,
        base: Document,
        changes: dict[str, object],
        disk_diverged: bool,
    ) -> bool:
        """Stage a body edit (at most one mode); return whether the body moved.

        ``disk_diverged`` is consulted only by ``replace_body`` — see
        :meth:`update` for why that is the only mode it can apply to. The
        parameter is named for what it measures rather than "stale", which in
        this codebase means a document past its review cadence: a different
        concept on a different clock.
        """
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
            if disk_diverged:
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
