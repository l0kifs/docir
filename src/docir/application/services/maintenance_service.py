"""Maintenance use cases: reindex fallback, Tier 1/2 checks, embedding flush.

These are not part of the normal write flow. ``reindex`` rebuilds the derived
index from the canonical files (after a hand-edit, fresh clone, or corruption);
``check`` and ``lint`` surface structural/advisory findings; ``flush`` forces a
synchronous embedding recompute.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from docir.domain.ports.embedder import Embedder
from docir.domain.ports.files import DocumentFileStore, TagFileStore
from docir.domain.ports.scheduler import EmbeddingScheduler
from docir.domain.ports.unit_of_work import UnitOfWork
from docir.domain.schema import Schema
from docir.domain.services.graph_checks import CheckIssue, GraphChecker
from docir.domain.services.similarity_lint import LintFinding, SimilarityLinter

UnitOfWorkFactory = Callable[[], UnitOfWork]


@dataclass(frozen=True, slots=True)
class ReindexResult:
    """Summary of a reindex run."""

    documents_indexed: int
    documents_removed: int
    tags_indexed: int


class MaintenanceService:
    """Use cases for index maintenance and the non-blocking check tiers."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        file_store: DocumentFileStore,
        tag_file_store: TagFileStore,
        scheduler: EmbeddingScheduler,
        embedder: Embedder,
        schema: Schema,
    ) -> None:
        self._uow_factory = uow_factory
        self._file_store = file_store
        self._tag_file_store = tag_file_store
        self._scheduler = scheduler
        self._embedder = embedder
        self._schema = schema
        self._graph_checker = GraphChecker(schema)
        self._linter = SimilarityLinter()

    def reindex(self, *, changed_only: bool = False) -> ReindexResult:
        """Rebuild the index from the canonical files (``docs reindex``)."""
        with self._uow_factory() as uow:
            tags_indexed = self._reindex_tags(uow)
            indexed, removed = self._reindex_documents(uow, changed_only=changed_only)
            uow.commit()
        self._scheduler.flush()
        return ReindexResult(
            documents_indexed=indexed,
            documents_removed=removed,
            tags_indexed=tags_indexed,
        )

    def reindex_embeddings(self) -> int:
        """Recompute every active document's vector (``docs reindex --embeddings``)."""
        with self._uow_factory() as uow:
            for document in uow.documents.all():
                if not document.archived:
                    uow.embeddings.mark_dirty(document.id)
            uow.commit()
        return self._scheduler.flush()

    def flush_embeddings(self) -> int:
        """Synchronously drain the embedding queue (``docs embed --flush``)."""
        return self._scheduler.flush()

    def check(self) -> list[CheckIssue]:
        """Tier 1 structural checks over the graph (``docs check``).

        Combines index-based graph checks (cycles, orphans, layering, dangling
        references) with a file-scan for duplicate ids — the latter reads the
        source files directly, because two files sharing an id are invisible in
        the index (which dedupes by primary key). Duplicate ids are exactly what
        a merge of two branches that both minted the same sequential id
        produces, so this is the check that guards a merge into ``main``.
        """
        with self._uow_factory() as uow:
            documents = uow.documents.all()
            relations = uow.documents.relations()
        issues = self._graph_checker.check(documents, relations)
        issues.extend(self._find_duplicate_ids())
        return issues

    def _find_duplicate_ids(self) -> list[CheckIssue]:
        paths_by_id: dict[str, list[str]] = {}
        for document in self._file_store.scan():
            paths_by_id.setdefault(document.id, []).append(document.path or "?")
        issues: list[CheckIssue] = []
        for doc_id, paths in sorted(paths_by_id.items()):
            if len(paths) > 1:
                joined = ", ".join(sorted(paths))
                issues.append(
                    CheckIssue(
                        kind="duplicate-id",
                        message=f"id {doc_id!r} is used by {len(paths)} files: {joined}",
                        doc_ids=(doc_id,),
                    )
                )
        return issues

    def lint_deep(self) -> list[LintFinding]:
        """Tier 2 advisory checks (``docs lint --deep``)."""
        with self._uow_factory() as uow:
            self._scheduler.flush()
            vectors = uow.embeddings.active_vectors()
            documents = [d for d in uow.documents.all() if not d.archived]
        findings = self._linter.find_duplicates(vectors)
        findings.extend(self._linter.find_scope_creep(documents))
        return findings

    # -- helpers ------------------------------------------------------------

    def _reindex_tags(self, uow: UnitOfWork) -> int:
        file_tags = self._tag_file_store.load()
        file_keys = {tag.key for tag in file_tags}
        for tag in file_tags:
            uow.tags.save(tag)
        for existing in uow.tags.all():
            if existing.key not in file_keys:
                uow.tags.delete(existing.key)
        return len(file_tags)

    def _reindex_documents(self, uow: UnitOfWork, *, changed_only: bool) -> tuple[int, int]:
        seen: set[str] = set()
        indexed = 0
        for document in self._file_store.scan():
            seen.add(document.id)
            if changed_only:
                current = uow.documents.get(document.id)
                if current is not None and current.content_hash() == (document.content_hash()):
                    continue
            uow.documents.save(document)
            if document.archived:
                uow.search.remove(document.id)
                uow.embeddings.remove(document.id)
            else:
                uow.search.index(document)
                uow.embeddings.mark_dirty(document.id)
            indexed += 1

        removed = 0
        if not changed_only:
            for stale in uow.documents.all():
                if stale.id not in seen:
                    uow.documents.delete(stale.id)
                    uow.search.remove(stale.id)
                    uow.embeddings.remove(stale.id)
                    removed += 1
        return indexed, removed
