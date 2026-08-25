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
from docir.modules.documents.domain.services import schema_shape
from docir.modules.documents.domain.services.graph_checks import CheckIssue, GraphChecker
from docir.modules.documents.domain.services.similarity_lint import LintFinding, SimilarityLinter
from docir.modules.documents.domain.value_objects.identifiers import DocId
from docir.modules.indexing.api import DrainResult, EmbeddingScheduler
from docir.platform.clock import Clock
from docir.platform.embedding import Embedder
from docir.platform.errors import ValidationError
from docir.platform.filesystem.ports import CodeMatcher, DocumentFileStore, TagFileStore
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
    #: is keyed by document. A full reindex re-embeds everything it re-saved, so
    #: this was always happening and simply went unreported, which is what let
    #: `--embeddings` look like the only way to get it (issue-b24e14474820).
    #:
    #: Not a vector count -- `vectors_written` is. It is also not always
    #: `documents_indexed`: an archived document is re-saved and has its vectors
    #: *removed*, so it counts there and not here.
    embeddings_recomputed: int = 0
    #: Vectors actually written by the drain: one per document plus one per `##`
    #: section (adr-927aa43d9635), so ~4x `embeddings_recomputed` on a real
    #: corpus. This is the number that explains the runtime -- embedding is ~96%
    #: of a full rebuild, and it is linear in vectors rather than documents, so
    #: the document count alone cannot say why 315 of them took a minute.
    vectors_written: int = 0


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
        version: str,
        code_matcher: CodeMatcher | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._file_store = file_store
        self._tag_file_store = tag_file_store
        self._scheduler = scheduler
        self._embedder = embedder
        self._schema = schema
        self._clock = clock
        #: The docir version this process is running. Stamped into the index on
        #: every rebuild, so a later run can say the derived state was produced
        #: by code that is no longer installed.
        self._version = version
        #: ``None`` when the store has no repository above it: there is then
        #: nothing to resolve a ``code`` glob against, and the finding is
        #: skipped rather than reported against a tree that does not exist.
        self._code_matcher = code_matcher
        self._prefixes = schema.prefixes()
        self._graph_checker = GraphChecker(schema)
        self._linter = SimilarityLinter()

    def _save(self, uow: UnitOfWork, document: Document) -> None:
        """Persist a document and the mention edges its body implies.

        The same pairing `DocumentService._save` makes, for the same reason:
        a rebuild that refreshed metadata and left the derived graph behind
        would make `docir reindex` the command that *creates* stale mentions.
        """
        uow.documents.save(document)
        uow.mentions.replace(document.id, document.mentioned_ids(self._prefixes))

    def reindex(self, *, changed_only: bool = False) -> ReindexResult:
        """Rebuild the index from the canonical files (``docir reindex``).

        Files that do not parse are skipped (see :class:`ReindexResult`) and
        counted, so "rebuilt 12 documents" cannot quietly mean "of 13 on disk".
        ``docir check`` reports each one individually as a ``malformed`` finding.

        A full rebuild re-embeds everything it re-saves, which is why there is
        no "recompute the vectors too" mode: the one that existed skipped the
        rebuild rather than adding to it, and so recomputed exactly these
        vectors while writing neither the schema baseline nor the build stamp
        (adr-6a4718fa7a7d, issue-b24e14474820).
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
        drained = self._scheduler.flush()
        return ReindexResult(
            documents_indexed=indexed,
            documents_removed=removed,
            tags_indexed=tags_indexed,
            documents_skipped=len(self._file_store.find_malformed()),
            embeddings_recomputed=drained.documents,
            vectors_written=drained.vectors,
        )

    def resync(self) -> ReindexResult:
        """Rebuild only what the build stamp says is not already indexed.

        What ``docir self upgrade`` runs. A full rebuild re-embeds every
        document it re-saves, and on a 300-document store that is ~96% of the
        command — the right price exactly once, when the code that *reads*
        documents has moved under them (adr-6a4718fa7a7d: a release that changes
        chunking is a full rebuild). Paid again against a store this same build
        already indexed, it recomputes vectors byte-identical to the ones
        already there, which is what made an upgrade of an unchanged corpus cost
        a minute: measured at 58.4 s against 1.5 s for the same store's changed
        pass, 315 documents and 1,326 vectors.

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

    def flush_embeddings(self) -> DrainResult:
        """Synchronously drain the embedding queue (``docir embed --flush``).

        Returns both counts rather than the document one alone: the caller is
        reporting to a human who has just waited for it, and what they waited
        for was the vectors.
        """
        return self._scheduler.flush()

    def check(self) -> list[CheckIssue]:
        """Tier 1 structural checks over the graph (``docir check``).

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
            mentions = uow.mentions.all_resolved()
        issues = self._graph_checker.check(
            documents,
            relations,
            self._clock.today(),
            known_tags=known_tags,
            code_matches=self._resolve_code(documents),
            code_digests=self._resolve_code_digests(documents),
            mentions=mentions,
        )
        issues.extend(self._find_duplicate_ids())
        issues.extend(self._find_malformed())
        issues.extend(self._drift_issues())
        issues.extend(self._build_issues())
        return issues

    def stale_index_build(self) -> str | None:
        """The version that built this index, when it is not the running one.

        ``None`` covers both "built by this docir" and "never recorded" — absent
        means unknown, the rule the schema baseline follows. A store that has
        not been rebuilt since the table arrived reports nothing rather than
        reporting itself as stale, which would fire on every store exactly once
        for no reason anyone could act on differently.
        """
        with self._uow_factory() as uow:
            recorded = uow.index_build.get()
        return None if recorded is None or recorded == self._version else recorded

    def _build_issues(self) -> list[CheckIssue]:
        """The index-was-built-by-other-code finding.

        Inequality, not "older than": a downgrade needs the same rebuild, and
        ordering two version strings is a question this does not have to answer
        to give the right advice.

        A warning, and for a stronger reason than schema drift: nothing is
        wrong with the documents *or* the rules — only the derived state was
        produced by code that is no longer installed, which is the ordinary
        state of every store between an upgrade and the next `reindex`.
        """
        recorded = self.stale_index_build()
        if recorded is None:
            return []
        return [
            CheckIssue(
                kind="stale-index-build",
                message=(
                    f"the index was built by docir {recorded}, this is {self._version} — "
                    f"run `docir self upgrade` (or `docir reindex`) to rebuild it"
                ),
                doc_ids=(),
            )
        ]

    def schema_drift(self) -> list[str]:
        """How the active schema differs from the one the index was built against.

        Empty means "nothing moved" *or* "nothing to compare against": a store
        that has never been reindexed since the baseline table arrived has no
        prior value, and absent means unknown rather than unchanged. Reporting
        an empty baseline as a wholesale addition would fire the loudest
        possible finding on every store, once, for no reason.

        Returned as lines rather than a structure because the report *is* the
        product: the change arrived without a diff to read, and this is the diff
        (issue-d891ab5501e6).
        """
        with self._uow_factory() as uow:
            baseline = uow.schema_baseline.get()
        if baseline is None:
            return []
        return schema_shape.diff(baseline, schema_shape.describe(self._schema))

    def _drift_issues(self) -> list[CheckIssue]:
        """The drift, as Tier 1 findings — one per change, so each is greppable.

        A warning, and the argument is the one every classification finding
        here makes, at its strongest: the change ships in the *package*, so a
        corpus that passed yesterday can fail today with no commit to point at.
        It also does not describe damage — the documents are untouched and it is
        the *rule* that moved. What it does is make the rest of `check`
        legible: `unknown-type` and `missing-required` become consequences with
        a stated cause instead of findings that appeared from nowhere.
        """
        return [
            CheckIssue(
                kind="schema-drift",
                message=(
                    f"the active schema differs from the one the index was built "
                    f"against: {line} (run `docir reindex` once you have dealt with it)"
                ),
                doc_ids=(),
            )
            for line in self.schema_drift()
        ]

    def _resolve_code(self, documents: list[Document]) -> dict[str, bool] | None:
        """Which declared ``code`` globs still match something on disk.

        Resolved once per distinct pattern rather than once per document: a
        pattern shared by five decisions is one walk of the tree, and the
        matcher stops at the first hit either way.
        """
        if self._code_matcher is None:
            return None
        patterns = {pattern for document in documents for pattern in document.code}
        return {pattern: self._code_matcher.matches(pattern) for pattern in sorted(patterns)}

    def _resolve_code_digests(self, documents: list[Document]) -> dict[str, str] | None:
        """Fingerprint only the globs some document has actually been verified against.

        Restricted to those on purpose. A fingerprint reads every file the
        pattern matches, where :meth:`_resolve_code` stops at the first hit, so
        digesting every declared glob would make `check` pay to hash whole
        subtrees in order to compare them against nothing. A pattern nobody has
        verified has no recorded value to differ from.

        Unresolvable patterns are dropped rather than stored as a sentinel:
        absent is already the unknown answer the check skips.
        """
        if self._code_matcher is None:
            return None
        verified = {
            pattern
            for document in documents
            if not document.archived
            for pattern in document.code
            if pattern in document.verified_code
        }
        digests = {}
        for pattern in sorted(verified):
            digest = self._code_matcher.fingerprint(pattern)
            if digest is not None:
                digests[pattern] = digest
        return digests

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
        first needs somebody to read the file and say what it was meant to be,
        the second a schema decision. Both are judgements, and a repair has
        nothing to read *with*. They come back in ``remaining``.
        """
        # Repair reads the files as the source of truth, so bring the index in
        # line first: id allocation consults it to find a free number. Both
        # passes are `--changed`, because agreeing with the files is all either
        # one is for: the deletion sweep and `_restore_id_sequences` run in that
        # mode too (the id allocator sees every id on disk either way), and what
        # it skips is re-saving — and so re-embedding — documents that did not
        # move. A re-issued file's hash changes with its id, so the second pass
        # still picks up everything `_repair_duplicate_ids` rewrote.
        self.reindex(changed_only=True)
        actions = self._repair_duplicate_ids()
        if actions:
            self.reindex(changed_only=True)
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
                # `updated` is deliberately left alone: staleness measures when
                # somebody last vouched for the content, and dropping a broken
                # link is not that. Bumping it would launder the review clock.
                repaired = document.with_updates(related=kept)
                self._file_store.write(repaired)
                self._save(uow, repaired)
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
        """Tier 2 advisory checks (``docir lint --deep``)."""
        with self._uow_factory() as uow:
            self._scheduler.flush()
            # Document vectors only, deliberately: the duplicate check asks
            # "are these two documents the same document", and chunk vectors
            # would answer "do these two documents share a section" — a
            # different, much noisier question.
            vectors = uow.embeddings.active_vectors(self._embedder.model_id)
            documents = [d for d in uow.documents.all() if not d.archived]
            # A pair the author has linked has already been explained; only the
            # unnoticed similarity is worth reporting (issue-08437ba704ff).
            linked = {frozenset((rel.source, rel.target)) for rel in uow.documents.relations()}
            # Tier 2 and not Tier 1, measured: every unresolved mention in this
            # project's own corpus is a documentation example, so a warning
            # would fire only on correct usage (adr-e86c5040d626).
            unresolved = uow.mentions.unresolved()
        findings = self._linter.find_duplicates(vectors, linked)
        findings.extend(self._linter.find_unresolved_mentions(unresolved))
        findings.extend(self._linter.find_scope_creep(documents, self._schema))
        # Reads the bodies already loaded above, not the stored chunks: the
        # answer must describe the document as it is now, not as it was when
        # the embedding queue last drained.
        findings.extend(self._linter.find_oversized_sections(documents))
        findings.extend(self._linter.find_ambiguous_headings(documents))
        findings.extend(self._linter.find_broken_expressions(documents))
        # Cross-document by nature: a reference is only stale relative to where
        # the section ended up, so this is the one lint that needs the corpus.
        findings.extend(self._linter.find_unqualified_section_refs(documents))
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
            self._save(uow, document)
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
