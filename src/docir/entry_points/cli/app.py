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
from docir.config.settings import PROJECT_STORE_DIRNAME, Settings
from docir.entry_points.cli import rendering
from docir.entry_points.cli.body_input import resolve_body
from docir.entry_points.cli.runner import (
    CliState,
    execute,
    get_state,
    help_wants_json,
    run_local,
    set_state,
    use_json,
)
from docir.entry_points.composition import InitResult, initialize_store
from docir.entry_points.daemon.cmds import daemon_app
from docir.modules.agents.api import (
    AGENT_NAMES,
    DEFAULT_AGENTS,
    InstallRequest,
    SetupResult,
    UpdateRequest,
    build_agent_service,
)
from docir.modules.documents.api import PROFILE_NAMES, describe_schema, load_schema

app = typer.Typer(
    help="Doc-Index CLI — git-backed markdown documents with a semantic index.",
    no_args_is_help=True,
    add_completion=False,
)
tag_app = typer.Typer(help="Manage the tag registry.", no_args_is_help=True)
agent_app = typer.Typer(help="Install AI-assistant instructions for docir.", no_args_is_help=True)
schema_app = typer.Typer(help="Inspect and validate the document schema.", no_args_is_help=True)
app.add_typer(tag_app, name="tag")
app.add_typer(agent_app, name="agent")
app.add_typer(schema_app, name="schema")
app.add_typer(daemon_app, name="daemon")


@app.callback()
def main_callback(
    home: Annotated[
        str | None,
        typer.Option("--home", help="Data root (default: $DOCIR_HOME or ~/.docir)."),
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
    directory: Annotated[Path, typer.Argument(help="Project directory to initialize.")] = Path("."),
    profiles: Annotated[
        str | None,
        typer.Option(
            "--profiles", help=f"Comma-separated schema profiles ({', '.join(PROFILE_NAMES)})."
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite an existing docs-schema.yaml / .gitignore."),
    ] = False,
) -> None:
    """Create a project-local docir store (./.docir) that commands auto-discover.

    Scopes this repo's docs to the repo instead of the global ~/.docir store:
    commands run anywhere inside the tree find the store by walking up for
    .docir (the git model). Commit .docir/docs/ and .docir/docs-schema.yaml; the
    derived index is gitignored for you.
    """
    home = directory.resolve() / PROJECT_STORE_DIRNAME
    settings = Settings.resolve(home=home, use_daemon=False)
    result = run_local(
        lambda: initialize_store(settings, profiles=_split_csv(profiles), force=force)
    )
    _emit_init(result)


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
    """Check docs-schema.yaml parses and merges cleanly; exit nonzero if not."""
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
    body: Annotated[str | None, typer.Option("--body")] = None,
    body_file: Annotated[Path | None, typer.Option("--body-file")] = None,
    stdin: Annotated[bool, typer.Option("--stdin")] = False,
    wait_embeddings: Annotated[bool, typer.Option("--wait-embeddings")] = False,
) -> None:
    """Create a new document with valid frontmatter."""
    payload: dict[str, object] = {
        "type": type,
        "title": title,
        "description": description,
        "tags": _split_csv(tags),
        "related": _split_csv(related),
        "status": status,
        "owner": owner,
        "body": resolve_body(body, body_file, stdin),
        "wait_embeddings": wait_embeddings,
    }
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
        bool, typer.Option("--override", help="Allow an illegal status transition.")
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
        "mark_verified": verified,
        "append_section": [append_section, body_text] if append_section else None,
        "replace_section": [replace_section, body_text] if replace_section else None,
        "replace_body": body_text if replace_body else None,
        "force": force,
        "allow_transition_override": override,
        "wait_embeddings": wait_embeddings,
    }
    _emit_document(execute("update", payload))


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
    """Hard-delete a document's file and index rows."""
    data = execute("delete", {"doc_id": doc_id, "force": force})
    _emit_or_message(data, f"deleted {doc_id}")


# -- read path --------------------------------------------------------------


@app.command()
def get(doc_id: Annotated[str, typer.Argument()]) -> None:
    """Return one document in full."""
    _emit_document(execute("get", {"doc_id": doc_id}))


