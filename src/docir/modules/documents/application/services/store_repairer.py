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

from docir.modules.documents.application.services.document_saving import save_with_mentions
from docir.modules.documents.application.services.id_generator import IdGenerator
from docir.modules.documents.application.services.index_rebuilder import IndexRebuilder
from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.schema import Schema
from docir.platform.filesystem.ports import DocumentFileStore
from docir.platform.persistence.unit_of_work import UnitOfWork

UnitOfWorkFactory = Callable[[], UnitOfWork]


@dataclass(frozen=True, slots=True)
class RepairAction:
    """One repair that was applied, in the caller's terms."""

    kind: str  # the finding kind repaired: duplicate-id | dangling
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
    ) -> None:
        self._uow_factory = uow_factory
        self._file_store = file_store
        self._schema = schema
        self._rebuilder = rebuilder
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
