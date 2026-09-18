"""Rebuilding the derived index from the canonical markdown files.

The index is a compile artifact — metadata, FTS rows, the relation and mention
graphs, the id counter and two stamps — and this is the only thing that rebuilds
it. Split out of :class:`MaintenanceService`, which changed for three unrelated
reasons; the rebuild is the one of them that writes.

Every path here ends in one transaction, so a rebuild that fails leaves the
previous index rather than half of a new one, and the schema baseline and build
stamp are written by :meth:`IndexRebuilder._rebuild` and nowhere else.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from docir.modules.documents.application.services.document_saving import save_with_mentions
from docir.modules.documents.domain.schema import SEQUENTIAL_ID_STYLE, Schema
from docir.modules.documents.domain.services import schema_shape
from docir.modules.documents.domain.value_objects.identifiers import DocId
from docir.modules.indexing.api import EmbeddingScheduler
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
    #: Documents re-embedded before the run returned -- the drained queue, which
    #: is keyed by document. A full reindex re-embedded everything it re-saved, so
    #: this was always happening and simply went unreported, which is what let
    #: `--embeddings` look like the only way to get it (issue-b24e14474820). It
    #: queues every one and the drain recomputes what is owed now
    #: (issue-77dd42e3a03a), so on an unchanged corpus this is 0.
    #:
    #: Not a vector count -- `vectors_written` is. It is also not always
    #: `documents_indexed`: an archived document is re-saved and has its vectors
    #: *removed*, so it counts there and not here.
    embeddings_recomputed: int = 0
    #: Vectors actually written by the drain: one per document plus one per `##`
    #: section (adr-927aa43d9635), so ~4x `embeddings_recomputed` on a real
    #: corpus. This is the number that explains the runtime -- embedding is ~96%
    #: of a rebuild *that embeds*, and it is linear in vectors rather than
    #: documents, so the document count alone cannot say why 315 of them took a
    #: minute. A rebuild whose inputs all match skips the lot and writes none.
    vectors_written: int = 0


class IndexRebuilder:
    """Rebuilds the derived index from the files, in one transaction."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        file_store: DocumentFileStore,
        tag_file_store: TagFileStore,
        scheduler: EmbeddingScheduler,
        schema: Schema,
        version: str,
    ) -> None:
        self._uow_factory = uow_factory
        self._file_store = file_store
        self._tag_file_store = tag_file_store
        self._scheduler = scheduler
        self._schema = schema
        #: The docir version this process is running. Stamped into the index on
        #: every rebuild, so a later run can say the derived state was produced
        #: by code that is no longer installed.
        self._version = version
        self._prefixes = schema.prefixes()

    def reindex(self, *, changed_only: bool = False) -> ReindexResult:
        """Rebuild the index from the canonical files (``docir reindex``).

        Files that do not parse are skipped (see :class:`ReindexResult`) and
        counted, so "rebuilt 12 documents" cannot quietly mean "of 13 on disk".
        ``docir check`` reports each one individually as a ``malformed`` finding.

        A full rebuild re-saves every document and so queues every one for
        embedding, but the drain recomputes only the vectors whose inputs
        actually moved (issue-77dd42e3a03a) — which is why there is still no
        "recompute the vectors too" mode: the one that existed skipped the
        rebuild rather than adding to it, and so recomputed exactly these
        vectors while writing neither the schema baseline nor the build stamp
        (adr-6a4718fa7a7d, issue-b24e14474820).
        """
        indexed, removed, tags_indexed = self._rebuild(changed_only=changed_only)
        drained = self._scheduler.flush()
        return ReindexResult(
            documents_indexed=indexed,
            documents_removed=removed,
            tags_indexed=tags_indexed,
            documents_skipped=len(self._file_store.find_malformed()),
            embeddings_recomputed=drained.documents,
            vectors_written=drained.vectors,
        )

    def bootstrap(self) -> ReindexResult:
        """Rebuild the index, leaving the vectors to the queue.

        :meth:`reindex` without the drain, for the one state where a store has
        files and no projection of them at all — a fresh clone, a new `git
        worktree`. It is what makes that state recoverable without a command,
        so it has to cost what a command would not be worth: measured on this
        repository's 191 documents, the rebuild is ~0.9s while the drain that
        follows it in `reindex` is ~70s, because the drain loads the embedding
        model and writes 1,454 vectors.

        Deferring them is not skipping them. Every document rebuilt here is
        marked dirty, which is the same queue a write leaves behind, drained by
        the daemon's scheduler within its debounce window. Until it drains,
        `context` ranks on full-text and the graph alone and `docir doctor`
        says so as `embeddings-pending` — a worse answer than a warm store, and
        an answer, where the state this replaces returned nothing at all. A
        process with no daemon (`--no-daemon`, CI) leaves the queue standing;
        `docir reindex` or `docir embed --flush` is what closes it there, which
        is why neither drops out of the documented CI order.

        This is not the recompute-only mode adr-6a4718fa7a7d rejected. That one
        skipped the *rebuild* and recomputed vectors, writing neither stamp;
        this does the whole rebuild — both stamps included, so `check` does not
        immediately report drift against a store docir has just built — and
        defers only the vectors.
        """
        indexed, removed, tags_indexed = self._rebuild(changed_only=False)
        return ReindexResult(
            documents_indexed=indexed,
            documents_removed=removed,
            tags_indexed=tags_indexed,
            documents_skipped=len(self._file_store.find_malformed()),
            embeddings_recomputed=0,
            vectors_written=0,
        )

    def _rebuild(self, *, changed_only: bool) -> tuple[int, int, int]:
        """The transaction both rebuild paths share, without the drain.

        One writer for the two stamps, so a rebuild that defers its vectors
        cannot also forget to record which schema and which build produced the
        rows it wrote.
        """
        with self._uow_factory() as uow:
            tags_indexed = self._reindex_tags(uow)
            indexed, removed = self._reindex_documents(uow, changed_only=changed_only)
            # The schema baseline advances here and nowhere else. `reindex` is
            # already the "make the derived state agree with the sources"
            # command, and the baseline is derived state; giving drift its own
            # acknowledge verb would add a ritual whose only effect is to
            # silence a report (the argument adr-bd7c4f3c5764 makes about
            # staleness). Until it is run, `check` keeps naming the change.
            uow.schema_baseline.set(schema_shape.describe(self._schema))
            # Same writer, same argument, a different question: the baseline
            # compares schemas and so cannot see a release that changed how
            # documents are read rather than what they must contain.
            uow.index_build.set(self._version)
            uow.commit()
        return indexed, removed, tags_indexed

    def resync(self) -> ReindexResult:
        """Rebuild only what the build stamp says is not already indexed.

        What ``docir self upgrade`` runs. The stamp decides whether every
        document's *metadata* is re-read — the FTS row, the relation and mention
        edges, the frontmatter the index projects — because a release can change
        how a document is read without changing the document
        (adr-6a4718fa7a7d), and that is the question the version answers.

        It no longer decides what gets embedded. The full pass used to re-embed
        every document it re-saved, which was ~96% of the command and made an
        upgrade of an *unchanged* corpus cost 146s against this repository's 205
        documents; the drain now compares what the model would read against what
        it read last time and skips what matches (issue-77dd42e3a03a). So the
        expensive half is paid when the chunking or the model moved, which is
        what adr-6a4718fa7a7d actually asked for, rather than on every release.

        The stamp has to be read *before* the rebuild: both modes write it, so a
        cheap pass would erase the evidence that a full one was needed.

        It deliberately does **not** go through :meth:`stale_index_build`, which
        answers a different question. That one folds "never recorded" into
        ``None`` because absent means unknown and `check` must not report a
        finding nobody can act on. Here unknown has to mean *rebuild*: a store
        with no stamp was last built by code that did not write one, so its
        vectors are exactly the ones a full pass exists to replace. Equality
        against the running version is the only reading that is safe in both
        directions — a downgrade needs the rebuild as much as an upgrade.
        """
        with self._uow_factory() as uow:
            recorded = uow.index_build.get()
        return self.reindex(changed_only=recorded == self._version)

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
            save_with_mentions(uow, document, self._prefixes)
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
            # different thing entirely (issue-d8295c5c76d1).
            if orphaned.id not in seen:
                uow.documents.delete(orphaned.id)
                uow.search.remove(orphaned.id)
                uow.embeddings.remove(orphaned.id)
                uow.chunks.remove(orphaned.id)
                removed += 1
        return indexed, removed
