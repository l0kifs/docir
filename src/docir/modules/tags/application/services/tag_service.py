"""The tag-registry use cases (``docs tag ...``).

The registry is the source of truth for what tags exist. ``rename`` and a
forced ``rm`` are not just registry edits: because a tag is a classifier rather
than a link, the CLI rewrites the ``tags`` list of every referencing document
(and reindexes it) as part of the same atomic operation, so no broken keys are
left behind.
"""

from __future__ import annotations

from collections.abc import Callable

from docir.modules.tags.application.dto import TagView
from docir.modules.tags.domain.entities.tag import Tag
from docir.platform.errors import (
    TagAlreadyExistsError,
    TagInUseError,
    TagNotFoundError,
)
from docir.platform.filesystem.ports import DocumentFileStore, TagFileStore
from docir.platform.persistence.unit_of_work import UnitOfWork

UnitOfWorkFactory = Callable[[], UnitOfWork]


class TagService:
    """Use cases for the tag registry."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        tag_file_store: TagFileStore,
        file_store: DocumentFileStore,
    ) -> None:
        # No `Clock`: nothing here stamps a date. The tag operations rewrite a
        # document's classification and deliberately leave `updated` alone, so
        # the only reason this service ever held a clock is gone with it.
        self._uow_factory = uow_factory
        self._tag_file_store = tag_file_store
        self._file_store = file_store

    def add(self, key: str, description: str) -> TagView:
        """Register a new tag (``docs tag add``)."""
        with self._uow_factory() as uow:
            if uow.tags.exists(key):
                raise TagAlreadyExistsError(f"tag {key!r} already exists")
            tag = Tag(key=key, description=description)
            uow.tags.save(tag)
            self._sync_file(uow)
            uow.commit()
        return TagView(key=tag.key, description=tag.description)

    def list_all(self) -> list[TagView]:
        """List every registered tag (``docs tag list``)."""
        with self._uow_factory() as uow:
            return [
                TagView(key=tag.key, description=tag.description)
                for tag in sorted(uow.tags.all(), key=lambda t: t.key)
            ]

    def rename(self, old: str, new: str, *, merge: bool = False) -> tuple[str, ...]:
        """Rename a tag across the registry and all documents (``docs tag rename``).

        With ``merge``, ``new`` may already exist: every document carrying
        ``old`` gets ``new`` instead, and ``old`` leaves the registry. Without
        it, renaming onto an existing key is still refused — a merge discards
        one of the two descriptions and is not what someone fixing a typo means.
        Consolidating two tags previously had no path at all: `tag rm --force`
        threw the classification away and you re-tagged by hand.

        Returns the ids of the documents rewritten, so a bulk edit says what it
        touched rather than reporting a bare success.

        Those documents keep their `updated` date. Staleness falls back to
        `updated` when a document has no explicit `verified`, so bumping it here
        would make every document carrying the tag report as freshly reviewed —
        a bulk administrative edit silently forging the one trust signal the
        product offers. Same reasoning as `check --fix` and `delete --force`:
        a mechanical rewrite is not a human re-verification.
        """
        with self._uow_factory() as uow:
            tag = uow.tags.get(old)
            if tag is None:
                raise TagNotFoundError(f"no tag {old!r}")
            target = uow.tags.get(new)
            if target is not None and not merge:
                raise TagAlreadyExistsError(
                    f"tag {new!r} already exists; pass --merge to fold {old!r} into it "
                    f"(the description of {new!r} is kept)"
                )

            # A merge keeps the surviving tag's own description: `new` is the
            # one being kept, so its wording is the one people chose for it.
            if target is None:
                uow.tags.save(Tag(key=new, description=tag.description))
            uow.tags.delete(old)

            rewritten: list[str] = []
            for document in uow.documents.all():
                if old not in document.tags:
                    continue
                # dict.fromkeys dedupes while preserving order: a document
                # carrying BOTH tags must end up with one `new`, not two.
                new_tags = tuple(dict.fromkeys(new if t == old else t for t in document.tags))
                updated = document.with_updates(tags=new_tags)
                self._file_store.write(updated)
                uow.documents.save(updated)
                uow.search.index(updated)
                rewritten.append(document.id)
            self._sync_file(uow)
            uow.commit()
        return tuple(rewritten)

    def remove(self, key: str, *, force: bool = False) -> tuple[str, ...]:
        """Remove a tag (``docs tag rm``); blocked while in use unless forced.

        Returns the ids of the documents it stripped the tag from. A forced
        removal rewrites other people's files, and reporting only ``removed
        <key>`` said nothing about that — the same reason `delete --force` and
        `tag rename --merge` name what they touched.

        As with `rename`, stripping the tag does not advance the referencing
        documents' `updated` — see that docstring for why.
        """
        with self._uow_factory() as uow:
            if uow.tags.get(key) is None:
                raise TagNotFoundError(f"no tag {key!r}")
            referencing = [d for d in uow.documents.all() if key in d.tags]
            if referencing and not force:
                joined = ", ".join(sorted(d.id for d in referencing))
                raise TagInUseError(
                    f"tag {key!r} is still used by {joined} "
                    f"(use --force to strip it from those documents)"
                )
            for document in referencing:
                new_tags = tuple(t for t in document.tags if t != key)
                updated = document.with_updates(tags=new_tags)
                self._file_store.write(updated)
                uow.documents.save(updated)
                uow.search.index(updated)
            uow.tags.delete(key)
            self._sync_file(uow)
            uow.commit()
        return tuple(sorted(d.id for d in referencing))

    def _sync_file(self, uow: UnitOfWork) -> None:
        """Rewrite ``tags.yaml`` from the current registry state."""
        self._tag_file_store.write(sorted(uow.tags.all(), key=lambda t: t.key))
