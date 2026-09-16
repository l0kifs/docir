"""Repairing the Tier 1 damage that needs no guess.

``docir check --fix`` and nothing else. Split out of :class:`MaintenanceService`
so that deciding *what* is broken and mechanically *fixing* it stop sharing a
class — they are read against different risks, and only one of them writes.

What it will not touch is the point: a ``malformed`` file needs somebody to read
it and say what it was meant to be, and an ``unknown-type`` needs a schema
decision. A repair has nothing to read those with, so both are left for
:meth:`MaintenanceService.check` to report.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from docir.modules.documents.application.services.code_evidence import mint_baseline
from docir.modules.documents.application.services.document_saving import save_with_mentions
from docir.modules.documents.application.services.id_generator import IdGenerator
from docir.modules.documents.application.services.index_rebuilder import IndexRebuilder
from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.schema import Schema
from docir.modules.documents.domain.services.store_format import (
    declared_store_format,
    required_store_format,
)
from docir.platform.filesystem.ports import CodeMatcher, DocumentFileStore
from docir.platform.filesystem.schema_store import YamlSchemaFileStore
from docir.platform.persistence.unit_of_work import UnitOfWork

UnitOfWorkFactory = Callable[[], UnitOfWork]


@dataclass(frozen=True, slots=True)
class RepairAction:
    """One repair that was applied, in the caller's terms."""

    # The finding kind repaired — `duplicate-id`, `dangling`,
    # `store-format-undeclared` — or, for the one action that repairs nothing,
    # what it filed: `code-baseline`. Deliberately not `code-drifted` there:
    # that action enables the finding rather than clearing it, and an action
    # naming a finding it did not repair reads as the opposite.
    kind: str
    message: str
    doc_ids: tuple[str, ...]


class StoreRepairer:
    """Applies the two repairs that need no judgement, and reports what it did."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        file_store: DocumentFileStore,
        schema: Schema,
        rebuilder: IndexRebuilder,
        code_matcher: CodeMatcher | None = None,
        schema_file_store: YamlSchemaFileStore | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._file_store = file_store
        self._schema = schema
        self._rebuilder = rebuilder
        # Optional at the seam for the reason it is optional everywhere else: a
        # global store has no repository above it, so there is no tree to
        # fingerprint and nothing to start watching.
        self._code_matcher = code_matcher
        self._schema_file_store = schema_file_store
        self._prefixes = schema.prefixes()

    def repair(self) -> list[RepairAction]:
        """Re-issue duplicate ids and drop dead edges, rebuilding around both.

        Returns only what it changed. Whether anything is *left* wrong is a
        question for the checker, and :meth:`MaintenanceService.repair` asks it.
        """
        # Repair reads the files as the source of truth, so bring the index in
        # line first: id allocation consults it to find a free number. Both
        # passes are `--changed`, because agreeing with the files is all either
        # one is for: the deletion sweep and `_restore_id_sequences` run in that
        # mode too (the id allocator sees every id on disk either way), and what
        # it skips is re-saving — and so re-embedding — documents that did not
        # move. A re-issued file's hash changes with its id, so the second pass
        # still picks up everything `_repair_duplicate_ids` rewrote.
        self._rebuilder.reindex(changed_only=True)
        actions = self._repair_duplicate_ids()
        if actions:
            self._rebuilder.reindex(changed_only=True)
        actions.extend(self._repair_dangling())
        actions.extend(self._mint_code_baselines())
        actions.extend(self._record_store_format())
        return actions

    def _record_store_format(self) -> list[RepairAction]:
        """Write the format floor the schema file's contents already need.

        The fourth repair, and the second that mends nothing here: this store
        reads perfectly on this build, and the line exists for a docir that
        predates its schema — a teammate's, or one reading this repository as a
        peer (issue-c30895cc62a3).

        It qualifies on the two tests `--fix` applies. The value needs no guess:
        it is derived from the constructs the file uses, by the same function the
        finding compares against, so there is exactly one answer. And it claims
        nothing anybody has to judge — a floor is a fact about what the file
        contains, not a preference about what it should.

        Only ever raised. A declaration *above* what the contents need is left
        alone: somebody may have written it deliberately, ahead of a change they
        are about to make, and a repair that lowers a floor takes away a
        protection to tidy a number.
        """
        if self._schema_file_store is None:
            return []
        raw = self._schema_file_store.read_raw()
        declared = declared_store_format(raw)
        required = required_store_format(raw)
        if declared >= required:
            return []
        if not self._schema_file_store.record_store_format(required):
            return []
        return [
            RepairAction(
                kind="store-format-undeclared",
                message=(
                    f"recorded `store_format: {required}` in "
                    f"{self._schema_file_store.path.name} — a docir that predates it now "
                    f"refuses this store by name instead of failing on a key"
                ),
                doc_ids=(),
            )
        ]

    def _mint_code_baselines(self) -> list[RepairAction]:
        """Start watching the globs a document declared before baselines existed.

        The third repair, and the one that is not repairing damage: a document
        with a ``code:`` glob and no baseline is intact, resolves, and reports
        nothing — which is exactly the problem. It was written by a build that
        minted no baseline, so its globs watch nothing until somebody verifies
        it, and in this project's own store not one of the 99 ever had.

        It belongs here on the two tests `--fix` applies. It needs no guess —
        the tree in front of it is the only answer a baseline can have — and it
        claims nothing anybody has to judge: a baseline says *this is what the
        tree held when we started watching*, never *somebody read this*. That is
        the line `check --fix` may not cross, and the reason it still cannot
        touch ``verified_code``.

        What it cannot do is recover the drift that already happened. A document
        whose code moved last month is based on the tree as it stands now and
        reports nothing about the month it missed; the finding starts at the
        next change. Saying so is the point of returning an action per document
        rather than doing this silently — the frontmatter of every governed
        document moves, and the reader has to see that in the diff.

        Only documents that gain an entry are rewritten, so a second run is a
        no-op, and ``updated`` is left alone for the reason `_repair_dangling`
        leaves it alone: filing evidence is not a review.
        """
        if self._code_matcher is None:
            return []
        actions: list[RepairAction] = []
        with self._uow_factory() as uow:
            for document in uow.documents.all():
                if not document.code:
                    continue
                baseline = mint_baseline(self._code_matcher, document.code, document.code_baseline)
                if baseline == dict(document.code_baseline):
                    continue
                minted = sorted(set(baseline) - set(document.code_baseline))
                based = document.with_updates(code_baseline=baseline)
                self._file_store.write(based)
                save_with_mentions(uow, based, self._prefixes)
                uow.search.index(based)
                actions.append(
                    RepairAction(
                        kind="code-baseline",
                        message=(
                            f"started watching {len(minted)} glob(s) on {document.id!r}: "
                            f"{', '.join(minted)} — drift is reported from now, not "
                            f"from when they were declared"
                        ),
                        doc_ids=(document.id,),
                    )
                )
            uow.commit()
        return actions

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
                save_with_mentions(uow, repaired, self._prefixes)
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
