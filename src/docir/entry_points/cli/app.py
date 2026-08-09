"""The ``docir`` Typer application — the single entry point / agent contract.

Each command assembles a JSON payload and runs it through the executor (daemon
or in-process), then renders the response with Rich (or as raw JSON for
agents). The CLI is a thin client: all business logic lives in the use cases.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from typer.main import get_command

from docir import __version__
from docir.config.settings import Settings, new_store_home
from docir.entry_points.cli import rendering
from docir.entry_points.cli.body_input import resolve_body
from docir.entry_points.cli.runner import (
    CliState,
    execute,
    execute_with,
    get_state,
    help_wants_json,
    run_local,
    set_state,
    use_json,
    with_executor,
)
from docir.entry_points.composition import (
    DEFAULT_INIT_ID_STYLE,
    InitResult,
    UpgradeResult,
    initialize_store,
    upgrade_store,
)
from docir.entry_points.daemon.cmds import daemon_app
from docir.entry_points.mcp.cmds import mcp_app
from docir.modules.agents.api import (
    AGENT_NAMES,
    DEFAULT_AGENTS,
    InstalledFile,
    InstallRequest,
    SetupResult,
    UpdateRequest,
    build_agent_service,
)
from docir.modules.documents.api import (
    DEFAULT_CONTEXT_EXPAND,
    ID_STYLES,
    PROFILE_NAMES,
    describe_schema,
    load_schema,
)
from docir.modules.publishing.api import PublishRequest, PublishResult, build_site_builder
from docir.modules.release.api import ReleaseStatus, build_release_service
from docir.modules.tags.api import DEFAULT_TAG_PAGE
from docir.platform.errors import ValidationError

#: How many documents one `build` enumerates. `query` pages, and a site build
#: wants the whole corpus rather than a page of it — high enough that no real
#: store hits it, finite so a runaway store cannot exhaust memory silently.
_BUILD_PAGE_LIMIT = 10_000

app = typer.Typer(
    help="Doc-Index CLI — git-backed markdown documents with a semantic index.",
    no_args_is_help=True,
    add_completion=False,
)
tag_app = typer.Typer(help="Manage the tag registry.", no_args_is_help=True)
agent_app = typer.Typer(help="Install AI-assistant instructions for docir.", no_args_is_help=True)
schema_app = typer.Typer(help="Inspect and validate the document schema.", no_args_is_help=True)
self_app = typer.Typer(help="Maintain the docir installation itself.", no_args_is_help=True)
app.add_typer(tag_app, name="tag")
app.add_typer(agent_app, name="agent")
app.add_typer(schema_app, name="schema")
app.add_typer(self_app, name="self")
app.add_typer(daemon_app, name="daemon")
app.add_typer(mcp_app, name="mcp")


@app.callback()
def main_callback(
    home: Annotated[
        str | None,
        typer.Option(
            "--home",
            help="Store to use (default: $DOCIR_HOME, a discovered .docir, or ~/.docir).",
        ),
    ] = None,
    no_daemon: Annotated[
        bool, typer.Option("--no-daemon", help="Run in-process, bypass the daemon.")
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Force compact JSON (already the default when piped)."),
    ] = False,
    pretty: Annotated[
        bool, typer.Option("--pretty", help="Force rich tables even when output is piped.")
    ] = False,
    no_trim: Annotated[
        bool,
        typer.Option("--no-trim", help="Keep empty fields and full-precision scores in JSON."),
    ] = False,
) -> None:
    """Resolve global options and initialize CLI state."""
    settings = Settings.resolve(home, use_daemon=False if no_daemon else None)
    set_state(CliState(settings=settings, json_output=json_output, pretty=pretty, trim=not no_trim))


@app.command()
def version() -> None:
    """Print the docir version."""
    rendering.render_message(__version__)


@app.command()
def init(
    directory: Annotated[
        Path | None,
        typer.Argument(help="Project directory to initialize (default: the current one)."),
    ] = None,
    profiles: Annotated[
        str | None,
        typer.Option(
            "--profiles", help=f"Comma-separated schema profiles ({', '.join(PROFILE_NAMES)})."
        ),
    ] = None,
    id_style: Annotated[
        str,
        typer.Option(
            "--id-style",
            help=(
                f"How ids are minted ({', '.join(ID_STYLES)}). "
                "random (default) is collision-free across branches; "
                "sequential mints readable numbers like adr-0007."
            ),
        ),
    ] = DEFAULT_INIT_ID_STYLE,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Regenerate the .gitignore, and an unmodified docs-schema.yaml.",
        ),
    ] = False,
    force_schema: Annotated[
        bool,
        typer.Option(
            "--force-schema",
            help="Also replace a docs-schema.yaml you have customised (cannot be undone).",
        ),
    ] = False,
) -> None:
    """Create a project-local docir store (./.docir) that commands auto-discover.

    Scopes this repo's docs to the repo instead of the global ~/.docir store:
    commands run anywhere inside the tree find the store by walking up for
    .docir (the git model). Commit .docir/docs/ and .docir/docs-schema.yaml; the
    derived index is gitignored for you.

    Ids default to the collision-resistant `random` style, because a repo store
    is shared: two branches using `sequential` can each mint adr-0007 and only
    find out at merge. Pass --id-style sequential for readable numbers.

    The store goes in DIRECTORY/.docir. The global --home names a store path
    directly, so `docir --home /srv/docs init` puts it exactly there; passing
    both is refused, since they disagree about where the store is.

    --force regenerates the .gitignore and an untouched docs-schema.yaml. A
    schema you have edited is kept and reported, not replaced: it is the one file
    in the store that cannot be rebuilt from the documents, and re-running init
    to refresh the .gitignore used to destroy it silently. Pass --force-schema to
    replace that too.
    """
    # via run_local so the conflict is a domain error, not a traceback.
    home = run_local(lambda: _init_home(directory))
    settings = Settings.resolve(home=home, use_daemon=False)
    result = run_local(
        lambda: initialize_store(
            settings,
            profiles=_split_csv(profiles),
            force=force,
            force_schema=force_schema,
            id_style=id_style,
        )
    )
    _emit_init(result)


@app.command()
def build(
    out: Annotated[
        Path,
        typer.Option("--out", help="Directory to write the site into (regenerated)."),
    ],
    title: Annotated[str, typer.Option("--title", help="Site heading.")] = "Documentation",
    logo: Annotated[
        Path | None,
        typer.Option("--logo", help="Image for the mark and favicon (default: docir's)."),
    ] = None,
    include_archived: Annotated[
        bool, typer.Option("--include-archived", help="Also publish archived documents.")
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite a directory docir did not build."),
    ] = False,
) -> None:
    """Render the store as a self-contained static site.

    One HTML page per document plus an index, with no external requests — it
    works from file:// and publishes to GitHub Pages or S3 unchanged. Everything
    docir knows is on the page: the typed relation graph in both directions, the
    staleness flag, tags, owner and dates.

    The site is a derived artifact, like the index: --out is regenerated on every
    build, so a document deleted from the store cannot survive as an orphaned
    page. A directory that is not empty and was not built by docir is refused
    unless you pass --force.

    Inactive documents (a superseded decision, a resolved issue) are published:
    the point of a browsable corpus is that a reader can follow a decision to the
    one that replaced it. Archived documents are not, unless you ask.

    The top-left mark and the favicon are docir's own unless you pass --logo
    (svg/png/jpg/webp/gif), which sets both — one flag brands the whole site. It
    is inlined into every page so the site stays self-contained, which is why a
    logo has a size limit: export it at header size.
    """
    _warn_on_global_fallback()
    state = get_state()
    skeletons = execute(
        "query",
        {
            "limit": _BUILD_PAGE_LIMIT,
            "include_archived": include_archived,
            "include_inactive": True,
        },
    )
    ids = [str(row["id"]) for row in _as_mappings(skeletons) if row.get("id")]
    # One `get` per document, because bodies are deliberately absent from every
    # list path (the skeleton contract). A site build is an offline operation
    # run occasionally, so N round trips is the right trade against widening a
    # read path that exists to stay narrow.
    documents = [
        mapping for doc_id in ids for mapping in _as_mappings([execute("get", {"doc_id": doc_id})])
    ]
    result = run_local(
        lambda: build_site_builder().build(
            PublishRequest(
                out=out,
                documents=documents,
                title=title,
                version=__version__,
                logo=logo,
                force=force,
            )
        )
    )
    _emit_build(result, settings_home=str(state.settings.home))


# -- schema introspection ---------------------------------------------------
#
# Both commands run in-process, bypassing the daemon/dispatcher, because
# ``build_container`` loads the schema: a file too broken to start the store
# would otherwise make the very commands meant to diagnose it unreachable.


@schema_app.command("show")
def schema_show() -> None:
    """Print the fully merged schema (core + profiles + inline overrides).

    This is what validation actually enforces — the raw docs-schema.yaml only
    lists the ingredients.
    """
    settings = get_state().settings
    schema = run_local(lambda: load_schema(settings.schema_path))
    _emit_schema(describe_schema(schema))


@schema_app.command("validate")
def schema_validate() -> None:
    """Check docs-schema.yaml parses and merges cleanly; exit nonzero if not.

    Rejects a status name that no type declares — a transition target, a
    `default_status`, or an `inactive_statuses` entry. That typo used to load
    happily and surface later as "invalid transition 'open' -> 'closed'",
    naming a status that IS declared and pointing at the write rather than the
    schema.

    A "dead end" warning (a live status with no outgoing transitions) was built
    and then dropped: measured against the bundled profiles it fired on 5 of the
    15 shipped types — `release_note.published`, `postmortem.published`,
    `experiment.complete`, `hypothesis.supported`, `obligation.breached` — every
    one a correct terminal state for a document that stays relevant. A warning
    that fires on the product's own defaults is issue-40d1792bc9f9 again.
    """
    settings = get_state().settings
    schema = run_local(lambda: load_schema(settings.schema_path))
    data = {"valid": True, "path": str(settings.schema_path), "types": len(schema.types)}
    state = get_state()
    if use_json(state):
        rendering.emit_json(data, trim=state.trim)
    else:
        rendering.render_schema_valid(str(settings.schema_path), len(schema.types))


# -- write path -------------------------------------------------------------


@app.command()
def add(
    type: Annotated[str, typer.Option("--type", help="Document type.")],
    title: Annotated[str, typer.Option("--title")],
    description: Annotated[str, typer.Option("--description")],
    tags: Annotated[str | None, typer.Option("--tags", help="Comma-separated.")] = None,
    related: Annotated[
        str | None,
        typer.Option("--related", help="Comma-separated <id> or <id>:<kind> typed edges."),
    ] = None,
    status: Annotated[str | None, typer.Option("--status")] = None,
    owner: Annotated[str | None, typer.Option("--owner", help="Steward for staleness.")] = None,
    code: Annotated[
        str | None,
        typer.Option("--code", help="Comma-separated repo-relative globs this document governs."),
    ] = None,
    id: Annotated[
        str | None,
        typer.Option(
            "--id",
            help="Adopt an existing id (migrating a numbered corpus) instead of allocating.",
        ),
    ] = None,
    body: Annotated[str | None, typer.Option("--body")] = None,
    body_file: Annotated[Path | None, typer.Option("--body-file")] = None,
    stdin: Annotated[bool, typer.Option("--stdin")] = False,
    wait_embeddings: Annotated[bool, typer.Option("--wait-embeddings")] = False,
) -> None:
    """Create a new document with valid frontmatter.

    Ids are allocated for you. `--id` adopts one instead, for the single case it
    exists for: migrating a repository whose ADRs are already numbered, where
    dropping `adr-0007` breaks every historical cross-reference. It is refused if
    the id is taken or its prefix does not match the type, and the next
    allocation still lands past it.

    `--code` records the code this document governs, as repo-relative globs
    (`src/docir/platform/persistence/**`). Only the shape is validated — a
    pattern that matches nothing today is allowed, because a decision is often
    written before the code it decides, or after that code moved.
    """
    payload: dict[str, object] = {
        "type": type,
        "title": title,
        "description": description,
        "tags": _split_csv(tags),
        "related": _split_csv(related),
        "status": status,
        "owner": owner,
        "code": _split_csv(code),
        "id": id,
        "body": resolve_body(body, body_file, stdin),
        "wait_embeddings": wait_embeddings,
    }
    _warn_on_global_fallback()
    _emit_document(execute("add", payload))


@app.command()
def update(
    doc_id: Annotated[str, typer.Argument(help="Document id.")],
    status: Annotated[str | None, typer.Option("--status")] = None,
    set_title: Annotated[str | None, typer.Option("--set-title")] = None,
    set_description: Annotated[str | None, typer.Option("--set-description")] = None,
    set_tags: Annotated[str | None, typer.Option("--set-tags")] = None,
    set_related: Annotated[
        str | None,
        typer.Option("--set-related", help="Comma-separated <id> or <id>:<kind> typed edges."),
    ] = None,
    set_owner: Annotated[str | None, typer.Option("--set-owner", help="Staleness steward.")] = None,
    set_code: Annotated[
        str | None,
        typer.Option(
            "--set-code",
            help="Comma-separated repo-relative globs this document governs "
            '(pass "" to clear them).',
        ),
    ] = None,
    verified: Annotated[
        bool, typer.Option("--verified", help="Stamp today as the last-verified date.")
    ] = False,
    append_section: Annotated[str | None, typer.Option("--append-section")] = None,
    replace_section: Annotated[str | None, typer.Option("--replace-section")] = None,
    replace_body: Annotated[bool, typer.Option("--replace-body")] = False,
    body: Annotated[str | None, typer.Option("--body")] = None,
    body_file: Annotated[Path | None, typer.Option("--body-file")] = None,
    stdin: Annotated[bool, typer.Option("--stdin")] = False,
    force: Annotated[bool, typer.Option("--force")] = False,
    override: Annotated[
        bool,
        typer.Option(
            "--override",
            help="Force an illegal status transition (warns; last resort).",
        ),
    ] = False,
    wait_embeddings: Annotated[bool, typer.Option("--wait-embeddings")] = False,
) -> None:
    """Update a document (metadata patch and/or a body edit)."""
    body_text = resolve_body(body, body_file, stdin, default="")
    payload: dict[str, object] = {
        "doc_id": doc_id,
        "status": status,
        "set_title": set_title,
        "set_description": set_description,
        "set_tags": None if set_tags is None else _split_csv(set_tags),
        "set_related": None if set_related is None else _split_csv(set_related),
        "set_owner": set_owner,
        "set_code": None if set_code is None else _split_csv(set_code),
        "mark_verified": verified,
        "append_section": [append_section, body_text] if append_section else None,
        "replace_section": [replace_section, body_text] if replace_section else None,
        "replace_body": body_text if replace_body else None,
        "force": force,
        "allow_transition_override": override,
        "wait_embeddings": wait_embeddings,
    }
    _warn_on_global_fallback()
    data = execute("update", payload)
    forced = data.get("forced_transition") if isinstance(data, dict) else None
    if forced:
        # Loud at the moment of the bypass, but not written to the file: git
        # records the status change, and docir has no actors to attribute it to.
        rendering.render_warning(f"forced illegal transition {forced}")
    _emit_document(data)


@app.command()
def archive(doc_id: Annotated[str, typer.Argument()]) -> None:
    """Soft-remove a document from active search."""
    _emit_document(execute("archive", {"doc_id": doc_id}))


@app.command()
def unarchive(doc_id: Annotated[str, typer.Argument()]) -> None:
    """Restore an archived document to active search."""
    _emit_document(execute("unarchive", {"doc_id": doc_id}))


@app.command()
def delete(
    doc_id: Annotated[str, typer.Argument()],
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    """Hard-delete a document's file and index rows.

    A forced delete also strips the edge from every document that referenced this
    one, and names them — a delete that silently rewrites other people's files
    would be worse than one that refuses.
    """
    data = execute("delete", {"doc_id": doc_id, "force": force})
    raw = data.get("unlinked") if isinstance(data, dict) else None
    unlinked = [str(item) for item in raw] if isinstance(raw, list) else []
    message = f"deleted {doc_id}"
    if unlinked:
        message += f"; unlinked from {', '.join(unlinked)}"
    _emit_or_message(data, message)


# -- read path --------------------------------------------------------------


@app.command()
def get(
    doc_id: Annotated[str, typer.Argument()],
    section: Annotated[
        str | None,
        typer.Option(
            "--section",
            help="Return only this heading's section instead of the whole body.",
        ),
    ] = None,
) -> None:
    """Return one document in full, or just one section of it.

    --section takes a heading and returns that heading plus the text under it —
    the same span --replace-section would overwrite. It is the paired read for
    `context`: a long document can rank on one of its sections, and this reads
    that section without paying for a body that is often ten times its size. An
    unknown heading is an error listing the ones that exist.
    """
    _warn_on_global_fallback()
    _emit_document(execute("get", {"doc_id": doc_id, "section": section}))


@app.command()
def query(
    type: Annotated[list[str] | None, typer.Option("--type")] = None,
    status: Annotated[list[str] | None, typer.Option("--status")] = None,
    tag: Annotated[list[str] | None, typer.Option("--tag")] = None,
    include_archived: Annotated[bool, typer.Option("--include-archived")] = False,
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
    limit: Annotated[int, typer.Option("--limit")] = 50,
    offset: Annotated[int, typer.Option("--offset", help="Rows to skip; page with --limit.")] = 0,
) -> None:
    """Structured metadata filtering.

    `--owner` and `--stale` are the review queue: `--owner platform-team --stale`
    is "what does this team need to re-verify". `--stale` is applied before
    `--limit`, so the limit counts stale documents rather than truncating the
    set they were selected from.

    Staleness only says a document is past its type's review cadence — nobody
    has vouched for it recently. It is not a claim that the content is wrong.
    Confirm with `docir update <id> --verified` once you have re-read it.

    `--code <path>` answers the other direction: which documents declared they
    govern this file. Repeat it to ask about several paths at once — the answer
    is any document matching any of them, which is what makes
    `docir query --code $(git diff --name-only main | tr '\\n' ' ')` the set of
    decisions a branch should be read against. The paths are matched against
    the patterns as text, so a file the branch *deleted* still finds its
    decisions. A document governing a directory governs what is in it.
    """
    payload: dict[str, object] = {
        "types": tuple(type or ()),
        "statuses": tuple(status or ()),
        "tags": tuple(tag or ()),
        "include_archived": include_archived,
        "include_inactive": _include_inactive(include_inactive, include_resolved),
        "owner": owner,
        "stale": stale,
        "code": tuple(code or ()),
        "limit": limit,
        "offset": offset,
    }
    _warn_on_global_fallback()
    _emit_document_list(execute("query", payload))


@app.command()
def search(
    text: Annotated[str, typer.Argument()],
    limit: Annotated[int, typer.Option("--limit")] = 20,
    offset: Annotated[int, typer.Option("--offset", help="Hits to skip; page with --limit.")] = 0,
    include_inactive: Annotated[
        bool,
        typer.Option("--include-inactive", help="Also return documents in an inactive status."),
    ] = False,
    include_resolved: Annotated[bool, typer.Option("--include-resolved", hidden=True)] = False,
) -> None:
    """Full-text search."""
    payload: dict[str, object] = {
        "text": text,
        "limit": limit,
        "offset": offset,
        "include_inactive": _include_inactive(include_inactive, include_resolved),
    }
    _warn_on_global_fallback()
    _emit_document_list(execute("search", payload))


@app.command()
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

    Two things it does not filter: documents with no current vector (a
    lexical-only hit, whose similarity is unknown rather than zero — run `docir
    embed --flush` if you need the floor to cover everything) and graph-reached
    neighbours, which are included because a selected document points at them,
    not because they scored.
    """
    payload: dict[str, object] = {
        "task": task,
        "limit": limit,
        "expand": expand,
        "include_inactive": _include_inactive(include_inactive, include_resolved),
        "min_score": min_score,
    }
    _warn_on_global_fallback()
    _emit_document_list(execute("context", payload))


