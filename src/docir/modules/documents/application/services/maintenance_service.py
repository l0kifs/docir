"""Maintenance use cases: reindex fallback, Tier 1/2 checks, embedding flush.

These are not part of the normal write flow. ``reindex`` rebuilds the derived
index from the canonical files (after a hand-edit, fresh clone, or corruption);
``check`` and ``lint`` surface structural/advisory findings; ``flush`` forces a
synchronous embedding recompute.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from docir.modules.documents.application.services.index_rebuilder import (
    IndexRebuilder,
    ReindexResult,
)
from docir.modules.documents.application.services.store_repairer import (
    RepairAction,
    StoreRepairer,
)
from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.schema import Schema
from docir.modules.documents.domain.services import schema_shape
from docir.modules.documents.domain.services.graph_checks import CheckIssue, GraphChecker
from docir.modules.documents.domain.services.similarity_lint import LintFinding, SimilarityLinter
from docir.modules.documents.domain.services.store_format import (
    FORMAT_FEATURES,
    STORE_FORMAT,
    declared_store_format,
    required_store_format,
)
from docir.modules.indexing.api import DrainResult, EmbeddingScheduler
from docir.platform.clock import Clock
from docir.platform.embedding import Embedder
from docir.platform.filesystem.ports import (
    CodeMatcher,
    DocumentFileStore,
    FileHistory,
    TagFileStore,
)
from docir.platform.filesystem.schema_store import YamlSchemaFileStore
from docir.platform.persistence.unit_of_work import UnitOfWork

UnitOfWorkFactory = Callable[[], UnitOfWork]


def index_is_empty(*, documents: int, documents_on_disk: int) -> bool:
    """Whether the index holds nothing while the files hold documents.

    One function because two reporters answer with it and must not disagree:
    `check` raises it as an `empty-index` error, and `docir doctor` reads the
    same pair out of :class:`StoreStatus`. Two copies of a two-term comparison
    is exactly the drift `validation.is_absent` exists to prevent, one size
    down.

    An empty *store* — freshly ``docir init``-ed, nothing written yet — has no
    files either, so the two agree at zero and this is ``False``. The condition
    is specifically "there are documents and the projection of them is blank".
    """
    return documents == 0 and documents_on_disk > 0


@dataclass(frozen=True, slots=True)
class StoreStatus:
    """What the derived index says about itself — the store half of ``docir doctor``.

    Facts, not advice: every field is something only the index can answer, and
    the judgement about what it means is made by the caller that also knows the
    process it is running in. The one exception is ``stale_index_build``, which
    is a judgement already implemented once
    (:meth:`MaintenanceService.stale_index_build`) and would otherwise be
    implemented a second time by whoever compared the two version strings.

    Deliberately says nothing about the corpus. ``docir check`` owns that
    question and answers it with a full graph scan; this one has to stay cheap
    enough that the command reporting a broken environment is not itself the
    slow part of the diagnosis.
    """

    #: Documents in the index. Counted in SQL, not hydrated.
    documents: int
    #: Source files under ``docs/``, counted without parsing them. The pair is
    #: the point: the index is a projection of these files, so a difference is
    #: the "reads are answering from stale state" condition stated as a number.
    #: A file that will not parse counts here and not in ``documents``, which is
    #: correct — the index does not hold it either.
    documents_on_disk: int
    #: The docir running this process, so a caller can report the pair without
    #: having to know the version itself.
    version: str
    #: The version that built this index, when it is not the running one.
    #: ``None`` covers both "built by this docir" and "never recorded" — absent
    #: means unknown, the rule the schema baseline follows.
    stale_index_build: str | None
    #: How the active schema differs from the one the index was built against,
    #: one line per change. Empty means nothing moved *or* nothing to compare.
    schema_drift: tuple[str, ...]
    #: The ``model_id`` this store's reads would score with, resolved rather
    #: than configured: it is the embedder that was actually built.
    embedding_model: str
    #: Documents with no current vector for that model. A leftover
    #: ``DOCIR_EMBEDDER`` shows up here as the whole corpus, because a vector
    #: made by another model reads as dirty rather than as a rival answer.
    embeddings_pending: int
    #: The floor this store's schema records, the floor its contents need, and
    #: the highest this build reads. The three numbers that answer "can another
    #: docir read this store" without running the experiment — here rather than
    #: only in `docir doctor`, because the reader over MCP is an agent and
    #: `doctor` has no tool (adr-6d4d43d44075). Defaults keep every existing
    #: construction of this DTO valid.
    store_format_declared: int = 1
    store_format_required: int = 1
    store_format_supported: int = STORE_FORMAT


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
        history: FileHistory | None = None,
        schema_file_store: YamlSchemaFileStore | None = None,
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
        self._history = history
        #: The schema *file*, where :attr:`_schema` is the resolved result of
        #: merging it with the package's. Only the file records a format floor,
        #: and only the file can be told to record one. ``None`` leaves both the
        #: finding and the repair silent.
        self._schema_file_store = schema_file_store
        self._prefixes = schema.prefixes()
        self._graph_checker = GraphChecker(schema)
        self._linter = SimilarityLinter()
        self._rebuilder = IndexRebuilder(
            uow_factory, file_store, tag_file_store, scheduler, schema, version
        )
        self._repairer = StoreRepairer(
            uow_factory,
            file_store,
            schema,
            self._rebuilder,
            clock,
            code_matcher,
            schema_file_store,
            history,
        )

    def reindex(self, *, changed_only: bool = False) -> ReindexResult:
        """Rebuild the index from the canonical files (``docir reindex``)."""
        return self._rebuilder.reindex(changed_only=changed_only)

    def bootstrap(self) -> ReindexResult:
        """Rebuild the index, leaving the vectors to the queue."""
        return self._rebuilder.bootstrap()

    def resync(self) -> ReindexResult:
        """Rebuild only what the build stamp says is not already indexed."""
        return self._rebuilder.resync()

    def flush_embeddings(self) -> DrainResult:
        """Synchronously drain the embedding queue (``docir embed --flush``).

        Returns both counts rather than the document one alone: the caller is
        reporting to a human who has just waited for it, and what they waited
        for was the vectors.
        """
        return self._scheduler.flush()

    def check(self, against: str | None = None) -> list[CheckIssue]:
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

        ``against`` guards it **before** the merge instead of after. The
        collision exists from the moment the second branch allocates — the ids
        are on both sides — but nothing could see it until both documents were
        in one tree, which is the point at which renumbering stopped being the
        branch's own cheap edit and became a conflict for whoever merged second
        (adr-df43aff8bb0d).
        """
        with self._uow_factory() as uow:
            documents = uow.documents.all()
            relations = uow.documents.relations()
            known_tags = frozenset(tag.key for tag in uow.tags.all())
        issues = self._graph_checker.check(
            documents,
            relations,
            self._clock.today(),
            known_tags=known_tags,
            code_matches=self._resolve_code(documents),
            code_digests=self._resolve_code_digests(documents),
        )
        issues.extend(self._unbuilt_index_issue())
        issues.extend(self._find_duplicate_ids())
        issues.extend(self._find_branch_id_collisions(against))
        issues.extend(self._find_malformed())
        issues.extend(self._drift_issues())
        issues.extend(self._format_issues())
        issues.extend(self._build_issues())
        return issues

    def _unbuilt_index_issue(self) -> list[CheckIssue]:
        """The finding that says this check could not look.

        Every structural check above reads the index; the index is derived and
        gitignored, so a fresh clone has none and they are all silent. That made
        `check --strict` a merge gate which passed by reading nothing — green on
        a corpus with sixteen dangling edges (issue-87410666c867).

        An **error**, unlike every other finding about derived state, and the
        distinction is the point: `stale-index-build` and `schema-drift` describe
        an index that is behind, which still answers. This one describes an index
        that answers nothing, so the report above it is not a weaker verdict but
        no verdict at all.

        Deliberately narrow. It compares against the files, so an empty store is
        silent, and a partially-behind index is left to `docir doctor` — a single
        unparseable file must not fail a build twice.
        """
        with self._uow_factory() as uow:
            documents = uow.documents.count()
        on_disk = self._file_store.count()
        if not index_is_empty(documents=documents, documents_on_disk=on_disk):
            return []
        return [
            CheckIssue(
                kind="empty-index",
                message=(
                    f"the index holds nothing while docs/ holds {on_disk} file(s), so every "
                    "structural check below read an empty graph — run `docir reindex` first "
                    "(the index is derived and gitignored, so a fresh clone has none)"
                ),
                doc_ids=(),
            )
        ]

    def store_status(self) -> StoreStatus:
        """The derived index's account of itself (the store half of ``docir doctor``).

        One round trip for facts that were each reachable and none of which
        were reportable together: the build stamp was a `check` finding buried
        among the corpus ones, the drift had its own command, and the embedding
        queue had no reader at all — `embed --flush` drains it without ever
        saying how long it was.

        Cheap on purpose. It counts documents in SQL and asks the queue for its
        ids; it does not hydrate the corpus, scan the files or walk the graph.
        A diagnosis command that costs what `check` costs is one nobody runs
        while something is actually wrong.
        """
        with self._uow_factory() as uow:
            documents = uow.documents.count()
            pending = len(uow.embeddings.dirty_ids(self._embedder.model_id))
        declared, required = self._store_format()
        return StoreStatus(
            documents=documents,
            documents_on_disk=self._file_store.count(),
            version=self._version,
            store_format_declared=declared,
            store_format_required=required,
            store_format_supported=STORE_FORMAT,
            stale_index_build=self.stale_index_build(),
            schema_drift=tuple(self.schema_drift()),
            embedding_model=self._embedder.model_id,
            embeddings_pending=pending,
        )

    def _store_format(self) -> tuple[int, int]:
        """``(declared, required)`` for the schema file, or ``(1, 1)`` with none.

        A store with no schema file to read is at the oldest format by the same
        rule the declaration follows: absent means every build can read it, not
        that the answer is unknown.
        """
        if self._schema_file_store is None:
            return 1, 1
        raw = self._schema_file_store.read_raw()
        return declared_store_format(raw), required_store_format(raw)

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

    def _format_issues(self) -> list[CheckIssue]:
        """Report a schema that needs a newer docir than it admits to.

        The declaration is the half that goes missing. A store gains a construct
        an older build cannot parse and the line saying so is written by whoever
        remembers — which is why this derives the answer from the file's own
        contents and compares, rather than trusting what is written there.

        The damage it predicts never lands here. This build reads the file
        perfectly; the reader who cannot is a teammate on an older docir, or a
        repository declaring this one a peer, and neither is present to complain.
        That is the whole argument for reporting it at all — nothing else in this
        corpus can notice, and adr-ab4598c6f707's cross-version run is a manual
        act somebody has to remember to perform (issue-c30895cc62a3).

        Silent when the store has no schema file, or one that will not parse:
        both are somebody else's finding, and neither is evidence about formats.
        """
        if self._schema_file_store is None:
            return []
        raw = self._schema_file_store.read_raw()
        declared = declared_store_format(raw)
        required = required_store_format(raw)
        if declared >= required:
            return []
        feature = FORMAT_FEATURES.get(required, f"a construct needing store format {required}")
        return [
            CheckIssue(
                kind="store-format-undeclared",
                message=(
                    f"{self._schema_file_store.path.name} uses {feature}, so it needs store "
                    f"format {required} and declares {declared} — a docir that predates it "
                    f"refuses this entire store with a parse error about a key nobody "
                    f"removed. Record it with `docir check --fix`"
                ),
                doc_ids=(),
            )
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
        """Fingerprint every glob some document holds evidence for.

        Evidence is either digest: ``verified_code`` (somebody read this) or
        ``code_baseline`` (the document declared this). A pattern carrying
        neither is still skipped — a fingerprint reads every file the pattern
        matches, where :meth:`_resolve_code` stops at the first hit, so hashing
        a whole subtree to compare it against nothing is the one cost worth
        refusing.

        Reading the baseline as well widens this from the verified globs to
        effectively all of them, and that is the cost the drift finding is
        bought with: before it, a glob nobody had verified was hashed by
        nothing and reported by nothing. Deduplicated across documents, so a
        pattern five decisions share is still one walk.

        Unresolvable patterns are dropped rather than stored as a sentinel:
        absent is already the unknown answer the check skips.
        """
        if self._code_matcher is None:
            return None
        evidenced = {
            pattern
            for document in documents
            if not document.archived
            for pattern in document.code
            if pattern in document.verified_code or pattern in document.code_baseline
        }
        digests = {}
        for pattern in sorted(evidenced):
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

    def _find_branch_id_collisions(self, against: str | None) -> list[CheckIssue]:
        """Ids this branch allocated that a base ref already uses.

        Only files **new on this branch** are compared. A document present at
        the ref keeps its id there and here, edited or not, and reporting it
        would make the check fire on every branch that touches a document.
        What is left is exactly the allocation question: this branch minted an
        id, and so did the other side.

        The finding names the repair, and the repair is **not** a renumber
        command, because there is none: an id is a document's only address and
        no write re-mints one. It is to merge the base into this branch and run
        `check --fix`, which then sees both files and re-issues the *newer* —
        this branch's, since the base's was committed first (adr-39210c34551a).
        Same repair either way; doing it here is what keeps it off `main` and
        out of the way of whoever merges next.

        Two answers are errors here, and neither red-builds anything that did
        not opt in — both exist only when a ref is named:

        * a collision, because the whole point of naming a ref is to fail
          before the merge that makes it real;
        * **a ref that could not be read**, because a pre-merge gate silent for
          that reason is indistinguishable from a clean branch, which is the
          `empty-index` argument arriving on the other side of the merge.

        The ids at the ref come from that side's *file contents*, and so do
        ours — the filename begins with the id but a prefix carrying a ``-``
        makes it ambiguous, and a hand-edited file can disagree with its own
        name.
        """
        if against is None:
            return []
        if self._history is None:
            return [
                CheckIssue(
                    kind="unreadable-ref",
                    message=(
                        f"cannot compare against {against!r}: this store has no repository "
                        f"above it, so there is no history to read — run the check from a "
                        f"project store created by `docir init` inside a checkout"
                    ),
                    doc_ids=(),
                )
            ]
        theirs = self._history.ids_at(against)
        if theirs is None:
            return [
                CheckIssue(
                    kind="unreadable-ref",
                    message=(
                        f"cannot read {against!r} — unknown ref, or a clone whose history "
                        f"does not reach it; fetch it first (`git fetch origin main`). "
                        f"Reporting nothing here would look exactly like a clean branch"
                    ),
                    doc_ids=(),
                )
            ]
        issues: list[CheckIssue] = []
        for document in sorted(self._file_store.scan(), key=lambda doc: doc.id):
            path = document.path or ""
            if path in theirs.values():
                continue
            other = theirs.get(document.id)
            if other is None:
                continue
            issues.append(
                CheckIssue(
                    kind="branch-id-collision",
                    message=(
                        f"{document.id!r} is new on this branch ({path}) and {against} "
                        f"already uses it ({other}); bring the base in and repair it here "
                        f"— `git merge {against}` then `docir check --fix`, which renumbers "
                        f"yours because theirs was committed first"
                    ),
                    doc_ids=(document.id,),
                )
            )
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
        actions = self._repairer.repair()
        return RepairResult(actions=tuple(actions), remaining=tuple(self.check()))

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
