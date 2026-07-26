"""Rich rendering for humans + a compact-JSON path for agents.

The output is token-aware. At a TTY the responses render as Rich tables/panels;
when stdout is piped (an AI agent capturing output) or ``--json`` is passed,
commands emit compact single-line JSON instead. By default that JSON is
*trimmed* — fields carrying no information (empty strings, empty lists, nulls)
are dropped and the relevance ``score`` is rounded — so an agent reads an absent
field as its default. ``--no-trim`` keeps the full-fidelity payload.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()
error_console = Console(stderr=True)

_SCORE_DECIMALS = 4


def emit_json(data: object, *, trim: bool = True) -> None:
    """Print compact single-line JSON — the token-efficient path for agents.

    With ``trim`` (the default) empty fields are omitted and ``score`` rounded;
    pass ``trim=False`` (the CLI's ``--no-trim``) to keep the full payload.
    """
    payload = _trim(data) if trim else data
    sys.stdout.write(json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n")


def _trim(value: object) -> object:
    """Drop information-free fields (empty str/list/map, null) and round scores.

    Never drops ``False`` or a numeric ``0`` — only genuinely empty values — so an
    omitted key always means "the default", never a real zero. Recurses into
    nested lists and maps.
    """
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            if key == "score" and isinstance(item, float):
                result[str(key)] = round(item, _SCORE_DECIMALS)
                continue
            trimmed = _trim(item)
            if trimmed is None or trimmed == "" or trimmed == [] or trimmed == {}:
                continue
            result[str(key)] = trimmed
        return result
    if isinstance(value, list | tuple):
        return [_trim(item) for item in value]
    return value


def render_error(error: Mapping[str, object]) -> None:
    """Print a domain error to stderr."""
    message = error.get("message", "unknown error")
    error_console.print(f"[bold red]error:[/] {message}")


def render_document(view: Mapping[str, object]) -> None:
    """Render one full document (frontmatter fields + body)."""
    header = (
        f"[bold]{view['id']}[/]  [dim]{view['type']}/{view['status']}[/]\n"
        f"[bold cyan]{view['title']}[/]"
    )
    lines = [header, "", str(view.get("description", ""))]
    tags = _join(view.get("tags"))
    related = _format_related(view.get("related"))
    if tags:
        lines.append(f"[dim]tags:[/] {tags}")
    if related:
        lines.append(f"[dim]related:[/] {related}")
    if view.get("owner"):
        lines.append(f"[dim]owner:[/] {view['owner']}")
    if view.get("verified"):
        lines.append(f"[dim]verified:[/] {view['verified']}")
    if view.get("stale"):
        lines.append("[yellow]⚠ stale — past its review cadence[/]")
    if view.get("archived"):
        lines.append("[yellow]archived[/]")
    body = str(view.get("body", "")).strip()
    if body:
        lines.extend(["", body])
    console.print(Panel("\n".join(lines), expand=False))


def render_document_list(views: Sequence[Mapping[str, object]]) -> None:
    """Render a compact table of documents."""
    if not views:
        console.print("[dim]no matching documents[/]")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("id")
    table.add_column("type")
    table.add_column("status")
    table.add_column("title")
    table.add_column("description", overflow="fold")
    has_score = any(view.get("score") is not None for view in views)
    if has_score:
        table.add_column("score", justify="right")
    for view in views:
        marker = " ↗" if view.get("via_graph") else ""
        marker += " ⚠" if view.get("stale") else ""
        row = [
            str(view["id"]) + marker,
            str(view["type"]),
            str(view["status"]),
            str(view["title"]),
            str(view.get("description", "")),
        ]
        if has_score:
            score = view.get("score")
            row.append(f"{score:.3f}" if isinstance(score, int | float) else "-")
        table.add_row(*row)
    console.print(table)


def render_tags(tags: Sequence[Mapping[str, object]]) -> None:
    if not tags:
        console.print("[dim]no tags registered[/]")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("key")
    table.add_column("description", overflow="fold")
    for tag in tags:
        table.add_row(str(tag["key"]), str(tag["description"]))
    console.print(table)


def render_findings(findings: Sequence[Mapping[str, object]], *, empty: str) -> None:
    if not findings:
        console.print(f"[green]{empty}[/]")
        return
    for finding in findings:
        ids = _join(finding.get("doc_ids"))
        console.print(f"[yellow]{finding.get('kind')}[/]: {finding.get('message')} [dim]({ids})[/]")


def _join(value: object) -> str:
    """Comma-join an unknown-typed sequence value for display."""
    if isinstance(value, list | tuple):
        return ", ".join(str(item) for item in value)
    return ""


def _format_related(value: object) -> str:
    """Format typed edges as ``target (kind)`` (kind omitted when generic)."""
    if not isinstance(value, list | tuple):
        return ""
    parts: list[str] = []
    for item in value:
        if isinstance(item, dict):
            target = str(item.get("target", ""))
            kind = str(item.get("kind", ""))
            parts.append(f"{target} [dim]({kind})[/]" if kind and kind != "relates_to" else target)
        else:
            parts.append(str(item))
    return ", ".join(parts)


def render_schema(data: Mapping[str, object]) -> None:
    """Render the merged schema: the relation registry plus a per-type table."""
    kinds = _join(data.get("relation_types")) or "unconstrained (any kind accepted)"
    console.print(f"[dim]relation kinds:[/] {kinds}")

    table = Table(show_header=True, header_style="bold")
    for column in ("type", "prefix", "default", "transitions", "inactive", "level", "review"):
        table.add_column(column)
    types = data.get("types")
    for entry in types if isinstance(types, list | tuple) else ():
        if not isinstance(entry, Mapping):
            continue
        review = entry.get("review_days") or 0
        table.add_row(
            str(entry.get("name", "")),
            str(entry.get("prefix", "")),
            str(entry.get("default_status", "")),
            _format_transitions(entry.get("transitions")),
            _join(entry.get("inactive_statuses")),
            str(entry.get("level", 0)),
            f"{review}d" if review else "[dim]never[/]",
        )
    console.print(table)


def _format_transitions(value: object) -> str:
    """Format a status machine as ``draft→active; active→deprecated``."""
    if not isinstance(value, Mapping):
        return ""
    parts = [
        f"{status}→{_join(targets)}"
        for status, targets in value.items()
        if isinstance(targets, list | tuple) and targets
    ]
    return "; ".join(parts) or "[dim]terminal[/]"


def render_schema_valid(path: str, type_count: int) -> None:
    """Confirm a schema file parsed and merged cleanly."""
    console.print(f"[green]schema valid[/] [dim]({type_count} types)[/] {path}")


def render_init(result: Mapping[str, object]) -> None:
    """Render the outcome of ``docir init``."""
    console.print(f"[green]initialized[/] docir store at [bold]{result.get('home')}[/]")
    profiles = _join(result.get("profiles"))
    schema_note = (
        f"docs-schema.yaml (profiles: {profiles})"
        if result.get("schema_written")
        else ("docs-schema.yaml [dim](kept existing)[/]")
    )
    gitignore_note = (
        ".gitignore" if result.get("gitignore_written") else ".gitignore [dim](kept existing)[/]"
    )
    console.print(f"  [dim]schema:[/]    {schema_note}")
    console.print(f"  [dim]gitignore:[/] {gitignore_note}")
    console.print(
        "[dim]commit docs/ and docs-schema.yaml under the store; the index is gitignored.[/]"
    )


def render_setup(files: Sequence[Mapping[str, object]]) -> None:
    """Render the outcome of ``docir agent install/update``."""
    if not files:
        console.print("[dim]nothing to install or update[/]")
        return
    colors = {"created": "green", "updated": "cyan", "skipped": "dim"}
    for file in files:
        action = str(file.get("action", ""))
        previous = file.get("previous_version")
        new = file.get("new_version")
        if action == "updated" and previous and previous != new:
            version = f"v{previous} → v{new}"
        elif new:
            version = f"v{new}"
        else:
            version = ""
        note = file.get("note")
        suffix = f" [dim]({note})[/]" if note else ""
        color = colors.get(action, "white")
        console.print(f"[{color}]{action:<9}[/] {file.get('path')}  [dim]{version}[/]{suffix}")


def render_message(message: str) -> None:
    console.print(message)