# -- tags -------------------------------------------------------------------


@tag_app.command("add")
def tag_add(
    key: Annotated[str, typer.Argument()],
    description: Annotated[str, typer.Option("--description")],
) -> None:
    """Register a new tag."""
    data = execute("tag_add", {"key": key, "description": description})
    _emit_or_message(data, f"registered tag {key}")


@tag_app.command("list")
def tag_list(
    limit: Annotated[int, typer.Option("--limit")] = DEFAULT_TAG_PAGE,
    offset: Annotated[int, typer.Option("--offset", help="Tags to skip; page with --limit.")] = 0,
) -> None:
    """List registered tags, key-ordered, with a usage count each.

    `usage` counts the indexed documents carrying the tag, archived included —
    the same set `tag rm` refuses to remove over, so `0` means the tag is dead
    and `tag rm` will take it without --force.

    Paged: a page shorter than --limit means you have reached the end. There is
    no total in the response — it is a bare JSON array, and a wrapper to carry
    one would break every existing caller.
    """
    data = execute("tag_list", {"limit": limit, "offset": offset})
    state = get_state()
    if use_json(state):
        rendering.emit_json(data, trim=state.trim)
    else:
        rendering.render_tags(_as_list(data))


@tag_app.command("rename")
def tag_rename(
    old: Annotated[str, typer.Argument()],
    new: Annotated[str, typer.Argument()],
    merge: Annotated[
        bool,
        typer.Option("--merge", help="Fold `old` into an existing `new` instead of failing."),
    ] = False,
) -> None:
    """Rename a tag across the registry and all documents.

    Renaming onto a tag that already exists is refused unless you pass --merge,
    which folds the two together: every document carrying `old` gets `new`, a
    document carrying both keeps one, and `new`'s description survives. Without
    the flag the refusal stands — a merge discards a description, which is not
    what someone fixing a typo means.
    """
    data = execute("tag_rename", {"old": old, "new": new, "merge": merge})
    touched = data.get("documents") if isinstance(data, dict) else None
    count = len(touched) if isinstance(touched, list) else 0
    verb = "merged" if merge else "renamed"
    _emit_or_message(data, f"{verb} {old} -> {new} across {count} document(s)")


