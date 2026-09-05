"""The site model — what a published corpus looks like, before any HTML.

Pure: no I/O, no markdown library, no templates. Everything here is the shape of
the site and the rules for deriving it — which documents appear, in what order,
and which edges point at each page. The HTML lives in ``infra`` so those rules
can be checked without parsing a rendered page to find out what they were.

The input is deliberately the CLI's own JSON shape rather than a ``Document``
entity. ``publishing`` is a leaf module: it depends on nothing but the error
taxonomy, exactly like ``agents``, and it consumes the documented output of
``docir query`` / ``docir get``. That keeps the site a projection of the public
contract instead of a second reader of the aggregate.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

#: Relation kinds whose *incoming* direction answers "is this still current?".
#: A `supersedes` edge points from the new document to the old one, so the
#: replacement is only reachable from the old page by looking backwards — which
#: is precisely the question a reader of an old decision has. Mirrors
#: `context`'s expansion rule; kept separate because this one is about what a
#: page shows, not about what retrieval pulls in.
SUCCESSOR_KINDS = frozenset({"supersedes", "contradicts"})

#: How an *incoming* edge of each kind reads from the target's side. A panel
#: that says "refines" on both directions tells the reader the opposite of the
#: truth for half its rows, so an inbound list is phrased from the page's own
#: point of view. An unknown kind keeps its own name behind the arrow rather
#: than guessing an English passive.
#:
#: It lives in the domain because both renderers need it — the document page's
#: relation panel and the graph card's — and they must not disagree about what
#: an edge means. `infra/graph.py` cannot import `infra/rendering.py` (the
#: dependency runs the other way), so a copy in each was the alternative.
INBOUND_KIND = {
    "relates_to": "relates to",
    "supersedes": "superseded by",
    "refines": "refined by",
    "implements": "implemented by",
    "depends_on": "depended on by",
    "contradicts": "contradicted by",
}


@dataclass(frozen=True, slots=True)
class Edge:
    """One typed relation as a page renders it."""

    target: str
    kind: str
    #: The target's title, when the target is in the corpus. ``None`` means a
    #: dangling edge — rendered as the bare id rather than silently dropped, so
    #: the site shows the same broken link `docir check` reports.
    title: str | None = None


@dataclass(frozen=True, slots=True)
class SiteDocument:
    """One document as the site needs it — frontmatter, body, and both edge directions."""

    id: str
    title: str
    description: str
    type: str
    status: str
    created: str
    updated: str
    body: str
    tags: tuple[str, ...] = ()
    outgoing: tuple[Edge, ...] = ()
    incoming: tuple[Edge, ...] = ()
    owner: str = ""
    verified: str | None = None
    #: When a standing verification was withdrawn. Carried so the page does not
    #: report a document as never verified when the corpus knows it was, and
    #: knows when the claim lapsed.
    revoked: str | None = None
    stale: bool = False
    archived: bool = False
    #: Repo-relative globs the document declares it governs. Published as text:
    #: the site has no repository to resolve them against, so it shows what the
    #: document claims and never whether the claim still holds.
    code: tuple[str, ...] = ()

    @property
    def successors(self) -> tuple[Edge, ...]:
        """Incoming edges that mean "something replaced or contradicts this".

        Surfaced separately because it is the one relation a reader must not
        miss: acting on a superseded decision is the failure the typed graph
        exists to prevent, and an undifferentiated "linked from" list buries it.
        """
        return tuple(edge for edge in self.incoming if edge.kind in SUCCESSOR_KINDS)

    @classmethod
    def from_view(cls, view: Mapping[str, object]) -> SiteDocument:
        """Build from a ``docir get`` payload (trimmed or not).

        Absent keys are read as their defaults, which is the CLI's documented
        contract for trimmed JSON — so a site can be built from captured output
        as well as from an in-process call.
        """
        return cls(
            id=_text(view, "id"),
            title=_text(view, "title"),
            description=_text(view, "description"),
            type=_text(view, "type"),
            status=_text(view, "status"),
            created=_text(view, "created"),
            updated=_text(view, "updated"),
            body=_text(view, "body"),
            tags=_texts(view, "tags"),
            outgoing=_edges(view.get("related")),
            owner=_text(view, "owner"),
            verified=_optional_text(view, "verified"),
            revoked=_optional_text(view, "revoked"),
            stale=bool(view.get("stale", False)),
            archived=bool(view.get("archived", False)),
            code=_texts(view, "code"),
        )


@dataclass(frozen=True, slots=True)
class Site:
    """The whole corpus, resolved: back-edges filled in and order settled."""

    documents: tuple[SiteDocument, ...] = ()
    #: Types in the order sections appear, each with its documents.
    groups: tuple[tuple[str, tuple[SiteDocument, ...]], ...] = field(default=())

    @property
    def stale_count(self) -> int:
        return sum(1 for document in self.documents if document.stale)


def build_site(views: Sequence[Mapping[str, object]]) -> Site:
    """Resolve a list of document payloads into a renderable site.

    Two things happen here that a template must not be left to do. Edge titles
    are resolved, so a link reads as a title and a *dangling* edge is visibly
    dangling rather than silently absent. And every edge is inverted onto its
    target, because a page has to show what points *at* it — the graph is
    stored one way and read both ways.
    """
    documents = [SiteDocument.from_view(view) for view in views]
    titles = {document.id: document.title for document in documents}

    inbound: dict[str, list[Edge]] = {document.id: [] for document in documents}
    resolved: list[SiteDocument] = []
    for document in documents:
        outgoing = tuple(
            Edge(target=edge.target, kind=edge.kind, title=titles.get(edge.target))
            for edge in document.outgoing
        )
        resolved.append(_replace_edges(document, outgoing=outgoing))
        for edge in outgoing:
            if edge.target in inbound:
                inbound[edge.target].append(
                    Edge(target=document.id, kind=edge.kind, title=document.title)
                )

    final = tuple(
        _replace_edges(
            document,
            outgoing=document.outgoing,
            incoming=tuple(sorted(inbound[document.id], key=lambda e: (e.kind, e.target))),
        )
        for document in resolved
    )
    ordered = tuple(sorted(final, key=_document_sort_key))
    groups = tuple(
        (type_name, tuple(d for d in ordered if d.type == type_name))
        for type_name in sorted({document.type for document in ordered})
    )
    return Site(documents=ordered, groups=groups)


def graph_payload(site: Site) -> dict[str, list[dict[str, object]]]:
    """The relation graph as data — the shape the graph page embeds.

    Derived from the *resolved* site so degree counts both directions: a
    document's visual weight on the map is how connected it is, not how many
    edges it happens to declare itself. Dangling edges (target outside the
    corpus) are excluded — the map cannot draw an arrow to a node that is not
    there, and the document pages already surface the broken reference; the
    graph silently omitting it is not a second loss.

    Keys are deliberately terse (``t``/``ty``/``st``/``tg``/``up``/``ar``):
    the payload is inlined into every graph page and the corpus appears once
    per key per document.
    """
    ids = {document.id for document in site.documents}
    nodes: list[dict[str, object]] = [
        {
            "id": document.id,
            "t": document.title,
            "ty": document.type,
            "st": document.status,
            "d": document.description,
            "tg": list(document.tags),
            "deg": sum(1 for edge in document.outgoing if edge.target in ids)
            + len(document.incoming),
            "up": document.updated,
            "ar": document.archived,
        }
        for document in site.documents
    ]
    edges: list[dict[str, object]] = [
        {"s": document.id, "t": edge.target, "k": edge.kind}
        for document in site.documents
        for edge in document.outgoing
        if edge.target in ids
    ]
    return {"nodes": nodes, "edges": edges}


def _document_sort_key(document: SiteDocument) -> tuple[str, str, str]:
    """Type, then newest first, then id.

    Newest-first inside a type because a reader arriving at a section wants the
    current decisions, not the first ones ever written. ``created`` is an ISO
    date, so a reversed string sort is a reversed chronological sort.
    """
    return (document.type, _descending(document.created), document.id)


def _descending(value: str) -> str:
    """Invert an ISO date for ascending sorts (no reverse= per key available)."""
    return "".join(chr(ord("9") - int(ch)) if ch.isdigit() else ch for ch in value)


def _replace_edges(
    document: SiteDocument,
    *,
    outgoing: tuple[Edge, ...],
    incoming: tuple[Edge, ...] = (),
) -> SiteDocument:
    return SiteDocument(
        id=document.id,
        title=document.title,
        description=document.description,
        type=document.type,
        status=document.status,
        created=document.created,
        updated=document.updated,
        body=document.body,
        tags=document.tags,
        outgoing=outgoing,
        incoming=incoming,
        owner=document.owner,
        verified=document.verified,
        revoked=document.revoked,
        stale=document.stale,
        archived=document.archived,
        code=document.code,
    )


def _text(view: Mapping[str, object], key: str) -> str:
    value = view.get(key)
    return "" if value is None else str(value)


def _optional_text(view: Mapping[str, object], key: str) -> str | None:
    value = view.get(key)
    return None if value is None else str(value)


def _texts(view: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = view.get(key)
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list | tuple):
        return tuple(str(item) for item in value)
    return ()


def _edges(value: object) -> tuple[Edge, ...]:
    """Parse ``related`` — typed mappings, or bare ids from a pre-typed file."""
    if not isinstance(value, list | tuple):
        return ()
    edges: list[Edge] = []
    for item in value:
        if isinstance(item, Mapping):
            target = str(item.get("target") or item.get("to") or "")
            if target:
                edges.append(Edge(target=target, kind=str(item.get("kind") or "relates_to")))
        elif item:
            edges.append(Edge(target=str(item), kind="relates_to"))
    return tuple(edges)