@app.command()
def query(
    type: Annotated[list[str] | None, typer.Option("--type")] = None,
    status: Annotated[list[str] | None, typer.Option("--status")] = None,
    tag: Annotated[list[str] | None, typer.Option("--tag")] = None,
    include_archived: Annotated[bool, typer.Option("--include-archived")] = False,
    include_resolved: Annotated[bool, typer.Option("--include-resolved")] = False,
    limit: Annotated[int, typer.Option("--limit")] = 50,
) -> None:
    """Structured metadata filtering."""
    payload: dict[str, object] = {
        "types": tuple(type or ()),
        "statuses": tuple(status or ()),
        "tags": tuple(tag or ()),
        "include_archived": include_archived,
        "include_inactive": include_resolved,
        "limit": limit,
    }
    _emit_document_list(execute("query", payload))


@app.command()
def search(
    text: Annotated[str, typer.Argument()],
    limit: Annotated[int, typer.Option("--limit")] = 20,
    include_resolved: Annotated[bool, typer.Option("--include-resolved")] = False,
) -> None:
    """Full-text search."""
    payload: dict[str, object] = {
        "text": text,
        "limit": limit,
        "include_inactive": include_resolved,
    }
    _emit_document_list(execute("search", payload))


@app.command()
def context(
    task: Annotated[str, typer.Argument(help="Agent task description.")],
    limit: Annotated[int, typer.Option("--limit")] = 5,
    include_resolved: Annotated[bool, typer.Option("--include-resolved")] = False,
) -> None:
    """Ranked, minimal relevant document set (hybrid + graph traversal)."""
    payload: dict[str, object] = {
        "task": task,
        "limit": limit,
        "include_inactive": include_resolved,
    }
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
def tag_list() -> None:
    """List every registered tag."""
    data = execute("tag_list", {})
    state = get_state()
    if use_json(state):
        rendering.emit_json(data, trim=state.trim)
    else:
        rendering.render_tags(_as_list(data))


@tag_app.command("rename")
def tag_rename(
    old: Annotated[str, typer.Argument()], new: Annotated[str, typer.Argument()]
) -> None:
    """Rename a tag across the registry and all documents."""
    data = execute("tag_rename", {"old": old, "new": new})
    _emit_or_message(data, f"renamed {old} -> {new}")


@tag_app.command("rm")
def tag_rm(
    key: Annotated[str, typer.Argument()],
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    """Remove a tag (blocked while in use unless forced)."""
    data = execute("tag_remove", {"key": key, "force": force})
    _emit_or_message(data, f"removed tag {key}")


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


# -- maintenance ------------------------------------------------------------


@app.command()
def reindex(
    changed: Annotated[bool, typer.Option("--changed")] = False,
    embeddings: Annotated[bool, typer.Option("--embeddings")] = False,
) -> None:
    """Rebuild the index from the canonical files."""
    data = execute("reindex", {"changed_only": changed, "embeddings": embeddings})
    _emit_or_message(data, str(data))


@app.command()
def check(
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Exit nonzero if any issue is found (for CI)."),
    ] = False,
) -> None:
    """Tier 1 structural checks (cycles, orphans, layering, dangling, dup ids).

    Pass --strict to gate a pre-merge / CI job: it exits 1 when any issue is
    found, which catches duplicate ids or dangling references a branch merge
    introduced before they reach main.
    """
    data = execute("check", {})
    state = get_state()
    issues = _as_list(data)
    if use_json(state):
        rendering.emit_json(data, trim=state.trim)
    else:
        rendering.render_findings(issues, empty="no structural issues")
    if strict and issues:
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


def _split_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _as_list(data: object) -> list[dict[str, object]]:
    if not isinstance(data, list):
        return []
    result: list[dict[str, object]] = []
    for item in data:
        if isinstance(item, dict):
            result.append({str(key): value for key, value in item.items()})
    return result


def _emit_document(data: object) -> None:
    state = get_state()
    if use_json(state):
        rendering.emit_json(data, trim=state.trim)
    elif isinstance(data, dict):
        rendering.render_document({str(key): value for key, value in data.items()})


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
        "schema_written": result.schema_written,
        "gitignore_written": result.gitignore_written,
    }
    state = get_state()
    if use_json(state):
        rendering.emit_json(data, trim=state.trim)
    else:
        rendering.render_init(data)


def _emit_schema(data: dict[str, object]) -> None:
    state = get_state()
    if use_json(state):
        rendering.emit_json(data, trim=state.trim)
    else:
        rendering.render_schema(data)


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