@tag_app.command("rm")
def tag_rm(
    key: Annotated[str, typer.Argument()],
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    """Remove a tag (blocked while in use unless forced)."""
    data = execute("tag_remove", {"key": key, "force": force})
    stripped = data.get("documents") if isinstance(data, dict) else None
    count = len(stripped) if isinstance(stripped, list) else 0
    message = f"removed tag {key}"
    if count:
        message += f"; stripped it from {count} document(s)"
    _emit_or_message(data, message)


# -- agent instructions -----------------------------------------------------


@agent_app.command("install")
def agent_install(
    directory: Annotated[Path, typer.Argument(help="Project directory.")] = Path("."),
    agent: Annotated[
        list[str] | None,
        typer.Option("--agent", help=f"Target(s): {', '.join(AGENT_NAMES)}. Repeatable."),
    ] = None,
    use_global: Annotated[
        bool,
        typer.Option("--global", help="Install the skill under ~/ instead of the project."),
    ] = False,
) -> None:
    """Install docir's agent instructions (a Claude skill and/or an AGENTS.md block)."""
    service = build_agent_service(__version__)
    request = InstallRequest(
        project_root=directory.resolve(),
        global_root=Path.home(),
        agents=tuple(agent) if agent else DEFAULT_AGENTS,
        use_global=use_global,
    )
    _emit_setup(run_local(lambda: service.install(request)))


@agent_app.command("update")
def agent_update(
    directory: Annotated[Path, typer.Argument(help="Project directory.")] = Path("."),
    agent: Annotated[
        list[str] | None,
        typer.Option("--agent", help="Add a target that isn't installed yet. Repeatable."),
    ] = None,
    use_global: Annotated[
        bool,
        typer.Option("--global", help="Refresh the skill under ~/ instead of the project."),
    ] = False,
) -> None:
    """Refresh already-installed agent instructions to the current docir version."""
    service = build_agent_service(__version__)
    request = UpdateRequest(
        project_root=directory.resolve(),
        global_root=Path.home(),
        agents=tuple(agent) if agent else (),
        use_global=use_global,
    )
    _emit_setup(run_local(lambda: service.update(request)))


# -- the installation itself -------------------------------------------------


@self_app.command("status")
def self_status(
    refresh: Annotated[
        bool,
        typer.Option("--refresh", help="Ask PyPI now instead of reading the last answer."),
    ] = False,
) -> None:
    """Report the docir installation: how it was installed, and whether it is current.

    A file read by default — the newest release is whatever was last fetched, and
    `checked_on` says when that was. `--refresh` asks PyPI (docir's only network
    call), and skips it when the answer is already from today.

    An absent `latest` means *unknown*, never "up to date": nothing has been
    checked, or the check could not reach the index. Set DOCIR_UPDATE_CHECK=1 to
    have the daemon keep it fresh and every command say so on stderr.
    """
    state = get_state()
    service = build_release_service(__version__, state.settings.release_cache_path)
    _emit_release_status(run_local(lambda: service.status(refresh=refresh)))


@self_app.command("upgrade")
def self_upgrade(
    directory: Annotated[Path, typer.Argument(help="Project directory.")] = Path("."),
    no_package: Annotated[
        bool,
        typer.Option("--no-package", help="Skip the package upgrade; only resync this store."),
    ] = False,
    upgraded_from: Annotated[
        str | None,
        typer.Option("--upgraded-from", hidden=True),
    ] = None,
) -> None:
    """Upgrade docir, then bring this store and its generated files in line with it.

    Four things in one command. It upgrades the package where docir owns its
    environment (a uv tool, a pipx install, a virtualenv) — and where it does
    not, says why and carries on. Then it rebuilds the index (derived,
    gitignored, and the only place the schema baseline and the build version are
    recorded), refreshes any installed agent instruction file to the running
    version, and reports what `check` still finds — `check` last, so the findings
    describe the state you are left in.

    The package step re-executes docir before doing the rest, because this
    process is the code being replaced: every step after the install would
    otherwise be the old build's work, starting with the stamp saying which
    version built the index. Pass --no-package to skip the install and only
    resync the store.
    """
    if not no_package and upgraded_from is None:
        _upgrade_the_package_then_restart()

    result = with_executor(
        lambda executor: upgrade_store(
            lambda command, payload: execute_with(executor, command, payload),
            project_root=directory.resolve(),
            version=__version__,
            upgraded_from=upgraded_from,
        )
    )
    _emit_upgrade(result)


# -- maintenance ------------------------------------------------------------


@app.command()
def reindex(
    changed: Annotated[
        bool,
        typer.Option(
            "--changed",
            help="Re-save only files whose content changed. Deletions are swept either way.",
        ),
    ] = False,
    embeddings: Annotated[bool, typer.Option("--embeddings")] = False,
) -> None:
    """Rebuild the index from the canonical files.

    Source files that do not parse are skipped and counted as
    `documents_skipped`: a rebuild that quietly dropped a document used to look
    exactly like one that did not. `docir check` names each such file.
    """
    data = execute("reindex", {"changed_only": changed, "embeddings": embeddings})
    skipped = data.get("documents_skipped") if isinstance(data, dict) else None
    if isinstance(skipped, int) and skipped:
        # stderr, so a captured JSON payload on stdout stays parseable.
        rendering.render_warning(
            f"{skipped} file(s) could not be parsed and are NOT in the index; "
            "run `docir check` to see which, then fix the frontmatter by hand."
        )
    _emit_or_message(data, str(data))


@app.command()
def check(
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Exit nonzero on error-severity findings (for CI)."),
    ] = False,
    strict_all: Annotated[
        bool,
        typer.Option("--strict-all", help="Exit nonzero on ANY finding, warnings included."),
    ] = False,
    fix: Annotated[
        bool,
        typer.Option("--fix", help="Repair what can be repaired (duplicate ids, dead edges)."),
    ] = False,
) -> None:
    """Tier 1 structural checks (cycles, orphans, layering, dangling, dup ids).

    Findings carry a severity. `error` means the corpus is broken — a duplicate
    id hiding a document, an edge pointing at nothing, a file that will not
    parse. `warning` describes shape or age: orphans, cycles, layering, staleness,
    unknown types, and a `code` glob that no longer matches anything (checked
    only when the store sits in a repository — there is nothing to resolve a
    pattern against otherwise).

    Pass --strict to gate a pre-merge / CI job: it exits 1 on errors only, which
    is what catches the duplicate ids and dangling references a branch merge
    introduces. Warnings do not fail the build — `orphan` fires for every
    document with no relations, so gating on them fails a healthy corpus.
    Use --strict-all if you really do want every finding to be fatal.
    """
    state = get_state()
    if fix:
        result = execute("repair", {})
        payload = result if isinstance(result, dict) else {}
        issues = _as_list(payload.get("remaining"))
        if use_json(state):
            rendering.emit_json(result, trim=state.trim)
        else:
            rendering.render_repair(_as_list(payload.get("actions")), issues)
    else:
        data = execute("check", {})
        issues = _as_list(data)
        if use_json(state):
            rendering.emit_json(data, trim=state.trim)
        else:
            rendering.render_findings(issues, empty="no structural issues")

    fatal = issues if strict_all else [i for i in issues if i.get("severity") == "error"]
    if (strict or strict_all) and fatal:
        raise typer.Exit(code=1)


