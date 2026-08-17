"""Ports for the filesystem source of truth.

Git-versioned markdown files (and ``tags.yaml``) are canonical; the index is
derived from them. These ports abstract reading and writing those files so the
use cases stay ignorant of paths, YAML, and frontmatter encoding.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from docir.modules.documents.domain.entities.document import Document
from docir.modules.tags.domain.entities.tag import Tag


class DocumentFileStore(ABC):
    """Reads and writes the canonical ``docs/<type>s/<id>-<slug>.md`` files."""

    @abstractmethod
    def write(self, document: Document, *, create: bool = False) -> str:
        """Write the document to disk, returning its path relative to the root.

        The path is ``<type>s/<id>-<slug>.md``. Overwrites in place when the
        document already exists. Pass ``create=True`` for a first write, which
        refuses to overwrite a file that is already there — a freshly allocated
        id whose file exists means the id is not actually free, and silently
        clobbering it would drop the existing document from every read path.
        """

    @abstractmethod
    def relocate(self, document: Document, *, from_path: str) -> str:
        """Write the document under its (new) type's directory, dropping ``from_path``.

        The paired write for a retype. A document's path is fixed at creation
        and reused forever, so changing the type alone would leave the file in
        the old type's directory — the layout would say one thing and the
        frontmatter another, on every document a rename touched.

        The *filename* is carried over rather than rebuilt: it encodes the id
        and the title slug at creation, and a retype is not a retitle, so
        reslugging here would bury the directory move in a rename git cannot
        follow.
        """

    @abstractmethod
    def read(self, path: str) -> Document:
        """Parse a single markdown file (relative path) into a Document."""

    @abstractmethod
    def delete(self, path: str) -> None:
        """Remove a document's markdown file from disk."""

    @abstractmethod
    def scan(self) -> Iterator[Document]:
        """Yield every document found under the docs root (for reindex).

        Implementations skip files that do not parse; use :meth:`find_malformed`
        to surface those.
        """

    def find_malformed(self) -> list[tuple[str, str]]:
        """Return ``(path, reason)`` for source files that fail to parse.

        Defaults to none; a real store overrides this to report hand-edited or
        foreign files that ``scan`` skipped.
        """
        return []


class CodeMatcher(ABC):
    """Resolves a document's ``code`` globs against a working tree.

    A port of its own rather than a method on the document store: the globs are
    written against the *repository*, which is the store's parent, and a store
    with no repository above it (the global ``~/.docir``) has nothing to resolve
    them against — the composition root then supplies no matcher at all, and the
    check that reads one is skipped rather than reporting every pattern missing.
    """

    @abstractmethod
    def matches(self, pattern: str) -> bool:
        """Whether ``pattern`` matches at least one path in the tree."""

    @abstractmethod
    def fingerprint(self, pattern: str) -> str | None:
        """A digest of the files ``pattern`` matches, or ``None`` if unresolvable.

        Stamped into a document's frontmatter when a human verifies it, and
        recomputed by `check` to answer the question the review cadence cannot:
        *has the code this document governs moved since somebody last read it?*

        ``None`` is the unknown answer — the pattern matches nothing, or the
        tree refused to be read — and it is deliberately distinct from a digest
        over an empty set. Absent means unknown everywhere in this codebase, and
        a document verified against nothing must not later read as unchanged.
        """


class TagFileStore(ABC):
    """Reads and writes the canonical ``tags.yaml`` registry file."""

    @abstractmethod
    def load(self) -> list[Tag]:
        """Return every tag defined in ``tags.yaml`` (empty if absent)."""

    @abstractmethod
    def write(self, tags: list[Tag]) -> None:
        """Persist the full tag registry back to ``tags.yaml``."""
