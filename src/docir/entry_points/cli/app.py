"""The ``docir`` Typer application — the single entry point / agent contract.

Each command assembles a JSON payload and runs it through the executor (daemon
or in-process), then renders the response with Rich (or as raw JSON for
agents). The CLI is a thin client: all business logic lives in the use cases.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml
from typer.main import get_command

from docir import __version__
from docir.config.settings import Settings, new_store_home
from docir.entry_points import doctor as doctor_report
from docir.entry_points.cli import emit, rendering
from docir.entry_points.cli.agent_cmds import agent_app
from docir.entry_points.cli.body_input import resolve_body
from docir.entry_points.cli.runner import (
    CliState,
    execute,
    get_state,
    help_wants_json,
    run_local,
    set_state,
    try_execute,
    use_json,
)
from docir.entry_points.cli.schema_cmds import schema_app
from docir.entry_points.cli.self_cmds import self_app
from docir.entry_points.cli.tag_cmds import tag_app
from docir.entry_points.composition import (
    DEFAULT_INIT_ID_STYLE,
    InitResult,
    initialize_store,
)
from docir.entry_points.daemon.cmds import daemon_app
from docir.entry_points.federation import LOCAL_ONLY_KEY
from docir.entry_points.mcp.cmds import mcp_app
from docir.modules.documents.api import (
    DEFAULT_CONTEXT_EXPAND,
    ID_STYLES,
    PROFILE_NAMES,
)
from docir.modules.publishing.api import PublishRequest, PublishResult, build_site_builder
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
    store: Annotated[
        list[str] | None,
        typer.Option(
            "--store",
            help="Also read this store (repeatable); adds to stores.yaml. Reads only.",
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
    set_state(
        CliState(
            settings=settings,
            json_output=json_output,
            pretty=pretty,
            trim=not no_trim,
            stores=tuple(store or ()),
        )
    )


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
            profiles=emit.split_csv(profiles),
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
    mermaid: Annotated[
        Path | None,
        typer.Option("--mermaid", help="Mermaid browser bundle, to draw mermaid fences."),
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

    A ```mermaid fence in a body publishes as its source unless you pass
    --mermaid path/to/mermaid.min.js (the browser bundle), which is written
    beside the pages and drawn from there — no CDN, so the site still works from
    file://. The runtime is megabytes, so it is yours to supply and is only
    written when some document actually draws a diagram.

    It must be a UMD build, loaded as a classic script. mermaid 11 ships only ES
    modules, so 10.x is the last line that has one — fetch it once with:

        curl -o mermaid.min.js \\
          https://cdn.jsdelivr.net/npm/mermaid@10.9.3/dist/mermaid.min.js

    An .mjs runtime is refused with that URL in the message, rather than copied
    into a page whose script never runs.
    """
    emit.warn_on_global_fallback()
    state = get_state()
    # Local only, explicitly: a site is a projection of *one* repository's
    # corpus (adr-fb938175f72a). `query` and `get` federate by default, so
    # without this a store that declares peers published their documents into
    # this repo's site while the summary still named this store.
    skeletons = execute(
        "query",
        {
            "limit": _BUILD_PAGE_LIMIT,
            "include_archived": include_archived,
            "include_inactive": True,
            LOCAL_ONLY_KEY: True,
        },
    )
    ids = [str(row["id"]) for row in emit.as_mappings(skeletons) if row.get("id")]
    # A second pass for the bodies, deliberately absent from every list path
    # (the skeleton contract) — but one batched `get`, since a site build reads
    # the whole corpus deeply, which is the shape the batch exists for. Two
    # deliberate omissions: `missing` is ignored, because these ids came from
    # `query` a moment ago and one that has since gone is a page not to publish
    # rather than an error; and an empty store skips the pass instead of being
    # tolerated by `get`, because nothing to read is not asking for nothing.
    documents = (
        emit.as_mappings(
            emit.as_mapping(execute("get", {"doc_ids": ids, LOCAL_ONLY_KEY: True})).get("documents")
        )
        if ids
        else []
    )
    result = run_local(
        lambda: build_site_builder().build(
            PublishRequest(
                out=out,
                documents=documents,
                title=title,
                version=__version__,
                logo=logo,
                mermaid=mermaid,
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


# -- write path -------------------------------------------------------------


@app.command()
def add(
    type: Annotated[str, typer.Option("--type", help="Document type.")],
    title: Annotated[str, typer.Option("--title", help="Document title.")],
    description: Annotated[
        str, typer.Option("--description", help="One-line summary, shown in every skeleton.")
    ],
    tags: Annotated[str | None, typer.Option("--tags", help="Comma-separated.")] = None,
    related: Annotated[
        str | None,
        typer.Option("--related", help="Comma-separated <id> or <id>:<kind> typed edges."),
    ] = None,
    status: Annotated[
        str | None,
        typer.Option("--status", help="Initial status; defaults to the type's default status."),
    ] = None,
    owner: Annotated[str | None, typer.Option("--owner", help="Steward for staleness.")] = None,
    code: Annotated[
        str | None,
        typer.Option("--code", help="Comma-separated repo-relative globs this document governs."),
    ] = None,
    isolated: Annotated[
        str | None,
        typer.Option(
            "--isolated",
            help="Why this document is meant to carry no relations; exempts it from `orphan`.",
        ),
    ] = None,
    id: Annotated[
        str | None,
        typer.Option(
            "--id",
            help="Adopt an existing id (migrating a numbered corpus) instead of allocating.",
        ),
    ] = None,
    body: Annotated[
        str | None, typer.Option("--body", help="Body markdown as a literal string.")
    ] = None,
    body_file: Annotated[
        Path | None,
        typer.Option("--body-file", help="Read the body markdown from this UTF-8 file."),
    ] = None,
    stdin: Annotated[
        bool,
        typer.Option("--stdin", help="Read the body markdown from stdin; avoids shell escaping."),
    ] = False,
    wait_embeddings: Annotated[
        bool, typer.Option("--wait-embeddings", help="Block until embeddings are recomputed.")
    ] = False,
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
        "tags": emit.split_csv(tags),
        "related": emit.split_csv(related),
        "status": status,
        "owner": owner,
        "code": emit.split_csv(code),
        "isolated": isolated,
        "id": id,
        "body": resolve_body(body, body_file, stdin),
        "wait_embeddings": wait_embeddings,
    }
    emit.warn_on_global_fallback()
    emit.emit_document(execute("add", payload))


@app.command()
def update(
    doc_id: Annotated[str, typer.Argument(help="Document id.")],
    status: Annotated[
        str | None, typer.Option("--status", help="Move the document to this status.")
    ] = None,
    set_type: Annotated[
        str | None,
        typer.Option("--type", help="Retype the document. The id never changes."),
    ] = None,
    set_title: Annotated[str | None, typer.Option("--set-title", help="Replace the title.")] = None,
    set_description: Annotated[
        str | None, typer.Option("--set-description", help="Replace the one-line summary.")
    ] = None,
    set_tags: Annotated[
        str | None,
        typer.Option(
            "--set-tags", help='Replace the tags, comma-separated (pass "" to clear them).'
        ),
    ] = None,
    set_related: Annotated[
        str | None,
        typer.Option("--set-related", help="Comma-separated <id> or <id>:<kind> typed edges."),
    ] = None,
    set_owner: Annotated[str | None, typer.Option("--set-owner", help="Staleness steward.")] = None,
    set_isolated: Annotated[
        str | None,
        typer.Option(
            "--set-isolated",
            help=(
                "Why this document is meant to carry no relations; exempts it from `orphan`. "
                'Pass "" to withdraw the exemption and put it back in the queue.'
            ),
        ),
    ] = None,
    set_code: Annotated[
        str | None,
        typer.Option(
            "--set-code",
            help="Comma-separated repo-relative globs this document governs "
            '(pass "" to clear them).',
        ),
    ] = None,
    verified: Annotated[
        bool,
        typer.Option(
            "--verified",
            help=(
                "Stamp today as the last-verified date, and record what the "
                "document's `code` globs match right now."
            ),
        ),
    ] = False,
    clear_verified: Annotated[
        bool,
        typer.Option(
            "--clear-verified",
            help=(
                "Withdraw the verification, leaving no review window: the "
                "document ages from `created` again. Use it when a stamp asserts "
                "a review nobody did. Refused when none is standing."
            ),
        ),
    ] = False,
    append_section: Annotated[
        str | None,
        typer.Option("--append-section", help="Append the body text under this heading."),
    ] = None,
    replace_section: Annotated[
        str | None,
        typer.Option(
            "--replace-section", help="Overwrite this heading's section with the body text."
        ),
    ] = None,
    remove_section: Annotated[
        str | None,
        typer.Option("--remove-section", help="Delete this heading and the text under it."),
    ] = None,
    replace_body: Annotated[
        bool, typer.Option("--replace-body", help="Overwrite the whole body. Requires --force.")
    ] = False,
    body: Annotated[
        str | None, typer.Option("--body", help="The edit's text, as a literal string.")
    ] = None,
    body_file: Annotated[
        Path | None, typer.Option("--body-file", help="Read the edit's text from this UTF-8 file.")
    ] = None,
    stdin: Annotated[
        bool,
        typer.Option("--stdin", help="Read the edit's text from stdin; avoids shell escaping."),
    ] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Allow --replace-body to overwrite the existing body.")
    ] = False,
    override: Annotated[
        bool,
        typer.Option(
            "--override",
            help="Force an illegal status transition (warns; last resort).",
        ),
    ] = False,
    wait_embeddings: Annotated[
        bool, typer.Option("--wait-embeddings", help="Block until embeddings are recomputed.")
    ] = False,
) -> None:
    """Update a document (metadata patch and/or a body edit).

    --type retypes the document. Its id is left alone, prefix included: the id is
    the only address the corpus has for it, so `adr-3f9a2b1c7d4e` stays `adr-3f9a2b1c7d4e`
    under a type whose prefix is something else. A prefix records which type
    minted an id, not which type owns it now. The file moves into the new type's
    directory, keeping its filename.

    The status is carried over if the new type declares it, and the write is
    refused if it does not — pass --status alongside --type to say what it
    becomes. That is a membership check, not a transition: the type being left
    has no say over the statuses of the one being entered.

    Retyping works even when the current type is one the schema no longer
    declares, which is how a corpus leaves a type that `disable_types:` removed.

    A body edit takes at most one mode. --append-section and --replace-section
    both write the heading line themselves, so --body carries only the text that
    goes *under* it: pasting back what `get --section` returned — which does
    include the heading — is refused rather than writing the heading twice.

    --remove-section deletes a heading and everything under it, and takes no
    --body — passing one is refused, since "delete this text" is not what it
    does. It is the way out of a body that already spells one heading twice,
    which --replace-section cannot undo (it keeps the first heading line by
    contract) and --append-section only adds to:

        docir update adr-3f9a2b1c7d4e --remove-section "Notes"

    A repeated heading resolves to the first, here as everywhere, so removing the
    second of two means running it twice. `docir lint --deep` names the documents
    that have one.

    --verified stamps today; --clear-verified takes the stamp back, erasing
    `verified` and stamping `revoked` in its place. Editing the title, the
    description or the body of a verified document does the same thing by
    itself: the review covered that content, the content moved, so the
    verification is withdrawn and the cadence restarts from the day it was:

        docir update adr-3f9a2b1c7d4e --verified          # verified: 2026-09-05
        docir update adr-3f9a2b1c7d4e --append-section H --body "..."
                                                          # revoked: 2026-09-05
        docir update adr-3f9a2b1c7d4e --clear-verified    # a stamp nobody earned
                                                          # -> ages from `created`

    Pass --verified alongside the edit to keep the stamp — that is "I rewrote it
    and re-read it". A status, tag, type or edge change is not a content change
    and leaves the verification standing. `docir query --stale` lists what the
    cadence has caught up with; `docir query --expr "revoked"` lists what lapsed.

    --verified also digests the text it covered, so `docir check` reports
    (`verification-outdated`) a document edited *around* the CLI — a hand-edit, a
    merge, or an older docir — where the stamp still stands over text nobody
    read. Clear it by re-reading and stamping again, or by withdrawing it.
    """
    body_text = resolve_body(body, body_file, stdin, default="")
    payload: dict[str, object] = {
        "doc_id": doc_id,
        "status": status,
        "set_type": set_type,
        "set_title": set_title,
        "set_description": set_description,
        "set_tags": None if set_tags is None else emit.split_csv(set_tags),
        "set_related": None if set_related is None else emit.split_csv(set_related),
        "set_owner": set_owner,
        "set_isolated": set_isolated,
        "set_code": None if set_code is None else emit.split_csv(set_code),
        "mark_verified": verified,
        "clear_verified": clear_verified,
        "append_section": [append_section, body_text] if append_section else None,
        "replace_section": [replace_section, body_text] if replace_section else None,
        "remove_section": remove_section,
        # Carried whole as well as folded into a mode above: --remove-section
        # consumes no text, and the dispatcher refuses it rather than dropping
        # it silently.
        "body": body_text,
        "replace_body": body_text if replace_body else None,
        "force": force,
        "allow_transition_override": override,
        "wait_embeddings": wait_embeddings,
    }
    emit.warn_on_global_fallback()
    data = execute("update", payload)
    forced = data.get("forced_transition") if isinstance(data, dict) else None
    if forced:
        # Loud at the moment of the bypass, but not written to the file: git
        # records the status change, and docir has no actors to attribute it to.
        rendering.render_warning(f"forced illegal transition {forced}")
    emit.emit_document(data)


@app.command()
def archive(doc_id: Annotated[str, typer.Argument(help="Document id.")]) -> None:
    """Soft-remove a document from active search."""
    emit.emit_document(execute("archive", {"doc_id": doc_id}))


@app.command()
def unarchive(doc_id: Annotated[str, typer.Argument(help="Document id.")]) -> None:
    """Restore an archived document to active search."""
    emit.emit_document(execute("unarchive", {"doc_id": doc_id}))


@app.command()
def delete(
    doc_id: Annotated[str, typer.Argument(help="Document id.")],
    force: Annotated[
        bool,
        typer.Option(
            "--force", help="Delete even while documents relate to it, stripping those edges."
        ),
    ] = False,
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
    emit.emit_or_message(data, message)


# -- read path --------------------------------------------------------------


@app.command()
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


@app.command()
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


@app.command()
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


# -- tags -------------------------------------------------------------------


# -- agent instructions -----------------------------------------------------


# -- the installation itself -------------------------------------------------


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
) -> None:
    """Rebuild the index from the canonical files.

    Source files that do not parse are skipped and counted as
    `documents_skipped`: a rebuild that quietly dropped a document used to look
    exactly like one that did not. `docir check` names each such file.

    Every document this run re-saves is re-embedded before it returns, and
    `embeddings_recomputed` says how many. So a full rebuild is also the way to
    recompute every vector — there is no flag for that, because there was
    nothing for one to add (adr-6a4718fa7a7d).
    """
    with rendering.progress("rebuilding the index"):
        data = execute("reindex", {"changed_only": changed})
    skipped = data.get("documents_skipped") if isinstance(data, dict) else None
    if isinstance(skipped, int) and skipped:
        # stderr, so a captured JSON payload on stdout stays parseable.
        rendering.render_warning(
            f"{skipped} file(s) could not be parsed and are NOT in the index; "
            "run `docir check` to see which, then fix the frontmatter by hand."
        )
    emit.emit_or_message(data, str(data))


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

    One warning reports good news: `unblocked` names a live document whose every
    `depends_on` target has closed, so the work is ready to start. Nothing else
    reads that edge — without this it stays true and unnoticed.

    Pass --strict to gate a pre-merge / CI job: it exits 1 on errors only, which
    is what catches the duplicate ids and dangling references a branch merge
    introduces. Warnings do not fail the build — `orphan` fires for every
    document with no relations, so gating on them fails a healthy corpus.
    Use --strict-all if you really do want every finding to be fatal.

    `unresolved-link` is the prose half of `dangling`: a `[[...]]` in a body
    whose target is no document. A target may be an id, a filename stem, a title
    slug or the title itself, and it resolves against every document — a link to
    a resolved issue or a superseded decision works, so "not in the default
    query" is never why one is reported. Links inside code are not links and are
    skipped. A warning, not an error: a prose link carries no kind, gates no
    merge and feeds no graph, so a broken one costs a reader a click. Find them,
    then find what each one meant:

        docir check | jq -r '.[] | select(.kind=="unresolved-link") | .message'
        docir search "the words from the broken target"

    `orphan` reads `related:` only — and so does every other check here. Neither
    an id named in a paragraph nor a `[[...]]` link clears it, and a triage that
    lists the orphans is exactly the prose that used to:

        docir check | jq -r '.[] | select(.kind=="orphan") | .doc_ids[0]'

    Each id on that list ends one of two ways — an edge, or a recorded reason
    for standing alone:

        docir update adr-3f9a2b1c7d4e --set-related arch-ad342aae8293:refines
        docir update adr-3f9a2b1c7d4e --set-isolated "scope deferred; nothing depends on it yet"

    The second is a judgement, so it is auditable and reversible: list every
    exemption with `docir query --expr "isolated"`, withdraw one with
    `--set-isolated ""`. Both are ordinary edits and stamp `updated`, like every
    other flag here.
    """
    state = get_state()
    if fix:
        with rendering.progress("repairing the corpus"):
            result = execute("repair", {})
        payload = result if isinstance(result, dict) else {}
        issues = emit.as_list(payload.get("remaining"))
        if use_json(state):
            rendering.emit_json(result, trim=state.trim)
        else:
            rendering.render_repair(emit.as_list(payload.get("actions")), issues)
    else:
        data = execute("check", {})
        issues = emit.as_list(data)
        if use_json(state):
            rendering.emit_json(data, trim=state.trim)
        else:
            rendering.render_findings(issues, empty="no structural issues")

    fatal = issues if strict_all else [i for i in issues if i.get("severity") == "error"]
    if (strict or strict_all) and fatal:
        raise typer.Exit(code=1)


@app.command()
def doctor(
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Exit nonzero on error-severity findings (for CI)."),
    ] = False,
    probe: Annotated[
        bool,
        typer.Option("--probe", help="Actually load the embedding model (may download ~67MB)."),
    ] = False,
) -> None:
    """Diagnose the docir installation, this store, the daemon and the peers.

    The conditions docir can be *subtly* wrong in, in one report: a daemon
    serving code you have since replaced, DOCIR_EMBEDDER left over from a test
    run, an index built by another version, a schema that has moved under the
    corpus, a peer every read is silently skipping, writes about to land in the
    global store because nobody ran `docir init` here.

    Each was already detectable — in `daemon status`, `self status`, a stderr
    line during a read, one finding among a hundred in `check`. None was
    reportable together, so the way you found out was an answer that looked
    right and was not.

    Findings carry a severity. `error` means docir cannot work correctly here (no
    index, a schema that will not load, no embedding model); `warning` means it
    works less well than you think. --strict exits 1 on errors only, which is
    what makes it usable in a setup script or CI.

    It never touches the network and, without --probe, never loads a model:

        docir doctor                # the whole report, in ~100ms
        docir doctor --strict       # gate a setup step on a working install
        docir doctor --probe        # also prove the model loads, and time it

    The corpus is `docir check`'s question, not this one.
    """
    state = get_state()
    # Before anything is dispatched: `ensure_running` replaces a daemon serving
    # other code and a container build creates a missing index, so both facts
    # are gone by the time the first request returns.
    environment = run_local(lambda: doctor_report.snapshot(state.settings, __version__))
    store, store_error = try_execute("store_status", {})
    if probe:
        # The one thing doctor does that is not instant: --probe's whole job is
        # to load the model, which downloads it on a cold cache.
        with rendering.progress("loading the embedding model (may download ~67MB)"):
            probed = run_local(lambda: doctor_report.probe_embedder(environment.embed_model))
    else:
        probed = None
    report = doctor_report.diagnose(
        environment,
        _store_reply(store),
        store_error=store_error,
        probe=probed,
    )
    _emit_doctor(report)
    if strict and report.errors:
        raise typer.Exit(code=1)


@app.command()
def lint(
    deep: Annotated[
        bool, typer.Option("--deep", help="Actually run the checks; without it lint does nothing.")
    ] = False,
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
        rendering.render_findings(emit.as_list(data), empty="no advisory findings")


@app.command()
def bench(
    fixture: Annotated[Path, typer.Argument(help="YAML or JSON file of judged tasks.")],
    limit: Annotated[int, typer.Option("--limit", help="Result-set size to score at.")] = 5,
    expand: Annotated[
        int,
        typer.Option("--expand", help="Neighbour slots for the `context` row."),
    ] = DEFAULT_CONTEXT_EXPAND,
) -> None:
    """Score this store's retrieval against a fixture of judged tasks.

    docir publishes retrieval numbers measured on its own corpus. This is the
    same instrument pointed at yours, so "is retrieval any good here?" has an
    answer you produced rather than one you inherited.

    The fixture is a list of tasks, each with the document **ids** a reader
    would need. Ids rather than paths, because a retitle moves the filename and
    a retype moves the directory, and a fixture has to outlive both:

        - id: T01
          task: how do we authenticate API clients
          relevant: [adr-3f9a2b1c7d4e, issue-90aea6d1b891]

    Three rows, and the pair is the point. `context` is the shipped default.
    `context --expand 0` removes graph expansion, which lifts every embedder and
    hides the difference between them, so the two together isolate the semantic
    signal. `search` is full-text alone — the floor anything semantic must beat.

    Ids no document carries are reported, never dropped quietly: removing one
    shrinks recall's denominator and raises the score for the wrong reason.

    It prints numbers and exits 0. Do not gate CI on it until the numbers are
    understood — a fixture is one annotator's opinion of what is relevant.
    """
    # via run_local, so a bad fixture is a domain error with an exit code rather
    # than a traceback — the same escape `load_schema` had to be given, on the
    # other file docir asks a human to write by hand.
    tasks = run_local(lambda: _read_fixture(fixture))
    data = execute("bench", {"tasks": tasks, "limit": limit, "expand": expand})
    state = get_state()
    if use_json(state):
        rendering.emit_json(data, trim=state.trim)
    else:
        rendering.render_bench(emit.as_mapping(data))


def _read_fixture(path: Path) -> list[object]:
    """Load a bench fixture. YAML, which also parses the JSON spelling.

    Read here rather than in the dispatcher: with the daemon the dispatcher runs
    in another process, and over MCP in another machine's, so a path argument
    would be resolved against a filesystem the caller never named.
    """
    if not path.exists():
        raise ValidationError(f"no fixture at {path}")
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValidationError(f"{path} is not valid YAML or JSON: {exc}") from exc
    # A mapping with a `tasks:` key is accepted too, so a fixture can carry a
    # description beside its tasks without a second format to document.
    if isinstance(loaded, dict):
        loaded = loaded.get("tasks")
    if not isinstance(loaded, list) or not loaded:
        raise ValidationError(f"{path} must hold a non-empty list of tasks, or a 'tasks:' key")
    return loaded


@app.command()
def embed(
    flush: Annotated[
        bool,
        typer.Option("--flush", help="Actually drain the queue; without it embed does nothing."),
    ] = False,
) -> None:
    """Force a synchronous embedding recompute of dirty documents."""
    if not flush:
        rendering.render_message("[dim]pass --flush to drain the embedding queue[/]")
        raise typer.Exit(code=0)
    with rendering.progress("recomputing embeddings"):
        data = execute("embed_flush", {})
    emit.emit_or_message(data, str(data))


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


def _emit_doctor(report: doctor_report.DoctorReport) -> None:
    """Emit the diagnosis as one payload, findings included.

    Sections and findings travel together rather than as two commands' output,
    because a finding is only actionable beside the fact that produced it: "12
    documents have no current vector" means one thing under the real model and
    another under a leftover DOCIR_EMBEDDER, and the embedding section is where
    the caller reads which.
    """
    environment = report.environment
    release = environment.release
    payload: dict[str, object] = {
        "ok": not report.errors,
        "installation": {
            "version": environment.version,
            "method": release.method,
            "latest": release.latest,
            "update_available": release.update_available,
            "fastembed_installed": environment.fastembed_installed,
        },
        "store": {
            "home": str(environment.home),
            "home_origin": environment.home_origin,
            "schema": str(environment.schema_path),
            "schema_loads": not environment.schema_error,
            "index_present": environment.index_present,
            "shadowed_home": _opt_str_path(environment.shadowed_home),
            "description": environment.store_description,
            **(report.store or {}),
        },
        "embedding": {
            "model": environment.embedder_id,
            "configured": environment.embed_model,
            "env": environment.embedder_env,
        },
        "daemon": {
            "running": environment.daemon.running,
            "pid": environment.daemon.pid,
            "socket": environment.daemon.socket_path,
            "serving": environment.daemon.version,
            "stale_code": environment.daemon.stale_code,
            "disabled_by_env": environment.daemon_env_disabled,
            "watching": environment.watch,
        },
        "peers": [
            {
                "home": str(peer.home),
                "unavailable": peer.unavailable,
                "description": peer.description,
            }
            for peer in environment.peers
        ],
        "findings": [asdict(finding) for finding in report.findings],
    }
    if report.probe is not None:
        payload["probe"] = asdict(report.probe)
    state = get_state()
    if use_json(state):
        rendering.emit_json(payload, trim=state.trim)
    else:
        rendering.render_doctor(payload)


def _store_reply(payload: object) -> dict[str, object] | None:
    """``store_status``'s reply as a mapping, or ``None`` when there is none.

    ``None`` is the store-unreachable signal doctor turns into a finding, so a
    reply that is not a mapping has to read the same way — a payload nobody can
    interpret is not a store that answered. Distinct from :func:`emit.as_mapping`,
    which coerces a missing reply to ``{}`` because its callers are rendering a
    result they already know arrived.
    """
    if not isinstance(payload, dict):
        return None
    return {str(key): value for key, value in payload.items()}


def _opt_str_path(path: Path | None) -> str | None:
    return None if path is None else str(path)


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
