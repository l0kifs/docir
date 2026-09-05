"""The MCP tool surface — the CLI's vocabulary over a second transport.

This is a *third* client of :class:`~docir.entry_points.dispatch.Dispatcher`,
beside the CLI and the daemon socket. Every tool below is one ``Request``
through a :class:`RequestExecutor`, so an MCP tool and its CLI command cannot
answer differently: the command vocabulary still lives in exactly one place.
Nothing here knows what a document is — it knows commands and payloads.

Two properties are inherited rather than reimplemented, and both are the point:

* the executor is the **daemon** one by default, so an MCP client gets the warm
  embedding model and the daemon's write serialization for free;
* every result goes through the same :func:`~docir.entry_points.payload.trim`
  the CLI's piped-JSON path uses, so a tool result costs an agent what the
  captured CLI output costs it.

``fastmcp`` is imported at module scope here and this module is imported lazily
by :mod:`docir.entry_points.mcp.cmds` — see that module for why the ~0.3s stays
off every other command's path.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any, cast

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from docir.entry_points.federation import STORES_KEY, resolve_extra
from docir.entry_points.payload import trim
from docir.platform.errors import DocirError
from docir.platform.transport.messages import Request, RequestExecutor

#: Handed to the client as the server's `instructions`. It carries the two
#: rules an agent cannot infer from the tool list: reads are body-less, and
#: markdown is never edited directly.
INSTRUCTIONS = """\
docir stores this project's design documents (decisions/ADRs, issues,
architecture notes) as git-backed markdown compiled into a derived index.

Two rules govern every use of these tools:

1. Never edit the markdown files directly — `docir_add` and `docir_update` are
   the only write path, and they are what guarantee schema-valid frontmatter
   and collision-free ids.
2. `docir_context`, `docir_search` and `docir_query` return *skeletons*:
   frontmatter, typed relation edges and staleness, with no body. Scan wide
   with those, then fetch the bodies you need with `docir_get` — one call with
   `doc_ids`, not one call per document.