@app.command()
def lint(
    deep: Annotated[bool, typer.Option("--deep")] = False,
) -> None:
    """Tier 2 advisory checks (content similarity, scope creep)."""
    if not deep:
        rendering.render_message("[dim]pass --deep to run advisory linting[/]")
        raise typer.Exit(code=0)
    data = execute("lint", {})
    state = get_state()
    if use_json(state):
        rendering.emit_json(data, trim=state.trim)
    else:
        rendering.render_findings(_as_list(data), empty="no advisory findings")


@app.command()
def embed(
    flush: Annotated[bool, typer.Option("--flush")] = False,
) -> None:
    """Force a synchronous embedding recompute of dirty documents."""
    if not flush:
        rendering.render_message("[dim]pass --flush to drain the embedding queue[/]")
        raise typer.Exit(code=0)
    data = execute("embed_flush", {})
    _emit_or_message(data, str(data))


# -- helpers ----------------------------------------------------------------


def _init_home(directory: Path | None) -> Path:
    """Resolve `init`'s store location, translating the rule's error.

    The rule itself lives in `config.settings.new_store_home`, beside
    `Settings.resolve`; this only supplies the flag and maps `ValueError` onto
    the error taxonomy, which `config` cannot depend on.
    """
    state = get_state()
    explicit = state.settings.home if state.settings.home_origin == "flag" else None
    try:
        return new_store_home(directory, explicit)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc


