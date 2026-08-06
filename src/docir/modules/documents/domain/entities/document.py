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

from docir.modules.documents.domain.services.chunking import EmbeddableChunk, split_body
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
    #: Repo-relative globs naming the code this document governs
    #: (issue-90aea6d1b891). Held as written, in the author's order: the
    #: patterns are matched against a working tree that is not this module's to
    #: read, so the entity carries them and judges nothing about them.
    code: tuple[str, ...] = ()

    def embedding_text(self) -> str:
        """The text embedded for semantic search: title + description + body.

        The agent-authored ``description`` gives the vector a concise,
        high-signal summary to anchor on, improving retrieval over embedding
        raw body text alone.
        """
        return f"{self.title}\n\n{self.description}\n\n{self.body}".strip()

    def embedding_chunks(self) -> tuple[EmbeddableChunk, ...]:
        """The per-section texts to embed alongside :meth:`embedding_text`.

        The entity owns this rather than the scheduler because the scheduler
        lives in ``indexing``, which may not depend on ``documents`` — the same
        reason ``embedding_text`` is a method here. Each chunk's text is
        prefixed with the title, so a section that never restates its subject
        ("Rotation is a runbook step") can still be matched by a query phrased
        in the document's terms.
        """
        return tuple(
            EmbeddableChunk(chunk.ordinal, chunk.heading, chunk.embedding_text(self.title))
            for chunk in split_body(self.body)
        )

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
            # Sorted for the same reason tags are: the file keeps the author's
            # order and the index returns them sorted, and a document that
            # round-tripped through the index must not read as diverged.
            ",".join(sorted(self.code)),
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