Start a task with `docir_context "<what you are about to change>"`. Call
`docir_schema` before your first write to learn the valid types, statuses and
relation kinds — an invalid one is refused, not corrected.
"""

#: MCP behaviour hints. A read tool is `readOnlyHint`; a tool that can drop a
#: document or rewrite other documents' frontmatter is `destructiveHint`.
_READ_ONLY = {"readOnlyHint": True}
_DESTRUCTIVE = {"destructiveHint": True}

#: The default `--expand` for `docir_context`, mirrored from the CLI so the two
#: transports return the same neighbourhood for the same query.
_DEFAULT_EXPAND = 1


class _Gateway:
    """Runs one command through the executor and shapes the reply for a tool.

    Serialized by a lock: FastMCP runs sync tools in a thread pool, so two tool
    calls can land at once, and neither executor promises to be re-entrant. The
    daemon serializes writes anyway — this makes the in-process executor
    (``--no-daemon``) behave the same way rather than differently.
    """

    def __init__(self, executor: RequestExecutor) -> None:
        self._executor = executor
        self._lock = threading.Lock()

    def __call__(self, command: str, payload: dict[str, object]) -> object:
        request = Request(command=command, payload=payload)
        try:
            with self._lock:
                response = self._executor.execute(request)
        except DocirError as exc:
            # Raised client-side by the transport (unreachable daemon, a reply
            # that never came) rather than returned by the dispatcher.
            raise ToolError(str(exc)) from exc
        if response.ok:
            return trim(response.data)
        error = response.error or {}
        raise ToolError(str(error.get("message", "unknown error")))

    def one(self, command: str, payload: dict[str, object]) -> dict[str, Any]:
        """A command whose result is a single object."""
        return cast(dict[str, Any], self(command, payload))

    def many(self, command: str, payload: dict[str, object]) -> list[dict[str, Any]]:
        """A command whose result is a list of objects."""
        return cast(list[dict[str, Any]], self(command, payload))


def build_mcp_server(
    executor: RequestExecutor,
    *,
    describe_schema: Callable[[], dict[str, object]],
    version: str,
) -> FastMCP:
    """Wire the docir command vocabulary onto a FastMCP server.

    ``describe_schema`` is injected rather than read here: the schema is the one
    thing an agent needs that is not a dispatcher command (it is a file the
    store owns, not an index query), and passing it in keeps this module a pure
    client of :class:`RequestExecutor`.
    """
    mcp: FastMCP = FastMCP(name="docir", instructions=INSTRUCTIONS, version=version)
    run = _Gateway(executor)

    # -- read path ----------------------------------------------------------

    @mcp.tool(annotations=_READ_ONLY)
    def docir_context(
        task: str,
        limit: int = 5,
        expand: int = _DEFAULT_EXPAND,
        min_score: float | None = None,
        include_inactive: bool = False,
        also: list[str] | None = None,
        explain: bool = False,
        stores: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Rank the documents relevant to a task. Start here.

        Fuses full-text and vector rankings, then pulls in graph neighbours of
        what ranked — including the documents that supersede or contradict them,
        so a replaced decision arrives with its replacement. Returns skeletons
        (no body); fetch a body with `docir_get`.

        A hit that matched through one of its sections carries
        `matched_section` — pass that heading straight to `docir_get(section=)`
        rather than pulling the whole body. Absent means the match was not
        addressable as a section (the document's own vector, a full-text hit, or
        a graph neighbour), not that nothing matched.

        Args:
            task: What you are about to do, in your own words.
            limit: Maximum documents to return — a token budget, not a page.
            expand: How many graph hops to follow from each ranked document.
            min_score: Drop hits whose raw cosine `similarity` is below this.
                Filters on `similarity`, never on `score` (which is rank-derived
                and has no absolute meaning). Omit for no floor.
            include_inactive: Also return archived documents and ones in a
                status their type marks inactive.
            also: Other phrasings of the same need, retrieved beside `task` and
                fused with it. docir writes none of them — you are the model
                that has read the code. The case that pays is a hypothetical
                *answer*: a question and an answer do not look alike to an
                embedder, so searching with the answer's shape is what finds the
                document. Use it when you could defend the answer you are
                guessing — a correct one takes recall@5 from 0.88 to 1.00 on
                docir's own corpus and a confidently wrong one takes it to 0.75.
            explain: Attach the retrieval trace to each hit — where it placed in
                the full-text and vector rankings, each RRF term, the raw
                cosine, and for a graph-reached document the seed and whether
                that edge was a successor, a relation or a mention.
            stores: Extra store paths to read alongside this one, for this call.
                Added to whatever `stores.yaml` already declares. Never written
                to; every row of the reply names the `store` it came from.
        """
        return run.many(
            "context",
            {
                "task": task,
                "limit": limit,
                "expand": expand,
                "min_score": min_score,
                "include_inactive": include_inactive,
                "also": list(also or []),
                "explain": explain,
                STORES_KEY: resolve_extra(stores or []),
            },
        )

    @mcp.tool(annotations=_READ_ONLY)
    def docir_search(
        text: str,
        limit: int = 20,
        offset: int = 0,
        include_inactive: bool = False,
        stores: list[str] | None = None,
        explain: bool = False,
    ) -> list[dict[str, Any]]:
        """Full-text search over title, description and body.

        Not over tags — those are a controlled vocabulary, queried with
        `docir_query`. Returns skeletons. Pages with `limit`/`offset`; a page
        shorter than `limit` is the end.

        Args:
            text: The search terms.
            limit: Page size.
            offset: How many matches to skip.
            include_inactive: Also return documents in an inactive status.
            stores: Extra store paths to read alongside this one, for this call.
        """
        return run.many(
            "search",
            {
                "text": text,
                "limit": limit,
                "offset": offset,
                "include_inactive": include_inactive,
                "explain": explain,
                STORES_KEY: resolve_extra(stores or []),
            },
        )

    @mcp.tool(annotations=_READ_ONLY)
    def docir_query(
        types: list[str] | None = None,
        statuses: list[str] | None = None,
        tags: list[str] | None = None,
        owner: str | None = None,
        stale: bool = False,
        code: list[str] | None = None,
        include_archived: bool = False,
        include_inactive: bool = False,
        limit: int = 50,
        offset: int = 0,
        expr: str | None = None,
        stores: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Filter documents by their frontmatter. No text matching.

        `expr` is a JMESPath expression over each document, for the questions
        these flags cannot ask. It sees the document's own fields plus its edges
        resolved in **both** directions, each carrying the other document's type
        and status:

            id type status title description tags owner verified revoked
            created updated archived stale code isolated
            related     [{to, kind, type, status}]   outgoing
            related_by  [{to, kind, type, status}]   incoming

        A truthy result keeps the document, so `related[?status=='superseded']`
        is a filter with no comparison bolted on. Applied before `limit`, like
        `stale`. Examples: `stale && owner == `null``,
        `length(related_by[?kind!='relates_to']) == `0``, and `isolated` — every
        document exempted from the `orphan` warning, with the recorded reason.

        `owner` plus `stale` is a review queue: the documents one steward is
        responsible for that are past their type's review cadence. Staleness is
        applied before `limit`, so `stale=True, limit=10` means ten stale
        documents, not the stale ones among the first ten.

        `code` is the question in the other direction — which documents claim to
        govern the files you are about to change. Pass the paths you are
        editing; a path that no longer exists still finds its documents, which
        is the case that matters when a change deletes code.

        Args:
            types: Document types to include (e.g. ["decision", "issue"]).
            statuses: Statuses to include.
            tags: Registered tag keys — a document must carry all of them.
            owner: The staleness steward to filter by.
            stale: Only documents past their type's review cadence. Measured
                against `verified`, else the date a verification was `revoked`,
                else `created` — never the last edit. Only
                `update(verified=True)` clears an entry; editing the title,
                description or body of a verified document withdraws the stamp
                and restarts the cadence from that day.
            code: Paths to find governing documents for; any match counts.
            include_archived: Also return archived documents.
            include_inactive: Also return documents in an inactive status.
            limit: Page size.
            offset: How many documents to skip.
            stores: Extra store paths to read alongside this one, for this call.
        """
        return run.many(
            "query",
            {
                "types": types or [],
                "statuses": statuses or [],
                "tags": tags or [],
                "owner": owner,
                "stale": stale,
                "expr": expr,
                "code": code or [],
                "include_archived": include_archived,
                "include_inactive": include_inactive,
                "limit": limit,
                "offset": offset,
                STORES_KEY: resolve_extra(stores or []),
            },
        )

    @mcp.tool(annotations=_READ_ONLY)
    def docir_get(
        doc_id: str | None = None,
        section: str | None = None,
        doc_ids: list[str] | None = None,
        stores: list[str] | None = None,
    ) -> dict[str, Any]:
        """Fetch documents in full — whole bodies, or single sections of them.

        The only read path that returns a body. Reach for it after skeletons
        from `docir_context` / `docir_search` / `docir_query` tell you which
        documents are worth the tokens.

        **Pass `doc_ids` whenever you want more than one.** Reading five
        documents with five calls costs five turns; one call costs one, and the
        reply is the same content. There is no penalty for batching.

        Prefer sections on a long document: architecture notes here run to tens
        of thousands of characters, and one section is usually the part that
        answers you. An unknown heading is an error listing the ones that exist,
        so you can find the right name without fetching the whole body first.

        Args:
            doc_id: One document id (e.g. "adr-3f9a2b1c7d4e"). Answers with that
                document. Use `doc_ids` instead for two or more.
            section: A heading. Returns that heading and the text under it.
                Applies to `doc_id`; with `doc_ids`, write the heading into each
                address instead.
            doc_ids: Several addresses, read in one request. Each is an id, or
                `"<id>#<heading>"` for one section of it — which is exactly what
                a hit's `matched_section` gives you. Answers with
                `{"documents": [...], "missing": [{"ref", "error"}]}`: an id that
                no longer exists, or a heading that does not, is reported beside
                the documents that did resolve rather than failing the request.
            stores: Extra store paths to search alongside this one. A federated
                hit names its `store`; this is how you then read it.
        """
        if doc_ids:
            return run.one(
                "get",
                {"doc_ids": doc_ids, STORES_KEY: resolve_extra(stores or [])},
            )
        return run.one(
            "get",
            {
                "doc_id": doc_id,
                "section": section,
                STORES_KEY: resolve_extra(stores or []),
            },
        )

    @mcp.tool(annotations=_READ_ONLY)
    def docir_schema() -> dict[str, Any]:
        """The merged schema: valid types, statuses, transitions, relation kinds.

        This is what validation enforces, so read it before a first write. A
        status or relation kind it does not list is refused, not corrected.
        """
        return cast(dict[str, Any], trim(describe_schema()))

    @mcp.tool(annotations=_READ_ONLY)
    def docir_tag_list(limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """The registered tag vocabulary.

        Only these keys may appear on a document; an unregistered tag is a
        refused write, so read this before tagging.

        Args:
            limit: Page size.
            offset: How many tags to skip.
        """
        return run.many("tag_list", {"limit": limit, "offset": offset})

    # -- write path ---------------------------------------------------------

    @mcp.tool
    def docir_add(
        # Named `type` to match the frontmatter field and the CLI flag; a
        # different name here would be a third spelling of one concept.
        type: str,
        title: str,
        description: str,
        body: str = "",
        tags: list[str] | None = None,
        related: list[str] | None = None,
        status: str | None = None,
        owner: str | None = None,
        code: list[str] | None = None,
        isolated: str | None = None,
        wait_embeddings: bool = False,
    ) -> dict[str, Any]:
        """Create a document. The single write path — never write the file yourself.

        The id is allocated for you and returned; ids are never chosen by the
        caller. The write is refused outright on an unknown type, an undeclared
        status, an unregistered tag or a `related` id that does not exist.

        Args:
            type: A type from `docir_schema` (e.g. "decision").
            title: One line, the document's name.
            description: One sentence — this is what search and ranked results
                show instead of the body, so make it say what the document is.
            body: The markdown body.
            tags: Registered tag keys — see `docir_tag_list`.
            related: Typed edges, each "<id>" or "<id>:<kind>" (e.g.
                "adr-3f9a2b1c7d4e:supersedes"). A bare id means `relates_to`.
            status: Initial status; omit for the type's default.
            owner: Who vouches for this document staying true.
            code: Repo-relative globs naming the code this document governs
                (e.g. "src/docir/platform/persistence/**"). Only the shape is
                checked: a pattern may name code that does not exist yet.
            isolated: Why this document is meant to carry no relations, which
                exempts it from the `orphan` warning. Set it only when the
                isolation is the conclusion — an edge is the usual answer.
            wait_embeddings: Block until the vector is computed. Only needed
                when the very next call is a `docir_context` that must find it.
        """
        return run.one(
            "add",
            {
                "type": type,
                "title": title,
                "description": description,
                "body": body,
                "tags": tags or [],
                "related": related or [],
                "status": status,
                "owner": owner,
                "code": code or [],
                "isolated": isolated,
                "wait_embeddings": wait_embeddings,
            },
        )

    @mcp.tool
    def docir_update(
        doc_id: str,
        status: str | None = None,
        set_type: str | None = None,
        set_title: str | None = None,
        set_description: str | None = None,
        set_tags: list[str] | None = None,
        set_related: list[str] | None = None,
        set_owner: str | None = None,
        set_code: list[str] | None = None,
        set_isolated: str | None = None,
        verified: bool = False,
        clear_verified: bool = False,
        append_section: str | None = None,
        replace_section: str | None = None,
        remove_section: str | None = None,
        replace_body: str | None = None,
        body: str | None = None,
        force: bool = False,
        override: bool = False,
        wait_embeddings: bool = False,
    ) -> dict[str, Any]:
        """Edit a document: a metadata patch, a body edit, or both.

        Every edit but `replace_body` is applied to the document as it is on
        disk, so it composes with an out-of-band change. `replace_body` throws
        the on-disk body away, so it needs `force` every time, and is refused
        outright — `force` or not — if the file has changed since it was
        indexed. Prefer `append_section` / `replace_section`; at most one body
        edit mode per call.

        Args:
            doc_id: The document to edit.
            status: New status. Must be a legal transition from the current one.
            set_type: Retype the document. The id never changes, prefix
                included — it is the corpus's only address. The file moves to
                the new type's directory. The status carries over if the new
                type declares it; if it does not, pass `status` too.
            set_title: Replace the title.
            set_description: Replace the description.
            set_tags: Replace the tag list wholesale (not a merge).
            set_related: Replace the edges wholesale, each "<id>" or
                "<id>:<kind>".
            set_owner: Replace the staleness steward.
            set_code: Replace the governed globs wholesale (not a merge); an
                empty list clears them.
            set_isolated: Record why this document is meant to carry no
                relations, which exempts it from the `orphan` warning. Pass ""
                to withdraw the exemption and put it back in the queue.
                Prefer `set_related` — an exemption is for
                the document that is isolated by design, not the one nobody has
                got round to wiring.
            verified: Stamp today as the last-verified date. Assert this only
                when a human has actually re-read the document — it is the one
                trust signal docir offers. Pass it alongside a body edit to keep
                the stamp: that is "I rewrote it and re-read it", and without it
                the edit withdraws the verification by itself. It also digests
                the text it covers, so `check` reports a stamp left standing over
                text edited around the CLI.
            clear_verified: Withdraw the standing verification and leave no
                review window: the document ages from `created` again, as one
                nobody ever verified does. The way back from a stamp asserting a
                review nobody did. Refused together with `verified`, and refused
                when no verification is standing.
            append_section: Heading to append `body` under.
            replace_section: Heading whose section `body` replaces.
            remove_section: Heading to delete, with the text under it. Passing
                `body` alongside it is refused, not ignored. The way out of a
                body that spells one heading twice —
                `replace_section` keeps the first heading line by contract, so it
                cannot undo one, and a repeated heading resolves to the first.
            replace_body: New markdown replacing the whole body.
            body: The text for `append_section` / `replace_section`. Both write
                the heading line themselves, so this is only what goes *under*
                the heading: text opening with that same heading — what
                `docir_get(section=)` returns — is refused.
            force: Required by `replace_body`, and only by it. Confirms you
                mean to discard the whole existing body.
            override: Force an illegal status transition. Last resort.
            wait_embeddings: Block until the vector is recomputed.
        """
        payload: dict[str, object] = {
            "doc_id": doc_id,
            "status": status,
            "set_type": set_type,
            "set_title": set_title,
            "set_description": set_description,
            "set_tags": set_tags,
            "set_related": set_related,
            "set_owner": set_owner,
            "set_code": set_code,
            "set_isolated": set_isolated,
            "mark_verified": verified,
            "clear_verified": clear_verified,
            "remove_section": remove_section,
            "body": body,
            "replace_body": replace_body,
            "force": force,
            "allow_transition_override": override,
            "wait_embeddings": wait_embeddings,
        }
        if append_section is not None:
            payload["append_section"] = [append_section, body or ""]
        if replace_section is not None:
            payload["replace_section"] = [replace_section, body or ""]
        return run.one("update", payload)

    @mcp.tool
    def docir_archive(doc_id: str) -> dict[str, Any]:
        """Soft-remove a document from the default read paths.

        Reversible with `docir_unarchive`, and preferred over `docir_delete`:
        the file and its edges survive.

        Args:
            doc_id: The document to archive.
        """
        return run.one("archive", {"doc_id": doc_id})

    @mcp.tool
    def docir_unarchive(doc_id: str) -> dict[str, Any]:
        """Return an archived document to the default read paths.

        Args:
            doc_id: The document to restore.
        """
        return run.one("unarchive", {"doc_id": doc_id})

    @mcp.tool(annotations=_DESTRUCTIVE)
    def docir_delete(doc_id: str, force: bool = False) -> dict[str, Any]:
        """Delete a document and its file. Prefer `docir_archive`.

        Refused while other documents link to it, unless `force`, which strips
        the edge from every referencing document in the same transaction and
        returns their ids — so a delete can never leave a dangling reference.

        Args:
            doc_id: The document to delete.
            force: Also strip the inbound edges. Cannot be undone.
        """
        return run.one("delete", {"doc_id": doc_id, "force": force})

    # -- tag registry -------------------------------------------------------

    @mcp.tool
    def docir_tag_add(key: str, description: str) -> dict[str, Any]:
        """Register a tag before any document may use it.

        Args:
            key: The tag key (lowercase, dash-separated).
            description: What the tag means — this is the vocabulary's contract.
        """
        return run.one("tag_add", {"key": key, "description": description})

    @mcp.tool
    def docir_tag_rename(old: str, new: str, merge: bool = False) -> dict[str, Any]:
        """Rename a tag and rewrite every document carrying it.

        Args:
            old: The current key.
            new: The replacement key.
            merge: Allow `new` to already exist, folding the two together.
        """
        return run.one("tag_rename", {"old": old, "new": new, "merge": merge})

    @mcp.tool(annotations=_DESTRUCTIVE)
    def docir_tag_remove(key: str, force: bool = False) -> dict[str, Any]:
        """Retire a tag from the registry.

        Refused while documents still carry it, unless `force`, which strips it
        from each of them and returns their ids.

        Args:
            key: The tag to remove.
            force: Also strip the tag from the documents using it.
        """
        return run.one("tag_remove", {"key": key, "force": force})

    # -- maintenance --------------------------------------------------------

    @mcp.tool(annotations=_READ_ONLY)
    def docir_check() -> list[dict[str, Any]]:
        """Structural findings over the corpus. Read the severity.

        `error` means the corpus is broken — a duplicate id hiding a document,
        an edge pointing at nothing, a file that will not parse. `warning`
        describes shape or age (orphan, cycle, layering, staleness), and an
        orphan is the normal state of a new document, not a defect.

        `orphan` reads `related:` alone. Naming an id in a paragraph does not
        clear it — a triage that lists the orphans is exactly the prose that
        would. Close each one with an edge (`docir_update(set_related=...)`),
        or, when standing alone is the conclusion, with
        `docir_update(set_isolated="<why>")`; `docir_query(expr="isolated")`
        lists every exemption and `set_isolated=""` withdraws one.
        """
        return run.many("check", {})

    @mcp.tool(annotations=_READ_ONLY)
    def docir_schema_drift() -> dict[str, Any]:
        """How the active schema differs from the one the index was built against.

        One line per change (`+type test_plan`, `type decision: required [] ->
        ['owner']`). The types and cadences come from the installed docir as
        much as from `docs-schema.yaml`, so an upgrade can move them with no
        edit to the file and nothing in `git diff` to read — this is that diff.
        Empty means nothing moved, or that the store has no baseline yet.
        """
        return run.one("schema_drift", {})

    @mcp.tool(annotations=_READ_ONLY)
    def docir_store_status() -> dict[str, Any]:
        """Whether this store's derived index is current, and worth trusting.

        The store half of `docir doctor`: how many documents are indexed, the
        docir version that built the index when it is not the running one
        (`stale_index_build`), how the schema has moved since
        (`schema_drift`), which embedding model reads score with, and how many
        documents have no current vector for it (`embeddings_pending`).

        Call it when a read answers something that looks wrong. A stale build
        stamp or a pending queue means the index is behind the files — reads
        still answer, they answer from older state, and nothing else in a
        result says so. `docir_reindex` fixes the first, `docir_embed_flush`
        the second.

        It says nothing about the corpus; `docir_check` owns that. The rest of
        `docir doctor` — the daemon, this shell's environment variables, which
        store the working directory resolved to — is not askable here: those
        are facts about the client process, and this one runs in the daemon.
        """
        return run.one("store_status", {})

    @mcp.tool
    def docir_check_fix() -> dict[str, Any]:
        """Repair what needs no guess: duplicate ids and dangling edges.

        Re-issues the newer of two files sharing an id (the older keeps it —
        existing edges were written against it) and drops edges pointing at
        nothing. Malformed files and unknown types are left alone and reported
        under `remaining` — each needs somebody to read it and decide. Does not
        advance any `updated` date: a mechanical repair is not a human
        re-verification.
        """
        return run.one("repair", {})

    @mcp.tool(annotations=_READ_ONLY)
    def docir_lint() -> list[dict[str, Any]]:
        """Advisory heuristics: near-duplicate documents, scope creep.

        Tier 2 — suggestions, never rules. Nothing here blocks a write.
        """
        return run.many("lint", {})

    @mcp.tool(annotations=_READ_ONLY)
    def docir_bench(
        tasks: list[dict[str, Any]],
        limit: int = 5,
        expand: int = 2,
    ) -> dict[str, Any]:
        """Score this store's retrieval against tasks whose answers you know.

        Each task is `{"id": ..., "task": "...", "relevant": ["adr-...", ...]}`
        — the document **ids** a reader would need. Ids rather than paths,
        because a retitle moves the filename and a retype moves the directory.

        Three rows come back. `context` is the shipped read path; `context
        --expand 0` removes graph expansion, which lifts every embedder and
        hides the difference between them, so the pair isolates the semantic
        signal; `search` is full-text alone, the floor semantics must beat.

        Ids no document carries come back under `unresolved`, and a task whose
        ids were all unknown under `dropped`. Neither is scored: removing an id
        quietly would shrink recall's denominator and raise the score for the
        wrong reason.

        A measurement, not a check. Nothing here blocks a write, and a fixture
        is one annotator's opinion of what is relevant.
        """
        return run.one("bench", {"tasks": tasks, "limit": limit, "expand": expand})

    @mcp.tool
    def docir_reindex(changed_only: bool = False) -> dict[str, Any]:
        """Rebuild the derived index from the markdown files.

        The recovery path after anything edits the files out of band (a branch
        merge, a hand edit, a fresh clone — the index is gitignored). The files
        are canonical; this makes the index agree with them again.

        Every document it re-saves is re-embedded before it returns, and
        `embeddings_recomputed` says how many — so this is also how you
        recompute every vector.

        Args:
            changed_only: Only reindex files whose content hash moved.
        """
        return run.one("reindex", {"changed_only": changed_only})

    @mcp.tool
    def docir_embed_flush() -> dict[str, Any]:
        """Compute every pending embedding now, and report how many.

        Embeddings are the one deferred piece: a write flags the vector dirty
        and returns. Flush when the next `docir_context` must see a document
        you just wrote.
        """
        return run.one("embed_flush", {})

    return mcp
