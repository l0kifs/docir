"""Rich rendering of command responses (with a JSON escape hatch for agents)."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()
error_console = Console(stderr=True)


def emit_json(data: object) -> None:
    """Print a raw JSON representation (used with the global --json flag)."""
    console.print_json(json.dumps(data))


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
    related = _join(view.get("related"))
    if tags:
        lines.append(f"[dim]tags:[/] {tags}")
    if related:
        lines.append(f"[dim]related:[/] {related}")
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
        row = [
            str(view["id"]) + (" ↗" if view.get("via_graph") else ""),
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


def render_message(message: str) -> None:
    console.print(message)
