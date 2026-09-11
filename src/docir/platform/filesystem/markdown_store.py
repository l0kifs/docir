"""Where a document's file goes (implements ``DocumentFileStore``).

Each document is a single ``docs/<type>s/<id>-<slug>.md`` file: a YAML
frontmatter block (the indexed metadata) followed by the markdown body. The
file path is fixed at creation from the id and slug and reused on every
subsequent write, so editing a title never orphans a renamed file. Changing the
*type* is the one edit that moves it (:meth:`~MarkdownDocumentFileStore.relocate`),
because the directory names the type.

What is *written* in the file is :mod:`markdown_format`. The two were one class
and changed for two unrelated reasons: the layout is this store's business and
local to a checkout, while the format is an interface against every installed
docir build that reads the same committed store.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from docir.modules.documents.domain.entities.document import Document
from docir.platform.errors import (
    DocumentNotFoundError,
    DuplicateDocumentIdError,
    ValidationError,
)
from docir.platform.filesystem import markdown_format
from docir.platform.filesystem.ports import DocumentFileStore
from docir.platform.naming.slug import slugify


class MarkdownDocumentFileStore(DocumentFileStore):
    """Filesystem-backed document store rooted at the docs directory."""

    def __init__(self, docs_root: Path) -> None:
        self._root = docs_root

    def write(self, document: Document, *, create: bool = False) -> str:
        rel_path = document.path or self._path_for(document)
        full_path = self._root / rel_path
        if create:
            # Key on the *id*, not the path: the filename carries the title slug,
            # so a colliding id under a different title lands on a different path
            # and would slip past an exists() check on ``full_path``.
            existing = self._existing_path_for_id(document)
            if existing is not None:
                raise DuplicateDocumentIdError(
                    f"cannot create {document.id!r}: {existing} already uses that id. "
                    f"The index's id counter is behind the files — run `docir reindex` "
                    f"to resync it, then retry."
                )
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(markdown_format.render(document), encoding="utf-8")
        return rel_path

    def relocate(self, document: Document, *, from_path: str) -> str:
        """Move the document into its type's directory, keeping its filename.

        Write-then-delete, in that order: a crash between the two leaves two
        files claiming one id, which `docir check` reports and `--fix` repairs.
        The reverse order can leave none, and the files are the source of truth.
        """
        rel_path = f"{document.type}s/{Path(from_path).name}"
        full_path = self._root / rel_path
        moving = rel_path != from_path
        if moving and full_path.exists():
            # Same guard as `create=True`, for the same reason: the filename
            # opens with the id, so something else already claims it there and
            # overwriting would drop that document from every read path.
            raise DuplicateDocumentIdError(
                f"cannot retype {document.id!r}: {rel_path} already exists. "
                f"Run `docir check` — two files claiming one id is a duplicate "
                f"the repair path can re-issue."
            )
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(markdown_format.render(document), encoding="utf-8")
        if moving:
            self.delete(from_path)
            self._prune_empty(self._root / from_path)
        return rel_path

    def _prune_empty(self, moved_from: Path) -> None:
        """Drop the vacated type directory once its last document has left it.

        Retyping a whole corpus otherwise leaves an empty ``decisions/`` behind,
        and a directory listing is how a person reads which types a store uses.
        ``rmdir`` refuses a non-empty directory, so this cannot take anything
        with it; the docs root itself is never a candidate.
        """
        parent = moved_from.parent
        if parent == self._root:
            return
        try:
            parent.rmdir()
        except OSError:
            return

    def read(self, path: str) -> Document:
        full_path = self._root / path
        if not full_path.exists():
            raise DocumentNotFoundError(f"file not found: {path}")
        return markdown_format.parse(full_path.read_text(encoding="utf-8"), path)

    def delete(self, path: str) -> None:
        full_path = self._root / path
        full_path.unlink(missing_ok=True)

    def scan(self) -> Iterator[Document]:
        # Bulk, best-effort: a single hand-edited/foreign file that does not
        # parse is skipped rather than aborting the whole scan (reindex, the
        # duplicate-id check). ``find_malformed`` surfaces those files instead.
        if not self._root.exists():
            return
        for full_path in sorted(self._root.rglob("*.md")):
            rel = str(full_path.relative_to(self._root))
            try:
                yield markdown_format.parse(full_path.read_text(encoding="utf-8"), rel)
            except ValidationError:
                continue

    def count(self) -> int:
        """Count the ``.md`` files under the root — the same glob ``scan`` walks."""
        if not self._root.exists():
            return 0
        return sum(1 for _ in self._root.rglob("*.md"))

    def find_malformed(self) -> list[tuple[str, str]]:
        """Return ``(path, reason)`` for every ``.md`` file that fails to parse."""
        malformed: list[tuple[str, str]] = []
        if not self._root.exists():
            return malformed
        for full_path in sorted(self._root.rglob("*.md")):
            rel = str(full_path.relative_to(self._root))
            try:
                markdown_format.parse(full_path.read_text(encoding="utf-8"), rel)
            except ValidationError as exc:
                malformed.append((rel, str(exc)))
        return malformed

    def _existing_path_for_id(self, document: Document) -> str | None:
        """The relative path of a file already claiming this id, if any.

        A narrow glob over the type's own directory, not a scan of the whole
        docs root — cheap enough to sit on the create path.
        """
        for match in sorted(self._root.glob(f"{document.type}s/{document.id}-*.md")):
            return str(match.relative_to(self._root))
        return None

    def _path_for(self, document: Document) -> str:
        slug = slugify(document.title)
        return f"{document.type}s/{document.id}-{slug}.md"
