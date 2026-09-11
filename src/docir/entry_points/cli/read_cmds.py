"""The read paths: ``get``, ``query``, ``search``, ``context``.

Only ``get`` returns a body. The other three return skeletons, which is the
context-saving contract these docstrings spend most of their length on —
``docir <cmd> --help`` is JSON when piped, so it is what an agent parses.
"""

from __future__ import annotations

from typing import Annotated

import typer

from docir.entry_points.cli import emit
from docir.entry_points.cli.runner import execute
from docir.modules.documents.api import DEFAULT_CONTEXT_EXPAND


def get(
    doc_ids: Annotated[
        list[str], typer.Argument(metavar="ID...", help="One or more document ids.")
    ],
    section: Annotated[
        str | None,
        typer.Option(
            "--section",
            help="Return only this heading's section instead of the whole body.",
        ),
    ] = None,
) -> None:
    """Return documents in full, or just one section of each.

    The only read path that carries a body: `query` / `search` / `context`
    return skeletons, so this is where you spend the tokens once you know which
    documents are worth them.

    --section takes a heading and returns that heading plus the text under it —
    the same span --replace-section addresses, with one difference that matters
    when writing it back: --replace-section keeps the document's heading line and
    replaces only what is under it, so the heading returned here is not part of
    the text you hand it. It is the paired read for
    `context`: a long document can rank on one of its sections, and this reads
    that section without paying for a body that is often ten times its size. An
    unknown heading is an error listing the ones that exist.

    Name several documents to read them in one command. That matters because a
    docir read is dominated by starting the process, not by retrieval, so five
    separate calls cost about five times one call regardless of how small the
    documents are. Address a section inline with ID#Heading — which is what a
    ranked hit's `matched_section` gives you:

        docir get adr-3f9a2b1c7d4e "arch-0002#Decision"

    One id answers with the document object, as it always has. Two or more
    answer with {"documents": [...], "missing": [...]}: an id that no longer
    exists, or a heading that does not, is reported beside the documents that
    did resolve instead of failing the whole read. --section takes one document;
    with several, write the '#' form.
    """
    emit.warn_on_global_fallback()
    if len(doc_ids) == 1:
        emit.emit_document(execute("get", {"doc_id": doc_ids[0], "section": section}))
        return
    emit.emit_batch(execute("get", {"doc_ids": doc_ids, "section": section}))


