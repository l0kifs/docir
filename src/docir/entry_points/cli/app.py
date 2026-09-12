"""The ``docir`` Typer application — the single entry point / agent contract.

Each command assembles a JSON payload and runs it through the executor (daemon
or in-process), then renders the response with Rich (or as raw JSON for
agents). The CLI is a thin client: all business logic lives in the use cases.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer
from typer.main import get_command

from docir import __version__
from docir.config.settings import Settings, new_store_home
from docir.entry_points.cli import emit, maintenance_cmds, read_cmds, rendering, write_cmds
from docir.entry_points.cli.agent_cmds import agent_app
from docir.entry_points.cli.runner import (
    CliState,
    execute,
    get_state,
    help_wants_json,
    run_local,
    set_state,
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


# Registered here rather than by decorator: these three groups live in their own
# modules, and `--help` lists commands in registration order, so the call sites
# sit exactly where the definitions used to.
write_cmds.register(app)
read_cmds.register(app)
maintenance_cmds.register(app)


#
# Both commands run in-process, bypassing the daemon/dispatcher, because
# ``build_container`` loads the schema: a file too broken to start the store
# would otherwise make the very commands meant to diagnose it unreachable.


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
