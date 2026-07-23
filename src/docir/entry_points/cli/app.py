"""The ``docir`` Typer application — the single entry point / agent contract.

Each command assembles a JSON payload and runs it through the executor (daemon
or in-process), then renders the response with Rich (or as raw JSON for
agents). The CLI is a thin client: all business logic lives in the use cases.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from docir import __version__
from docir.config.settings import Settings
from docir.entry_points.cli import rendering
from docir.entry_points.cli.body_input import resolve_body
from docir.entry_points.cli.runner import CliState, execute, get_state, set_state
from docir.entry_points.daemon.cmds import daemon_app

app = typer.Typer(
    help="Doc-Index CLI — git-backed markdown documents with a semantic index.",
    no_args_is_help=True,
    add_completion=False,
)
tag_app = typer.Typer(help="Manage the tag registry.", no_args_is_help=True)
app.add_typer(tag_app, name="tag")
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
        bool, typer.Option("--json", help="Emit raw JSON instead of tables.")
    ] = False,
) -> None:
    """Resolve global options and initialize CLI state."""
    settings = Settings.resolve(home, use_daemon=False if no_daemon else None)
    set_state(CliState(settings=settings, json_output=json_output))


@app.command()
def version() -> None:
    """Print the docir version."""
    rendering.render_message(__version__)


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
    if state.json_output:
        rendering.emit_json(data)
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
    if state.json_output:
        rendering.emit_json(data)
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
    if state.json_output:
        rendering.emit_json(data)
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
    if state.json_output:
        rendering.emit_json(data)
    elif isinstance(data, dict):
        rendering.render_document({str(key): value for key, value in data.items()})


def _emit_document_list(data: object) -> None:
    state = get_state()
    if state.json_output:
        rendering.emit_json(data)
    else:
        rendering.render_document_list(_as_list(data))


def _emit_or_message(data: object, message: str) -> None:
    state = get_state()
    if state.json_output:
        rendering.emit_json(data)
    else:
        rendering.render_message(message)


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
