"""Data-transfer objects crossing the documents module boundary.

Requests are plain, framework-free inputs assembled by the caller;
:class:`DocumentView` is the read-side output. Dates are carried as ISO strings
so the DTOs serialize cleanly over the daemon's JSON transport.
"""

from __future__ import annotations

from dataclasses import dataclass

from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.value_objects.relations import RelatedRef


@dataclass(frozen=True, slots=True)
class RelatedView:
    """A serialization-friendly typed edge (``{target, kind}`` when JSON-encoded)."""

    target: str
    kind: str

    @classmethod
    def of(cls, ref: RelatedRef) -> RelatedView:
        return cls(target=ref.target, kind=ref.kind)


def _related_views(document: Document) -> tuple[RelatedView, ...]:
    return tuple(RelatedView.of(ref) for ref in document.related)


@dataclass(frozen=True, slots=True)
class DocumentView:
    """A serialization-friendly projection of a :class:`Document` in full."""

    id: str
    title: str
    description: str
    type: str
    status: str
    created: str
    updated: str
    tags: tuple[str, ...]
    related: tuple[RelatedView, ...]
    archived: bool
    body: str
    path: str | None
    owner: str = ""
    verified: str | None = None
    stale: bool = False
    score: float | None = None
    via_graph: bool = False

    @classmethod
    def from_document(
        cls,
        document: Document,
        *,
        stale: bool = False,
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
            related=_related_views(document),
            archived=document.archived,
            body=document.body,
            path=document.path,
            owner=document.owner,
            verified=None if document.verified is None else document.verified.isoformat(),
            stale=stale,
            score=score,
            via_graph=via_graph,
        )


@dataclass(frozen=True, slots=True)
class DocumentSummary:
    """The skeleton projection for list read paths — frontmatter without the body.

    ``query`` / ``search`` / ``context`` return these so an agent scans titles,
    descriptions, tags, and typed edges cheaply, then fetches only the bodies it
    needs by id via ``get``. This two-tier contract is where the context savings
    come from — the body never rides along in a result set.
    """

    id: str
    title: str
    description: str
    type: str
    status: str
    created: str
    updated: str
    tags: tuple[str, ...]
    related: tuple[RelatedView, ...]
    archived: bool
    owner: str = ""
    verified: str | None = None
    stale: bool = False
    score: float | None = None
    via_graph: bool = False

    @classmethod
    def from_document(
        cls,
        document: Document,
        *,
        stale: bool = False,
        score: float | None = None,
        via_graph: bool = False,
    ) -> DocumentSummary:
        return cls(
            id=document.id,
            title=document.title,
            description=document.description,
            type=document.type,
            status=document.status,
            created=document.created.isoformat(),
            updated=document.updated.isoformat(),
            tags=document.tags,
            related=_related_views(document),
            archived=document.archived,
            owner=document.owner,
            verified=None if document.verified is None else document.verified.isoformat(),
            stale=stale,
            score=score,
            via_graph=via_graph,
        )


@dataclass(frozen=True, slots=True)
class AddDocumentRequest:
    """Input for ``docs add``.

    ``related`` entries are compact ``<id>`` / ``<id>:<kind>`` tokens (the CLI
    form), parsed into typed edges by the service.
    """

    type: str
    title: str
    description: str
    tags: tuple[str, ...] = ()
    related: tuple[str, ...] = ()
    body: str = ""
    status: str | None = None
    owner: str | None = None
    wait_embeddings: bool = False


@dataclass(frozen=True, slots=True)
class UpdateDocumentRequest:
    """Input for ``docs update`` (metadata patch and/or a body edit).

    ``None`` collection fields mean "leave unchanged"; an empty tuple means
    "clear". Exactly one body mode may be set at a time. ``set_related`` entries
    are compact ``<id>`` / ``<id>:<kind>`` tokens.
    """

    doc_id: str
    status: str | None = None
    set_title: str | None = None
    set_description: str | None = None
    set_tags: tuple[str, ...] | None = None
    set_related: tuple[str, ...] | None = None
    set_owner: str | None = None
    mark_verified: bool = False
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
