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

from docir.entry_points.payload import trim as trim_payload

console = Console()
error_console = Console(stderr=True)


def emit_json(data: object, *, trim: bool = True) -> None:
    """Print compact single-line JSON — the token-efficient path for agents.

    With ``trim`` (the default) empty fields are omitted and ``score`` rounded;
    pass ``trim=False`` (the CLI's ``--no-trim``) to keep the full payload.

    The trimming itself lives in ``entry_points.payload`` — the MCP server emits
    the same shape over a different transport, and the two must not drift.
    """
    payload = trim_payload(data) if trim else data
    sys.stdout.write(json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n")


def describe_help(ctx: object) -> dict[str, object]:
    """Serialize a Click command's help as plain data for the agent path.

    Mirrors what the Rich help panel shows — usage, description, options and
    sub-commands — but parseable and without the box-drawing characters that
    make up roughly a tenth of the rendered payload.
    """
    command = getattr(ctx, "command", None)
    path = str(getattr(ctx, "command_path", "") or "")

    pieces = command.collect_usage_pieces(ctx) if command is not None else []
    options = [
        {
            "flags": list(param.opts),
            "help": (getattr(param, "help", None) or "").strip(),
            "required": bool(getattr(param, "required", False)),
        }
        for param in getattr(command, "params", ())
        if getattr(param, "opts", None)
        and getattr(param, "name", None) != "help"
        # Hidden options are omitted here as well as from the Rich panel. Only
        # `commands` was filtered originally, which went unnoticed while no
        # option was hidden: the first deprecated alias (`--include-resolved`)
        # vanished from the human help and stayed in the JSON — the copy an
        # agent actually reads, and the one where a duplicate flag for one
        # concept does the most damage.
        and not getattr(param, "hidden", False)
    ]
    commands = [
        {"name": name, "help": _first_line(sub.help or sub.short_help or "")}
        for name, sub in sorted(getattr(command, "commands", {}).items())
        if not getattr(sub, "hidden", False)
    ]
    return {
        "command": path,
        "usage": " ".join([path, *pieces]).strip(),
        "help": _first_line(getattr(command, "help", "") or "", full=True),
        "options": options,
        "commands": commands,
    }


def _first_line(text: str, *, full: bool = False) -> str:
    """The summary line of a help string (or the whole body when ``full``)."""
    stripped = " ".join(text.split()) if not full else text.strip()
    return stripped.split("\n")[0].strip() if not full else stripped


def render_error(error: Mapping[str, object]) -> None:
    """Print a domain error to stderr."""
    message = error.get("message", "unknown error")
    error_console.print(f"[bold red]error:[/] {message}")


def render_warning(message: str) -> None:
    """Print a non-fatal notice to stderr.

    Stderr specifically: stdout carries the JSON an agent parses, and a
    deprecation notice mixed into it would corrupt the payload.
    """
    error_console.print(f"[yellow]warning:[/] {message}")


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
    has_similarity = any(view.get("similarity") is not None for view in views)
    if has_similarity:
        table.add_column("sim", justify="right")
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
        if has_similarity:
            similarity = view.get("similarity")
            row.append(f"{similarity:.3f}" if isinstance(similarity, int | float) else "-")
        table.add_row(*row)
    console.print(table)


def render_tags(tags: Sequence[Mapping[str, object]]) -> None:
    if not tags:
        console.print("[dim]no tags registered[/]")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("key")
    table.add_column("docs", justify="right")
    table.add_column("description", overflow="fold")
    for tag in tags:
        # Dim a dead tag rather than hiding it: zero is the finding.
        raw = tag.get("usage", 0)
        usage = raw if isinstance(raw, int) else 0
        table.add_row(
            str(tag["key"]),
            str(usage) if usage else "[dim]0[/]",
            str(tag["description"]),
        )
    console.print(table)


def render_findings(findings: Sequence[Mapping[str, object]], *, empty: str) -> None:
    if not findings:
        console.print(f"[green]{empty}[/]")
        return
    for finding in findings:
        ids = _join(finding.get("doc_ids"))
        # Colour by severity so the findings that fail a build are visually
        # separable from the ones that never will (`docir check --strict`).
        colour = "red" if finding.get("severity") == "error" else "yellow"
        console.print(
            f"[{colour}]{finding.get('kind')}[/]: {finding.get('message')} [dim]({ids})[/]"
        )


def render_repair(
    actions: Sequence[Mapping[str, object]],
    remaining: Sequence[Mapping[str, object]],
) -> None:
    """Report what ``check --fix`` changed, then what a human still has to judge."""
    if not actions:
        console.print("[green]nothing to repair[/]")
    for action in actions:
        console.print(f"[green]fixed[/] [cyan]{action.get('kind')}[/]: {action.get('message')}")
    if remaining:
        console.print("\n[dim]still open (not mechanically fixable):[/]")
        render_findings(remaining, empty="")
    elif actions:
        console.print("\n[green]no findings remain[/]")


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


def _render_relation_kinds(data: Mapping[str, object]) -> str:
    """Each kind with the properties it actually carries, resolved.

    A bare name list cannot answer the question a reader has here — whether an
    edge of this kind is cycle-checked, layering-checked, or followed backwards
    — and a core kind carries those without appearing in the file at all.
    """
    entries = data.get("relation_kinds")
    if not isinstance(entries, list | tuple) or not entries:
        return _join(data.get("relation_types"))
    rendered = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        flags = [p for p in ("symmetric", "dependency", "successor") if entry.get(p)]
        name = str(entry.get("name", ""))
        rendered.append(f"{name} ({', '.join(flags)})" if flags else name)
    return ", ".join(rendered)


def render_schema(data: Mapping[str, object]) -> None:
    """Render the merged schema: the relation registry plus a per-type table."""
    kinds = _render_relation_kinds(data) or "unconstrained (any kind accepted)"
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
    """Confirm a schema file parsed and merged cleanly.

    ``soft_wrap`` keeps a long store path on one line — Rich's default hard wrap
    breaks it mid-token, which makes the path unusable when copied.
    """
    console.print(f"[green]schema valid[/] [dim]({type_count} types)[/] {path}", soft_wrap=True)


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
