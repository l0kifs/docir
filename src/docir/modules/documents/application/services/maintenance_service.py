"""Maintenance use cases: reindex fallback, Tier 1/2 checks, embedding flush.

These are not part of the normal write flow. ``reindex`` rebuilds the derived
index from the canonical files (after a hand-edit, fresh clone, or corruption);
``check`` and ``lint`` surface structural/advisory findings; ``flush`` forces a
synchronous embedding recompute.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from docir.modules.documents.application.services.id_generator import IdGenerator
from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.schema import SEQUENTIAL_ID_STYLE, Schema
from docir.modules.documents.domain.services.graph_checks import CheckIssue, GraphChecker
from docir.modules.documents.domain.services.similarity_lint import LintFinding, SimilarityLinter
from docir.modules.documents.domain.value_objects.identifiers import DocId
from docir.modules.indexing.api import EmbeddingScheduler
from docir.platform.clock import Clock
from docir.platform.embedding import Embedder
from docir.platform.errors import ValidationError
from docir.platform.filesystem.ports import DocumentFileStore, TagFileStore
from docir.platform.persistence.unit_of_work import UnitOfWork

UnitOfWorkFactory = Callable[[], UnitOfWork]


@dataclass(frozen=True, slots=True)
class ReindexResult:
    """Summary of a reindex run.

    ``documents_skipped`` counts source files that would not parse. ``scan`` is
    best-effort by design — one bad file must not abort the rebuild of the rest —
    but reporting only what succeeded made a partial rebuild indistinguishable
    from a complete one. On a fresh clone (nothing in the index to remove) two
    files on disk and one indexed produced output that read as success, and the
    unparseable document was simply absent from every read path.
    """

    documents_indexed: int
    documents_removed: int
    tags_indexed: int
    documents_skipped: int = 0


@dataclass(frozen=True, slots=True)
class RepairAction:
    """One repair that was applied, in the caller's terms."""

    kind: str  # the finding kind repaired: duplicate-id | dangling
    message: str
    doc_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RepairResult:
    """What ``docir check --fix`` changed, and what a human still has to decide.

    ``remaining`` is the check output *after* repairing, so an empty
    error-severity remainder means the corpus is mechanically sound again.
    """

    actions: tuple[RepairAction, ...]
    remaining: tuple[CheckIssue, ...]


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
        clock: Clock,
    ) -> None:
        self._uow_factory = uow_factory
        self._file_store = file_store
        self._tag_file_store = tag_file_store
        self._scheduler = scheduler
        self._embedder = embedder
        self._schema = schema
        self._clock = clock
        self._graph_checker = GraphChecker(schema)
        self._linter = SimilarityLinter()

    def reindex(self, *, changed_only: bool = False) -> ReindexResult:
        """Rebuild the index from the canonical files (``docs reindex``).

        Files that do not parse are skipped (see :class:`ReindexResult`) and
        counted, so "rebuilt 12 documents" cannot quietly mean "of 13 on disk".
        ``docs check`` reports each one individually as a ``malformed`` finding.
        """
        with self._uow_factory() as uow:
            tags_indexed = self._reindex_tags(uow)
            indexed, removed = self._reindex_documents(uow, changed_only=changed_only)
            uow.commit()
        self._scheduler.flush()
        return ReindexResult(
            documents_indexed=indexed,
            documents_removed=removed,
            tags_indexed=tags_indexed,
            documents_skipped=len(self._file_store.find_malformed()),
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

        Also catches the two Tier 0 rules a hand-edit can bypass: a status the
        type does not declare and a tag that is not in the registry. The CLI
        cannot write either, so both mean a file was edited outside it — the
        case `reindex` exists for and `check` could not previously see.

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
            known_tags = frozenset(tag.key for tag in uow.tags.all())
        issues = self._graph_checker.check(
            documents, relations, self._clock.today(), known_tags=known_tags
        )
        issues.extend(self._find_duplicate_ids())
        issues.extend(self._find_malformed())
        return issues

    def _find_malformed(self) -> list[CheckIssue]:
        """Report source files that do not parse (skipped by reindex/scan)."""
        return [
            CheckIssue(kind="malformed", message=reason, doc_ids=())
            for _path, reason in self._file_store.find_malformed()
        ]

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

    def repair(self) -> RepairResult:
        """Fix the mechanically-fixable Tier 1 damage (``docir check --fix``).

        Two kinds are repairable without guessing at intent:

        * ``duplicate-id`` — two files claim one id, so one of them is invisible
          to every read path. The oldest keeps the id (it is the one existing
          links were written against); the rest are re-issued and their files
          renamed.
        * ``dangling`` — an edge resolves to nothing, so it is dropped.

        ``malformed`` and ``unknown-type`` are deliberately *not* touched: the
        first needs a human to say what the file was meant to be, the second
        needs a schema decision. They come back in ``remaining``.
        """
        # Repair reads the files as the source of truth, so bring the index in
        # line first: id allocation consults it to find a free number.
        self.reindex()
        actions = self._repair_duplicate_ids()
        if actions:
            self.reindex()
        actions.extend(self._repair_dangling())
        return RepairResult(actions=tuple(actions), remaining=tuple(self.check()))

    def _repair_duplicate_ids(self) -> list[RepairAction]:
        """Re-issue every file after the first that claims a given id."""
        by_id: dict[str, list[Document]] = {}
        for document in self._file_store.scan():
            by_id.setdefault(document.id, []).append(document)

        actions: list[RepairAction] = []
        with self._uow_factory() as uow:
            generator = IdGenerator(self._schema, uow.documents)
            for doc_id, documents in sorted(by_id.items()):
                if len(documents) < 2:
                    continue
                # The oldest file keeps the id: any existing `related` edge naming
                # it was written against that document, and an edge cannot say
                # which of the two it meant.
                documents.sort(key=lambda doc: (doc.created, doc.path or ""))
                for duplicate in documents[1:]:
                    new_id = str(generator.next_id(duplicate.type))
                    old_path = duplicate.path
                    reissued = duplicate.with_updates(id=new_id, path=None)
                    new_path = self._file_store.write(reissued, create=True)
                    if old_path:
                        self._file_store.delete(old_path)
                    actions.append(
                        RepairAction(
                            kind="duplicate-id",
                            message=(
                                f"re-issued {doc_id!r} as {new_id!r} "
                                f"({old_path} -> {new_path}); {documents[0].path} keeps the id"
                            ),
                            doc_ids=(doc_id, new_id),
                        )
                    )
            uow.commit()  # persist the counter advances the re-issue consumed
        return actions

    def _repair_dangling(self) -> list[RepairAction]:
        """Drop `related` edges whose target does not exist."""
        actions: list[RepairAction] = []
        with self._uow_factory() as uow:
            documents = uow.documents.all()
            existing = {document.id for document in documents}
            for document in documents:
                kept = tuple(ref for ref in document.related if ref.target in existing)
                if len(kept) == len(document.related):
                    continue
                dropped = tuple(
                    ref.target for ref in document.related if ref.target not in existing
                )
                # `updated` is deliberately left alone: staleness measures when a
                # human last vouched for the content, and dropping a broken link
                # is not that. Bumping it here would launder the review clock.
                repaired = document.with_updates(related=kept)
                self._file_store.write(repaired)
                uow.documents.save(repaired)
                uow.search.index(repaired)
                actions.append(
                    RepairAction(
                        kind="dangling",
                        message=(
                            f"dropped {len(dropped)} dead edge(s) from {document.id!r}: "
                            f"{', '.join(dropped)}"
                        ),
                        doc_ids=(document.id, *dropped),
                    )
                )
            uow.commit()
        return actions

    def lint_deep(self) -> list[LintFinding]:
        """Tier 2 advisory checks (``docs lint --deep``)."""
        with self._uow_factory() as uow:
            self._scheduler.flush()
            # Document vectors only, deliberately: the duplicate check asks
            # "are these two documents the same document", and chunk vectors
            # would answer "do these two documents share a section" — a
            # different, much noisier question.
            vectors = uow.embeddings.active_vectors(self._embedder.model_id)
            documents = [d for d in uow.documents.all() if not d.archived]
            # A pair the author has linked has already been explained; only the
            # unnoticed similarity is worth reporting (GAP-055).
            linked = {frozenset((rel.source, rel.target)) for rel in uow.documents.relations()}
        findings = self._linter.find_duplicates(vectors, linked)
        findings.extend(self._linter.find_scope_creep(documents, self._schema))
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

    def _restore_id_sequences(self, uow: UnitOfWork, doc_ids: set[str]) -> None:
        """Rebuild the id counter from the ids the files already use.

        The counter lives in the derived index but was the one table ``reindex``
        did not reconstruct, so a rebuilt store (a fresh clone — the index is
        gitignored) re-minted a live id on the next ``add``: two files claimed
        it and the older document fell out of every read path.

        Only types that actually draw from a counter are considered. Deciding
        that by the id's shape alone is not enough — hex digits include the
        decimal digits, so about one random token in 281 is all-digits and would
        otherwise be read as a hundred-billion-th sequential id and shove the
        counter up with it.
        """
        counted_prefixes = {
            type_schema.prefix
            for type_schema in self._schema.types.values()
            if type_schema.id_style == SEQUENTIAL_ID_STYLE
        }
        if not counted_prefixes:
            return

        highest: dict[str, int] = {}
        for doc_id in doc_ids:
            try:
                parsed = DocId(doc_id)
            except ValidationError:
                continue  # foreign id, not something this store mints
            if parsed.prefix not in counted_prefixes or parsed.looks_random:
                continue  # random-style type, or a token left behind by one
            try:
                number = parsed.number
            except ValidationError:
                continue
            if number > highest.get(parsed.prefix, 0):
                highest[parsed.prefix] = number
        for prefix, number in highest.items():
            uow.documents.raise_next_number(prefix, number + 1)

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
                uow.chunks.remove(document.id)
            else:
                uow.search.index(document)
                uow.embeddings.mark_dirty(document.id)
            indexed += 1

        # Restore the counter from the ids on disk, including the ones ``--changed``
        # skipped re-saving: an unchanged file still owns its id.
        self._restore_id_sequences(uow, seen)

        # The removal sweep runs in BOTH modes. It used to be skipped under
        # ``--changed``, which gave the fast path quietly different semantics: a
        # document deleted from the filesystem stayed in the index and kept
        # being returned by every read path — `get` answered for a file that no
        # longer existed. Nothing in `--help` or the README said so.
        #
        # It is not why ``--changed`` is fast. ``scan()`` runs in full either
        # way (that is where the parsing cost is, and ``seen`` has to be
        # complete for ``_restore_id_sequences`` above); ``--changed`` skips the
        # *writes* — save, FTS index, embedding recompute. The sweep adds one
        # query and a set difference.
        removed = 0
        for orphaned in uow.documents.all():
            # Named `orphaned`, not `stale`: in this codebase `stale` is the
            # review-cadence feature. An index row whose file is gone is a
            # different thing entirely (GAP-032).
            if orphaned.id not in seen:
                uow.documents.delete(orphaned.id)
                uow.search.remove(orphaned.id)
                uow.embeddings.remove(orphaned.id)
                uow.chunks.remove(orphaned.id)
                removed += 1
        return indexed, removed
