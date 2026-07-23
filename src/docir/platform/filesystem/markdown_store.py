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
import yaml

from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.services.slugify import slugify
from docir.modules.documents.domain.value_objects.relations import (
    DEFAULT_RELATION_KIND,
    RelatedRef,
)
from docir.platform.errors import DocumentNotFoundError, ValidationError
from docir.platform.filesystem.ports import DocumentFileStore


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
        return self._parse(full_path, path)

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
                yield self._parse(full_path, rel)
            except ValidationError:
                continue

    def find_malformed(self) -> list[tuple[str, str]]:
        """Return ``(path, reason)`` for every ``.md`` file that fails to parse."""
        malformed: list[tuple[str, str]] = []
        if not self._root.exists():
            return malformed
        for full_path in sorted(self._root.rglob("*.md")):
            rel = str(full_path.relative_to(self._root))
            try:
                self._parse(full_path, rel)
            except ValidationError as exc:
                malformed.append((rel, str(exc)))
        return malformed

    # -- rendering / parsing ------------------------------------------------

    def _parse(self, full_path: Path, rel: str) -> Document:
        """Parse a file into a Document, or raise ValidationError naming it."""
        try:
            post = frontmatter.loads(full_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ValidationError(f"malformed frontmatter in {rel}: {exc}") from exc
        return self._to_document(post.metadata, post.content, rel)

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
            "related": _render_related(document.related),
            "created": document.created.isoformat(),
            "updated": document.updated.isoformat(),
        }
        if document.archived:
            metadata["archived"] = True
        # Stewardship metadata is written only when set, so untyped/unowned docs
        # keep a minimal, clean frontmatter block.
        if document.owner:
            metadata["owner"] = document.owner
        if document.verified is not None:
            metadata["verified"] = document.verified.isoformat()
        post = frontmatter.Post(content=document.body)
        post.metadata.update(metadata)
        return frontmatter.dumps(post) + "\n"

    def _to_document(self, metadata: dict[str, object], body: str, path: str) -> Document:
        try:
            verified_raw = metadata.get("verified")
            return Document(
                id=str(metadata["id"]),
                title=str(metadata["title"]),
                description=str(metadata.get("description", "")),
                type=str(metadata["type"]),
                status=str(metadata["status"]),
                created=_as_date(metadata["created"]),
                updated=_as_date(metadata["updated"]),
                tags=_as_str_tuple(metadata.get("tags")),
                related=_as_related_tuple(metadata.get("related")),
                archived=bool(metadata.get("archived", False)),
                body=body,
                path=path,
                owner=str(metadata.get("owner", "")),
                verified=None if verified_raw is None else _as_date(verified_raw),
            )
        except (KeyError, ValueError) as exc:
            # KeyError: a required field is absent. ValueError: a field is present
            # but unparseable (e.g. a ``created``/``updated`` that is not an ISO date).
            raise ValidationError(f"malformed frontmatter in {path}: {exc}") from exc


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


def _render_related(related: tuple[RelatedRef, ...]) -> list[object]:
    """Serialize edges: a bare id for the default kind, a mapping otherwise.

    Default-kind edges stay bare strings so documents authored before typed
    edges (``related: [adr-0001]``) round-trip byte-for-byte.
    """
    rendered: list[object] = []
    for ref in related:
        if ref.kind == DEFAULT_RELATION_KIND:
            rendered.append(ref.target)
        else:
            rendered.append({"to": ref.target, "kind": ref.kind})
    return rendered


def _as_related_tuple(value: object) -> tuple[RelatedRef, ...]:
    """Parse the ``related`` frontmatter (bare ids and/or ``{to, kind}`` maps)."""
    if not isinstance(value, list | tuple):
        return ()
    refs: list[RelatedRef] = []
    for item in value:
        if isinstance(item, dict):
            target = str(item.get("to", "")).strip()
            if not target:
                raise ValueError(f"related entry {item!r} is missing a 'to' id")
            kind = str(item.get("kind", DEFAULT_RELATION_KIND)).strip() or DEFAULT_RELATION_KIND
            refs.append(RelatedRef(target=target, kind=kind))
        else:
            refs.append(RelatedRef(target=str(item).strip()))
    return tuple(refs)
