"""The tag-registry use cases (``docs tag ...``).

The registry is the source of truth for what tags exist. ``rename`` and a
forced ``rm`` are not just registry edits: because a tag is a classifier rather
than a link, the CLI rewrites the ``tags`` list of every referencing document
(and reindexes it) as part of the same atomic operation, so no broken keys are
left behind.
"""

from __future__ import annotations

from collections.abc import Callable

from docir.application.dto import TagView
from docir.domain.entities.tag import Tag
from docir.domain.errors import (
    TagAlreadyExistsError,
    TagInUseError,
    TagNotFoundError,
)
from docir.domain.ports.clock import Clock
from docir.domain.ports.files import DocumentFileStore, TagFileStore
from docir.domain.ports.unit_of_work import UnitOfWork

UnitOfWorkFactory = Callable[[], UnitOfWork]


class TagService:
    """Use cases for the tag registry."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        tag_file_store: TagFileStore,
        file_store: DocumentFileStore,
        clock: Clock,
    ) -> None:
        self._uow_factory = uow_factory
        self._tag_file_store = tag_file_store
        self._file_store = file_store
        self._clock = clock

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

    def rename(self, old: str, new: str) -> None:
        """Rename a tag across the registry and all documents (``docs tag rename``)."""
        today = self._clock.today()
        with self._uow_factory() as uow:
            tag = uow.tags.get(old)
            if tag is None:
                raise TagNotFoundError(f"no tag {old!r}")
            if uow.tags.exists(new):
                raise TagAlreadyExistsError(f"tag {new!r} already exists")

            uow.tags.save(Tag(key=new, description=tag.description))
            uow.tags.delete(old)
            for document in uow.documents.all():
                if old in document.tags:
                    new_tags = tuple(new if t == old else t for t in document.tags)
                    updated = document.with_updates(tags=new_tags, updated=today)
                    self._file_store.write(updated)
                    uow.documents.save(updated)
                    uow.search.index(updated)
            self._sync_file(uow)
            uow.commit()

    def remove(self, key: str, *, force: bool = False) -> None:
        """Remove a tag (``docs tag rm``); blocked while in use unless forced."""
        today = self._clock.today()
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
                updated = document.with_updates(tags=new_tags, updated=today)
                self._file_store.write(updated)
                uow.documents.save(updated)
                uow.search.index(updated)
            uow.tags.delete(key)
            self._sync_file(uow)
            uow.commit()

    def _sync_file(self, uow: UnitOfWork) -> None:
        """Rewrite ``tags.yaml`` from the current registry state."""
        self._tag_file_store.write(sorted(uow.tags.all(), key=lambda t: t.key))