def query(
    type: Annotated[
        list[str] | None, typer.Option("--type", help="Only this type (repeat for more).")
    ] = None,
    status: Annotated[
        list[str] | None, typer.Option("--status", help="Only this status (repeat for more).")
    ] = None,
    tag: Annotated[
        list[str] | None,
        typer.Option("--tag", help="Only documents carrying this tag (repeat for more)."),
    ] = None,
    include_archived: Annotated[
        bool, typer.Option("--include-archived", help="Also return archived documents.")
    ] = False,
    include_inactive: Annotated[
        bool,
        typer.Option("--include-inactive", help="Also return documents in an inactive status."),
    ] = False,
    include_resolved: Annotated[bool, typer.Option("--include-resolved", hidden=True)] = False,
    owner: Annotated[
        str | None, typer.Option("--owner", help="Only documents with this steward.")
    ] = None,
    stale: Annotated[
        bool, typer.Option("--stale", help="Only documents past their type's review cadence.")
    ] = False,
    code: Annotated[
        list[str] | None,
        typer.Option("--code", help="Only documents governing this path (repeat for more)."),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Maximum rows to return.")] = 50,
    offset: Annotated[int, typer.Option("--offset", help="Rows to skip; page with --limit.")] = 0,
    expr: Annotated[
        str | None,
        typer.Option("--expr", help="Keep documents a JMESPath expression matches."),
    ] = None,
) -> None:
    """Structured metadata filtering.

    `--owner` and `--stale` are the review queue: `--owner platform-team --stale`
    is "what does this team need to re-verify". `--stale` is applied before
    `--limit`, so the limit counts stale documents rather than truncating the
    set they were selected from.

    Staleness only says a document is past its type's review cadence — nobody
    has vouched for it recently. It is not a claim that the content is wrong.
    Confirm with `docir update <id> --verified` once you have re-read it.

    The clock runs from `verified`, or from the day a verification was `revoked`,
    or from `created` for a document nobody ever verified — never from the last
    edit. Writing into an unverified document does not take it off this queue,
    so a note recording that an open question is *still* open is safe to add
    (adr-fad49eaa4648). Only `--verified` clears an entry.

    Editing the title, description or body of a *verified* document withdraws
    that verification and restarts the cadence from that day (adr-f4e6ade4afd0) — the
    content somebody read is not the content that is there now. Pass `--verified`
    with the edit to keep the stamp.

    `--code <path>` answers the other direction: which documents declared they
    govern this file. Repeat it to ask about several paths at once — the answer
    is any document matching any of them, which is what makes
    `docir query --code $(git diff --name-only main | tr '\\n' ' ')` the set of
    decisions a branch should be read against. The paths are matched against
    the patterns as text, so a file the branch *deleted* still finds its
    decisions. A document governing a directory governs what is in it.

    `--expr` is a JMESPath expression, for the questions these flags cannot ask.
    It sees each document's own fields plus its edges resolved in *both*
    directions, every edge carrying the other document's type and status:

        id type status title description tags owner verified revoked created
        updated archived stale code isolated
        related     [{to, kind, type, status}]   outgoing
        related_by  [{to, kind, type, status}]   incoming

    A truthy result keeps the document, so a filter needs no comparison bolted
    on. Applied before --limit, like --stale:

        docir query --expr "stale && owner == `null`"
        docir query --type issue --expr "related[?status=='superseded']"
        docir query --expr "isolated"          # every exemption from `orphan`

    docir ships no expressions of its own — this is the ability to state a rule,
    not a rule (adr-7316abc6be93).
    """
    payload: dict[str, object] = {
        "types": tuple(type or ()),
        "statuses": tuple(status or ()),
        "tags": tuple(tag or ()),
        "include_archived": include_archived,
        "include_inactive": emit.wants_inactive(include_inactive, include_resolved),
        "owner": owner,
        "stale": stale,
        "expr": expr,
        "code": tuple(code or ()),
        "limit": limit,
        "offset": offset,
    }
    emit.warn_on_global_fallback()
    emit.emit_document_list(execute("query", payload))


def search(
    text: Annotated[str, typer.Argument(help="Free-text query.")],
    limit: Annotated[int, typer.Option("--limit", help="Maximum hits to return.")] = 20,
    offset: Annotated[int, typer.Option("--offset", help="Hits to skip; page with --limit.")] = 0,
    include_inactive: Annotated[
        bool,
        typer.Option("--include-inactive", help="Also return documents in an inactive status."),
    ] = False,
    include_resolved: Annotated[bool, typer.Option("--include-resolved", hidden=True)] = False,
    explain: Annotated[
        bool,
        typer.Option("--explain", help="Attach the retrieval trace to every hit."),
    ] = False,
) -> None:
    """Full-text search over title, description and body — not tags.

    `--explain` attaches each hit's rank and its raw BM25 score. Thinner than
    `context --explain` by nature: one backend, no fusion, nothing to weigh
    against anything.
    """
    payload: dict[str, object] = {
        "text": text,
        "limit": limit,
        "offset": offset,
        "include_inactive": emit.wants_inactive(include_inactive, include_resolved),
        "explain": explain,
    }
    emit.warn_on_global_fallback()
    emit.emit_document_list(execute("search", payload))


def context(
    task: Annotated[str, typer.Argument(help="Agent task description.")],
    limit: Annotated[int, typer.Option("--limit", help="Hard ceiling on documents returned.")] = 5,
    expand: Annotated[
        int,
        typer.Option(
            "--expand",
            help="How many of those slots may go to related documents (0 disables).",
        ),
    ] = DEFAULT_CONTEXT_EXPAND,
    include_inactive: Annotated[
        bool,
        typer.Option("--include-inactive", help="Also return documents in an inactive status."),
    ] = False,
    include_resolved: Annotated[bool, typer.Option("--include-resolved", hidden=True)] = False,
    min_score: Annotated[
        float | None,
        typer.Option(
            "--min-score",
            help="Drop ranked hits whose `similarity` is below this (0.0-1.0).",
        ),
    ] = None,
    also: Annotated[
        list[str] | None,
        typer.Option(
            "--also",
            help="Another phrasing of the same need (repeatable); fused with the task.",
        ),
    ] = None,
    explain: Annotated[
        bool,
        typer.Option("--explain", help="Attach the retrieval trace to every hit."),
    ] = False,
) -> None:
    """Ranked, minimal relevant document set (hybrid + graph traversal).

    ``--limit`` bounds the whole response. Graph expansion runs inside that
    budget: ``--expand`` slots are held for related documents, and any the graph
    does not use are given back to the ranked hits.

    Each ranked hit carries a `similarity` — the raw cosine against your task,
    the only number here with absolute meaning. `score` is rank-derived, so it is
    roughly the same for a perfect match and the only document in the store, and
    cannot tell you whether anything relevant exists. `--min-score` filters on
    `similarity`, so an empty result is a real answer: nothing was close enough.

    `--also` takes another phrasing of the same need, repeatable, retrieved
    alongside the task and fused with it. docir writes none of them — rewriting
    belongs with you, who has read the code. Passing a hypothetical *answer* is
    the useful case: a question and an answer do not look alike to an embedder,
    and searching with the answer's shape is what finds the document:

        docir context "how do clients authenticate" \\
          --also "Clients present a short-lived bearer token."

    Use it when you could defend the answer you are guessing. Measured on
    docir's own corpus: a correct hypothetical takes recall@5 from 0.88 to
    1.00, a confidently wrong one takes it to 0.75. Queries take turns filling
    the result rather than pooling scores, so the task keeps its share.

    `--explain` attaches the trace behind each hit — where it placed in the
    full-text and vector rankings, each RRF term, the raw cosine, and for a
    graph-reached document the seed it came from and whether that edge was a
    successor, an ordinary relation or a mention. Off by default: it is a
    diagnostic, and a skeleton read is meant to be cheap.

    Two things it does not filter: documents with no current vector (a
    lexical-only hit, whose similarity is unknown rather than zero — run `docir
    embed --flush` if you need the floor to cover everything) and graph-reached
    neighbours, which are included because a selected document points at them,
    not because they scored.

    While this store federates — peers in `.docir/stores.yaml`, or `--store` —
    every hit also carries the `store` that answered it and, when that store
    describes itself, a `store_description`. Read it: it is what says whether
    that corpus is the one that governs what you are doing, which the path
    cannot. A store writes its own once, beside the peers it reads:

        # .docir/stores.yaml
        description: Platform decisions every service must follow.
        stores:
          - ../platform/.docir

    Keep `stores:` even with no peers (`stores: []`): docir 0.20.0 and earlier
    refuse a `stores.yaml` without that key, and every read in that repository
    fails until it upgrades.
    """
    payload: dict[str, object] = {
        "task": task,
        "limit": limit,
        "expand": expand,
        "include_inactive": emit.wants_inactive(include_inactive, include_resolved),
        "min_score": min_score,
        "explain": explain,
        "also": list(also or ()),
    }
    emit.warn_on_global_fallback()
    emit.emit_document_list(execute("context", payload))


def register(app: typer.Typer) -> None:
    """Register these commands on the root app, in the order `--help` prints them."""
    app.command()(get)
    app.command()(query)
    app.command()(search)
    app.command()(context)