def _include_inactive(include_inactive: bool, include_resolved: bool) -> bool:
    """Resolve the flag and its deprecated alias, warning on the old spelling.

    The flag was `--include-resolved`, but the concept it controls is the
    schema's `inactive_statuses` — `rejected`/`superseded` for a decision,
    `deprecated` for architecture, `retired` for a policy. `resolved` is a
    status of only two of the fifteen shipped types, so the name described the
    minority case and gave a user querying decisions no reason to guess which
    flag surfaces superseded ones. The wire field was already `include_inactive`.

    The old spelling keeps working (hidden, undocumented) because it appears in
    scripts and in agent instructions installed before this release. The notice
    goes to stderr so a captured JSON payload on stdout is untouched.
    """
    if include_resolved:
        rendering.render_warning(
            "--include-resolved is deprecated; use --include-inactive "
            "(it covers every inactive status, not just `resolved`)."
        )
    return include_inactive or include_resolved


def _split_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _as_list(data: object) -> list[dict[str, object]]:
    # Tuples too, not just lists: ``dataclasses.asdict`` preserves the field's
    # container type, so a DTO with ``tuple`` fields arrives as a tuple in-process
    # and as a JSON array over the daemon. Accepting only ``list`` made the table
    # renderer silently show nothing while ``--json`` printed the full payload.
    if not isinstance(data, list | tuple):
        return []
    result: list[dict[str, object]] = []
    for item in data:
        if isinstance(item, dict):
            result.append({str(key): value for key, value in item.items()})
    return result


