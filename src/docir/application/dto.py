"""Data-transfer objects crossing the application boundary.

Requests are plain, framework-free inputs assembled by the presentation layer;
:class:`DocumentView` is the read-side output. Dates are carried as ISO strings
so the DTOs serialize cleanly over the daemon's JSON transport.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from docir.domain.entities.document import Document


@dataclass(frozen=True, slots=True)
class DocumentView:
    """A serialization-friendly projection of a :class:`Document`."""

    id: str
    title: str
    description: str
    type: str
    status: str
    created: str
    updated: str
    tags: tuple[str, ...]
    related: tuple[str, ...]
    archived: bool
    body: str
    path: str | None
    score: float | None = None
    via_graph: bool = False

    @classmethod
    def from_document(
        cls,
        document: Document,
        *,
        score: float | None = None,
        via_graph: bool = False,
    ) -> DocumentView:
        return cls(
            id=document.id,
            title=document.title,
            description=document.description,
            type=document.type,
            status=document.status,
            created=document.created.isoformat(),
            updated=document.updated.isoformat(),
            tags=document.tags,
            related=document.related,
            archived=document.archived,
            body=document.body,
            path=document.path,
            score=score,
            via_graph=via_graph,
        )


@dataclass(frozen=True, slots=True)
class TagView:
    """A serialization-friendly projection of a :class:`Tag`."""

    key: str
    description: str


@dataclass(frozen=True, slots=True)
class AddDocumentRequest:
    """Input for ``docs add``."""

    type: str
    title: str
    description: str
    tags: tuple[str, ...] = ()
    related: tuple[str, ...] = ()
    body: str = ""
    status: str | None = None
    wait_embeddings: bool = False


@dataclass(frozen=True, slots=True)
class UpdateDocumentRequest:
    """Input for ``docs update`` (metadata patch and/or a body edit).

    ``None`` collection fields mean "leave unchanged"; an empty tuple means
    "clear". Exactly one body mode may be set at a time.
    """

    doc_id: str
    status: str | None = None
    set_title: str | None = None
    set_description: str | None = None
    set_tags: tuple[str, ...] | None = None
    set_related: tuple[str, ...] | None = None
    append_section: tuple[str, str] | None = None
    replace_section: tuple[str, str] | None = None
    replace_body: str | None = None
    force: bool = False
    allow_transition_override: bool = False
    wait_embeddings: bool = False


@dataclass(frozen=True, slots=True)
class QueryRequest:
    """Input for ``docs query`` (structured filtering)."""

    types: tuple[str, ...] = ()
    statuses: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    include_archived: bool = False
    include_inactive: bool = False
    limit: int = 50


@dataclass(frozen=True, slots=True)
class SearchRequest:
    """Input for ``docs search`` (full-text)."""

    text: str
    limit: int = 20
    include_inactive: bool = False


@dataclass(frozen=True, slots=True)
class ContextRequest:
    """Input for ``docs context`` (hybrid ranking + one-hop graph traversal)."""

    task: str
    limit: int = 5
    include_inactive: bool = False


@dataclass(frozen=True, slots=True)
class CheckReport:
    """Output of ``docs check`` / ``docs lint`` — a list of findings."""

    findings: tuple[dict[str, object], ...] = field(default_factory=tuple)
