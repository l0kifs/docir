"""Markdown + frontmatter document store (implements ``DocumentFileStore``).

Each document is a single ``docs/<type>s/<id>-<slug>.md`` file: a YAML
frontmatter block (the indexed metadata) followed by the markdown body. The
file path is fixed at creation from the id and slug and reused on every
subsequent write, so editing a title never orphans a renamed file.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

import frontmatter

from docir.domain.entities.document import Document
from docir.domain.errors import DocumentNotFoundError, ValidationError
from docir.domain.ports.files import DocumentFileStore
from docir.domain.services.slugify import slugify


class MarkdownDocumentFileStore(DocumentFileStore):
    """Filesystem-backed document store rooted at the docs directory."""

    def __init__(self, docs_root: Path) -> None:
        self._root = docs_root

    def write(self, document: Document) -> str:
        rel_path = document.path or self._path_for(document)
        full_path = self._root / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(self._render(document), encoding="utf-8")
        return rel_path

    def read(self, path: str) -> Document:
        full_path = self._root / path
        if not full_path.exists():
            raise DocumentNotFoundError(f"file not found: {path}")
        post = frontmatter.loads(full_path.read_text(encoding="utf-8"))
        return self._to_document(post.metadata, post.content, path)

    def delete(self, path: str) -> None:
        full_path = self._root / path
        full_path.unlink(missing_ok=True)

    def scan(self) -> Iterator[Document]:
        if not self._root.exists():
            return
        for full_path in sorted(self._root.rglob("*.md")):
            rel = str(full_path.relative_to(self._root))
            post = frontmatter.loads(full_path.read_text(encoding="utf-8"))
            yield self._to_document(post.metadata, post.content, rel)

    # -- rendering / parsing ------------------------------------------------

    def _path_for(self, document: Document) -> str:
        slug = slugify(document.title)
        return f"{document.type}s/{document.id}-{slug}.md"

    def _render(self, document: Document) -> str:
        metadata: dict[str, object] = {
            "id": document.id,
            "title": document.title,
            "description": document.description,
            "type": document.type,
            "status": document.status,
            "tags": list(document.tags),
            "related": list(document.related),
            "created": document.created.isoformat(),
            "updated": document.updated.isoformat(),
        }
        if document.archived:
            metadata["archived"] = True
        post = frontmatter.Post(content=document.body)
        post.metadata.update(metadata)
        return frontmatter.dumps(post) + "\n"

    def _to_document(self, metadata: dict[str, object], body: str, path: str) -> Document:
        try:
            return Document(
                id=str(metadata["id"]),
                title=str(metadata["title"]),
                description=str(metadata.get("description", "")),
                type=str(metadata["type"]),
                status=str(metadata["status"]),
                created=_as_date(metadata["created"]),
                updated=_as_date(metadata["updated"]),
                tags=_as_str_tuple(metadata.get("tags")),
                related=_as_str_tuple(metadata.get("related")),
                archived=bool(metadata.get("archived", False)),
                body=body,
                path=path,
            )
        except KeyError as exc:
            raise ValidationError(f"malformed frontmatter in {path}: missing field {exc}") from exc


def _as_date(value: object) -> date:
    """Coerce a frontmatter date value (date or ISO string) to ``date``."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _as_str_tuple(value: object) -> tuple[str, ...]:
    """Coerce a frontmatter list value into a tuple of strings."""
    if isinstance(value, list | tuple):
        return tuple(str(item) for item in value)
    return ()