def _emit_document(data: object) -> None:
    state = get_state()
    if isinstance(data, dict):
        data = {**data, "store": str(state.settings.home)}
    if use_json(state):
        rendering.emit_json(data, trim=state.trim)
    elif isinstance(data, dict):
        rendering.render_document({str(key): value for key, value in data.items()})


def _warn_on_global_fallback() -> None:
    """Say so when a command is about to use the global store from inside a repo.

    Called on reads as well as writes. The read paths deliberately do *not* carry
    the `store` field the write paths do: it is one absolute path, identical for
    every row, and a list response has nowhere to put it once — per-row it would
    cost far more than the 4.7% one small field added to `context`. A stderr
    warning answers the same question ("am I reading the corpus I think I am?")
    for nothing on stdout.

    The reported `path` is relative to the *store*, so in a repository that was
    never `docir init`-ed it reads as repo-local while the file goes to the
    user's home directory — ungitted and invisible to teammates, with no error
    at any point. Only this case warns: outside a repository the global store is
    unambiguous, and warning on correct usage is how a check gets ignored.
    """
    settings = get_state().settings
    if not settings.is_unintended_global_fallback():
        return
    rendering.render_warning(
        f"using the global store {settings.home} — this directory is inside a "
        "git repository with no .docir/. Run `docir init` to scope docs to the repo, "
        "or set DOCIR_HOME to silence this."
    )


