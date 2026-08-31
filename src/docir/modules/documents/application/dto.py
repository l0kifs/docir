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
    #: Repo-relative globs naming the code this document governs. Empty (and so
    #: dropped from the trimmed JSON) when it names none.
    code: tuple[str, ...] = ()
    stale: bool = False
    score: float | None = None
    via_graph: bool = False
    #: Which section ``body`` was narrowed to, when the caller asked for one.
    #: Absent means the body is whole — the trimmed JSON drops the field, so an
    #: agent reads "no section key" as "you have all of it".
    section: str | None = None
    #: Set only when ``--override`` actually bypassed the transition rules, so
    #: the CLI can say which rule was broken. Deliberately not persisted to the
    #: file: docir has no actors (adr-90e994d931cc), so "who overrode this" has no
    #: answer worth storing, and git already records the status change itself.
    forced_transition: str | None = None
    #: Ids this document's *body* names, and the documents whose bodies name it —
    #: the derived graph, resolved against the index. Untyped and unauthored, so
    #: they sit beside ``related`` rather than in it: a reader must be able to
    #: tell an edge somebody wrote from one docir inferred.
    #:
    #: On ``get`` only. The list paths return skeletons, and two more id arrays
    #: per hit is exactly the context cost that contract exists to avoid — while
    #: on ``get`` the body they were derived from is already in the response.
    mentions: tuple[str, ...] = ()
    mentioned_by: tuple[str, ...] = ()

    @classmethod
    def from_document(
        cls,
        document: Document,
        *,
        stale: bool = False,
        score: float | None = None,
        via_graph: bool = False,
        forced_transition: str | None = None,
        mentions: tuple[str, ...] = (),
        mentioned_by: tuple[str, ...] = (),
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
            code=document.code,
            stale=stale,
            score=score,
            via_graph=via_graph,
            forced_transition=forced_transition,
            mentions=mentions,
            mentioned_by=mentioned_by,
        )


@dataclass(frozen=True, slots=True)
class MissingDocument:
    """One address in a batch read that did not resolve, and why.

    Carries the ``ref`` as the caller wrote it rather than an id plus a section:
    the address is what they would have to retype, it is what federation resends
    to a peer, and splitting it into two fields would put the ``id#heading``
    grammar in a second place — which is how a document becomes addressable by
    one spelling and invisible to another. The id is the ref, or its half before
    the hash, and ``error`` names it anyway.
    """

    ref: str
    error: str


@dataclass(frozen=True, slots=True)
class DocumentBatch:
    """Several deep reads answered together (``get`` with more than one id).

    A partial answer on purpose. The batch exists because an agent that just
    ranked five documents should pay one round trip for their bodies, and one of
    those five having been deleted since must not cost it the other four — so a
    reference that fails lands in ``missing`` instead of failing the request. A
    *malformed* reference still raises: that is the caller's own typo, not a
    fact about the corpus, and it is Tier 0's to refuse.

    ``documents`` holds them in the order they were asked for, deduplicated by
    address — the same document twice under two headings is two entries, the
    same address twice is one.
    """

    documents: tuple[DocumentView, ...]
    missing: tuple[MissingDocument, ...] = ()


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
    #: The governed globs ride along on the skeleton, like tags and edges: they
    #: are a handful of tokens and they answer "does this document concern the
    #: code I am about to change" without a second fetch.
    code: tuple[str, ...] = ()
    stale: bool = False
    score: float | None = None
    #: Raw cosine similarity to the query — the only field with absolute
    #: meaning. ``score`` is rank-derived (RRF), so it cannot distinguish a
    #: perfect match from the only document in the store. ``None`` means the
    #: document had no current vector, or arrived via the graph rather than
    #: the ranking; that is *unknown*, not zero.
    similarity: float | None = None
    #: The heading of the section whose vector produced ``similarity`` — what to
    #: pass to ``get --section`` next. ``None`` when the document's own vector
    #: won, when the hit was lexical or graph-reached, or when the winning chunk
    #: has no heading: the match is real but not addressable as a section, which
    #: is *unknown*, not "nothing matched".
    #:
    #: Deliberately not called ``section``: ``DocumentView.section`` already
    #: means "the body was narrowed to this one", a different claim on a sibling
    #: DTO, and one word meaning two things is how `stale` came to name three
    #: concepts (issue-d8295c5c76d1).
    matched_section: str | None = None
    via_graph: bool = False
    #: How this document reached the result, when ``--explain`` asked. Absent
    #: otherwise, and absent from every write path: a trace is a diagnostic, and
    #: paying for it on every read would tax the skeleton contract it explains
    #: (issue-d3278330eb63). Keys are omitted rather than nulled — a hit the FTS
    #: index never returned carries no ``lexical_rank``, which is the fact.
    explain: dict[str, object] | None = None

    @classmethod
    def from_document(
        cls,
        document: Document,
        *,
        stale: bool = False,
        score: float | None = None,
        similarity: float | None = None,
        matched_section: str | None = None,
        via_graph: bool = False,
        explain: dict[str, object] | None = None,
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
            code=document.code,
            stale=stale,
            score=score,
            similarity=similarity,
            matched_section=matched_section,
            via_graph=via_graph,
            explain=explain,
        )


