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


class TagFileStore(ABC):
    """Reads and writes the canonical ``tags.yaml`` registry file."""

    @abstractmethod
    def load(self) -> list[Tag]:
        """Return every tag defined in ``tags.yaml`` (empty if absent)."""

    @abstractmethod
    def write(self, tags: list[Tag]) -> None:
        """Persist the full tag registry back to ``tags.yaml``."""