def _emit_document_list(data: object) -> None:
    state = get_state()
    if use_json(state):
        rendering.emit_json(data, trim=state.trim)
    else:
        rendering.render_document_list(_as_list(data))


def _emit_or_message(data: object, message: str) -> None:
    state = get_state()
    if use_json(state):
        rendering.emit_json(data, trim=state.trim)
    else:
        rendering.render_message(message)


def _emit_init(result: InitResult) -> None:
    data = {
        "home": str(result.home),
        "profiles": list(result.profiles),
        "id_style": result.id_style,
        "schema_written": result.schema_written,
        "gitignore_written": result.gitignore_written,
        "schema_preserved": result.schema_preserved,
        "enclosing_home": str(result.enclosing_home) if result.enclosing_home else "",
    }
    if result.enclosing_home is not None:
        # Legitimate (a monorepo subproject) and easy to do by accident, so it
        # is a warning rather than a refusal — but silence here means documents
        # split across two corpora with nothing pointing at the split.
        rendering.render_warning(
            f"there is already a docir store at {result.enclosing_home}; commands run "
            f"under {result.home.parent} will now use the new store, and the outer "
            "store's `docir check` will not see documents added here."
        )
    if result.schema_preserved:
        # Not an error, but --force did not do everything its name implies, and
        # silence here would read as "the schema was regenerated".
        rendering.render_warning(
            "kept your customised docs-schema.yaml (it cannot be rebuilt from the "
            "documents); pass --force-schema to replace it as well."
        )
    state = get_state()
    if use_json(state):
        rendering.emit_json(data, trim=state.trim)
    else:
        rendering.render_init(data)


def _as_mappings(data: object) -> list[dict[str, object]]:
    """Coerce a dispatcher payload into typed mappings, dropping anything else.

    The executor's return type is deliberately ``object`` — one boundary, many
    commands — so every caller that wants fields has to narrow. Rebuilding the
    dicts rather than casting keeps the key type honest: the wire is JSON, where
    keys are strings whatever the producer thought.
    """
    if not isinstance(data, list):
        return []
    return [
        {str(key): value for key, value in row.items()} for row in data if isinstance(row, dict)
    ]


