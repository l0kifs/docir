"""The :class:`Document` aggregate.

A document is the union of its YAML frontmatter (structured, indexed metadata)
and its markdown body (free-form natural language). The markdown file on disk
is the source of truth; this entity is the in-memory representation the use
cases manipulate before persisting back to the file and the index.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from datetime import date

from docir.modules.documents.domain.value_objects.relations import RelatedRef


@dataclass
class Document:
    """A single indexed markdown document."""

    id: str
    title: str
    description: str
    type: str
    status: str
    created: date
    updated: date
    tags: tuple[str, ...] = ()
    related: tuple[RelatedRef, ...] = ()
    archived: bool = False
    body: str = ""
    # Filesystem path relative to the docs root; ``None`` before persistence.
    path: str | None = field(default=None)
    # Optional stewardship metadata (staleness). ``owner`` is a free-form name;
    # ``verified`` is the date a human last re-confirmed the doc is still true.
    owner: str = ""
    verified: date | None = None

    def embedding_text(self) -> str:
        """The text embedded for semantic search: title + description + body.

        The agent-authored ``description`` gives the vector a concise,
        high-signal summary to anchor on, improving retrieval over embedding
        raw body text alone.
        """
        return f"{self.title}\n\n{self.description}\n\n{self.body}".strip()

    def content_hash(self) -> str:
        """A stable hash over the content that matters for stale-write checks.

        Covers every field a write could change; used to detect that the file
        was modified out-of-band since the caller last fetched it.
        """
        parts = [
            self.title,
            self.description,
            self.type,
            self.status,
            # Sorted so tag/relation ordering (which differs between the file's
            # insertion order and the index's sorted order) never affects the
            # hash — only genuine content changes do.
            ",".join(sorted(self.tags)),
            ",".join(sorted(f"{ref.kind}:{ref.target}" for ref in self.related)),
            str(self.archived),
            self.owner,
            "" if self.verified is None else self.verified.isoformat(),
            self.body.strip("\n"),
        ]
        digest = hashlib.sha256("\x1f".join(parts).encode("utf-8"))
        return digest.hexdigest()

    def stale_reference_date(self) -> date:
        """The date staleness is measured from: last verification, else last edit."""
        return self.verified or self.updated

    def related_targets(self) -> tuple[str, ...]:
        """Just the target ids of the outgoing edges (kind-agnostic)."""
        return tuple(ref.target for ref in self.related)

    def with_updates(self, **changes: object) -> Document:
        """Return a copy with the given fields replaced (frontmatter patch)."""
        return replace(self, **changes)  # type: ignore[arg-type]