@dataclass(frozen=True, slots=True)
class AddDocumentRequest:
    """Input for ``docir add``.

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
    #: Repo-relative globs naming the code this document governs.
    code: tuple[str, ...] = ()
    #: Adopt an existing id instead of allocating one — for a repo migrating a
    #: numbered ADR corpus, where losing `adr-0007` breaks every historical
    #: cross-reference. It is *supplied*, never inferred, and validated against
    #: the type's prefix and both the index and the files before use.
    doc_id: str | None = None
    wait_embeddings: bool = False


@dataclass(frozen=True, slots=True)
class UpdateDocumentRequest:
    """Input for ``docir update`` (metadata patch and/or a body edit).

    ``None`` collection fields mean "leave unchanged"; an empty tuple means
    "clear". Exactly one body mode may be set at a time. ``set_related`` entries
    are compact ``<id>`` / ``<id>:<kind>`` tokens.
    """

    doc_id: str
    status: str | None = None
    #: Retype the document. The id never changes with it — it is the corpus's
    #: only address, written into every ``related`` edge that points here, so a
    #: retyped document keeps the prefix it was minted under. A prefix records
    #: which type minted an id, not which type owns it today (adr-f8cce745d0d5).
    set_type: str | None = None
    set_title: str | None = None
    set_description: str | None = None
    set_tags: tuple[str, ...] | None = None
    set_related: tuple[str, ...] | None = None
    set_owner: str | None = None
    #: ``None`` leaves the governed globs unchanged; an empty tuple clears them,
    #: the same convention ``set_tags`` / ``set_related`` follow.
    set_code: tuple[str, ...] | None = None
    mark_verified: bool = False
    append_section: tuple[str, str] | None = None
    replace_section: tuple[str, str] | None = None
    #: Delete a section outright — the one body edit that takes a heading and no
    #: text. It is how a body carrying a heading twice is repaired without
    #: ``replace_body`` (issue-9d4db5cd5f29).
    remove_section: str | None = None
    replace_body: str | None = None
    force: bool = False
    allow_transition_override: bool = False
    wait_embeddings: bool = False


@dataclass(frozen=True, slots=True)
class QueryRequest:
    """Input for ``docir query`` (structured filtering).

    ``owner`` and ``stale_only`` are what turn staleness from a finding into a
    worklist: "what do I own?" and "what of it is overdue?". Combined they are
    the review queue for one person.
    """

    types: tuple[str, ...] = ()
    statuses: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    include_archived: bool = False
    include_inactive: bool = False
    owner: str | None = None
    stale_only: bool = False
    #: A JMESPath expression over each document's projection — the questions
    #: `query`'s fixed flags cannot ask (issue-9b2d2ab09060). Like `stale_only`
    #: it is a post-SQL predicate applied *before* the limit, so `--expr ...
    #: --limit 10` means ten matching documents.
    expression: str | None = None
    #: Paths to answer "which documents govern this?" for. Matched against each
    #: document's ``code`` globs — like ``stale_only``, a predicate the index
    #: cannot express, so it is applied after the query and before the limit.
    code_paths: tuple[str, ...] = ()
    limit: int = 50
    #: Rows to skip. A short page means the end — there is no total in the
    #: response, which is a bare JSON array with nowhere to put one.
    offset: int = 0


@dataclass(frozen=True, slots=True)
class SearchRequest:
    """Input for ``docir search`` (full-text)."""

    text: str
    limit: int = 20
    include_inactive: bool = False
    offset: int = 0
    #: Attach the retrieval trace to every hit. Off by default: it is a
    #: diagnostic, and the skeleton contract exists to keep a read cheap.
    explain: bool = False


#: How many of a context result's slots are reserved for graph-reached
#: neighbours by default. Expansion used to run *after* the limit was applied
#: and was itself uncapped, so ``--limit 3`` could return nine documents — the
#: opposite of the token budget the limit exists to enforce.
DEFAULT_CONTEXT_EXPAND = 2


@dataclass(frozen=True, slots=True)
class ContextRequest:
    """Input for ``docir context`` (hybrid ranking + one-hop graph traversal).

    ``limit`` is the hard ceiling on documents returned. ``expand`` is how many
    of those slots may go to graph-reached neighbours; the rest go to ranked
    hits, and unused neighbour slots are backfilled with more ranked hits.

    ``min_score`` is a floor on the *raw cosine similarity*, not on the fused
    ``score``: the latter is rank-derived, so it is ~identical for a perfect
    match and a nonsense one and cannot express "nothing relevant exists".
    """

    task: str
    limit: int = 5
    include_inactive: bool = False
    expand: int = DEFAULT_CONTEXT_EXPAND
    min_score: float | None = None
    #: Attach the retrieval trace to every hit. Off by default: it is a
    #: diagnostic, and the skeleton contract exists to keep a read cheap.
    explain: bool = False
    #: Extra phrasings of the same need, retrieved alongside ``task`` and fused
    #: with it. docir writes none of them: rewriting belongs at the caller,
    #: which is already a model that has read the code (adr-27c63ad02695). An
    #: agent passing a hypothetical *answer* here is doing HyDE, with a better
    #: model than docir could ship and no dependency.
    also: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BenchTask:
    """One judged retrieval task: a query, and the ids a reader would need.

    ``relevant`` holds document **ids**, not paths, which is what makes a
    fixture survive the edits a corpus actually receives — a retitle moves the
    filename, a retype moves the directory, and neither touches the id.
    """

    id: str
    task: str
    relevant: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BenchRequest:
    """Input for ``docir bench``: the judged tasks, and the result-set size."""

    tasks: tuple[BenchTask, ...]
    limit: int = 5
    expand: int = DEFAULT_CONTEXT_EXPAND


@dataclass(frozen=True, slots=True)
class StrategyScore:
    """One retrieval strategy's means over every task that could be scored."""

    #: The strategy as a user would invoke it, e.g. ``context --expand 0``.
    name: str
    recall: float
    precision: float
    mrr: float
    #: Tasks this strategy was scored over, so a mean is never read as covering
    #: more than it did.
    tasks: int


@dataclass(frozen=True, slots=True)
class BenchResult:
    """What ``docir bench`` measured, and what it could not.

    ``unresolved`` and ``dropped`` are reported rather than counted away. A
    fixture outlives the corpus it judges, so ids go missing; silently removing
    them shrinks the recall denominator and *improves* the score for the wrong
    reason, which is the one failure mode a benchmark must not have.
    """

    strategies: tuple[StrategyScore, ...]
    limit: int
    expand: int
    #: Tasks actually scored.
    scored: int
    #: Ids named by the fixture that no document carries, sorted and deduped.
    unresolved: tuple[str, ...]
    #: Task ids dropped because every id they named was unresolved.
    dropped: tuple[str, ...]