def _emit_build(result: PublishResult, *, settings_home: str) -> None:
    data = {
        "out": str(result.out),
        "pages": result.pages,
        "documents": result.documents,
        "stale": result.stale,
        "store": settings_home,
    }
    if result.documents == 0:
        # An empty store is legitimate, so this is a warning rather than an
        # error — but the index is derived and gitignored, so a fresh clone has
        # none, and `build` otherwise writes a site with an empty index and
        # exits 0. Silence there reads as "nothing to publish" when it means
        # "nothing was read", which is the failure `check --strict` announces
        # rather than passing quietly.
        rendering.render_warning(
            f"no documents found in {settings_home} — the site will be empty. The index "
            "is derived and gitignored, so a fresh clone needs `docir reindex` first."
        )
    state = get_state()
    if use_json(state):
        rendering.emit_json(data, trim=state.trim)
    else:
        rendering.render_message(
            f"[green]built[/] {result.documents} documents into {result.out} ({result.pages} files)"
        )
        if result.stale:
            rendering.render_message(
                f"[yellow]{result.stale}[/] past their review cadence — flagged on the index"
            )


def _emit_schema(data: dict[str, object]) -> None:
    state = get_state()
    if use_json(state):
        rendering.emit_json(data, trim=state.trim)
    else:
        rendering.render_schema(data)


def _upgrade_the_package_then_restart() -> None:
    """Run the installer, then hand off to the docir it just installed.

    Returns normally when nothing was installed — an environment docir does not
    own (a checkout, a lockfile-managed project, an ephemeral `uvx` run), where
    the rest of the command is still worth doing. On a successful install it does
    not return at all: the process is replaced by the new build, carrying
    `--upgraded-from` so the report can still name the version that was here.
    """
    state = get_state()
    service = build_release_service(__version__, state.settings.release_cache_path)
    outcome = run_local(service.upgrade_package)
    if not outcome.ran:
        rendering.render_warning(f"package not upgraded — {outcome.message}")
        return
    if not outcome.ok:
        rendering.render_error(
            {"message": f"`{' '.join(outcome.command)}` failed: {outcome.message}"}
        )
        raise typer.Exit(code=1)
    _restart_as_the_new_build()


def _restart_as_the_new_build() -> None:
    """Replace this process with the docir that was just installed.

    `-m docir` rather than `sys.argv[0]`: the console script is a generated
    shebang wrapper, and the interpreter is the one thing that is certainly the
    upgraded environment's.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    argv = [sys.executable, "-m", "docir", *sys.argv[1:], "--upgraded-from", __version__]
    os.execv(sys.executable, argv)


def _emit_release_status(status: ReleaseStatus) -> None:
    payload: dict[str, object] = {
        "installed": status.installed,
        "latest": status.latest,
        "update_available": status.update_available,
        "checked_on": status.checked_on,
        "method": status.method,
        "upgrade_command": list(status.upgrade_command),
        "explanation": status.explanation,
    }
    state = get_state()
    if use_json(state):
        rendering.emit_json(payload, trim=state.trim)
    else:
        rendering.render_release_status(payload)


def _emit_upgrade(result: UpgradeResult) -> None:
    """Emit one report for the three steps, rather than three commands' output."""
    agents = [_setup_file(file) for file in result.agents]
    findings = list(result.findings)
    state = get_state()
    if use_json(state):
        payload: dict[str, object] = {
            "version": result.version,
            "upgraded_from": result.upgraded_from,
            "reindex": result.reindex,
            "agents": agents,
            "findings": findings,
        }
        rendering.emit_json(payload, trim=state.trim)
    else:
        rendering.render_upgrade(result.reindex, agents, findings, result.upgraded_from)


def _setup_file(file: InstalledFile) -> dict[str, object]:
    return {
        "target": file.target,
        "path": file.path,
        "action": file.action.value,
        "previous_version": file.previous_version,
        "new_version": file.new_version,
        "note": file.note,
    }


def _emit_setup(result: SetupResult) -> None:
    files = [
        {
            "target": file.target,
            "path": file.path,
            "action": file.action.value,
            "previous_version": file.previous_version,
            "new_version": file.new_version,
            "note": file.note,
        }
        for file in result.files
    ]
    state = get_state()
    if use_json(state):
        rendering.emit_json(files, trim=state.trim)
    else:
        rendering.render_setup(files)


def _install_json_help(command: Any, seen: set[int] | None = None) -> None:
    """Make ``--help`` obey the JSON/table contract at every command level.

    ``--help`` is eager: Click renders it during parsing, before the app
    callback sets :class:`CliState`, so the normal ``use_json`` path cannot
    reach it. Each command's ``get_help`` is wrapped instead, deciding per call
    (via :func:`help_wants_json`) whether to return the Rich panel a human wants
    or the compact JSON an agent captures.
    """
    seen = seen if seen is not None else set()
    if id(command) in seen:
        return
    seen.add(id(command))

    original = command.get_help

    def get_help(ctx: Any) -> str:
        if help_wants_json():
            return json.dumps(
                rendering.describe_help(ctx), separators=(",", ":"), ensure_ascii=False
            )
        return original(ctx)

    command.get_help = get_help
    for sub in getattr(command, "commands", {}).values():
        _install_json_help(sub, seen)


def main() -> None:
    """Console-script entry point."""
    command = get_command(app)
    _install_json_help(command)
    command()


if __name__ == "__main__":
    main()
