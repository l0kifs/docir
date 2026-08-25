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

from docir import __version__
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


def render_schema_drift(lines: Sequence[str]) -> None:
    """Print the schema-drift notice to stderr (``DOCIR_SCHEMA_NOTICE=1``).

    One line per change, because the lines *are* the report: the schema moved
    without a diff to read, and this is that diff.
    """
    error_console.print(
        "[yellow]warning:[/] the active schema differs from the one the index was built against:"
    )
    for line in lines:
        error_console.print(f"  {line}")
    error_console.print("  run `docir reindex` once you have dealt with it.")


def render_warning(message: str) -> None:
    """Print a non-fatal notice to stderr.

    Stderr specifically: stdout carries the JSON an agent parses, and a
    deprecation notice mixed into it would corrupt the payload.
    """
    error_console.print(f"[yellow]warning:[/] {message}")


def _render_traces(views: Sequence[Mapping[str, object]]) -> None:
    """The ``--explain`` traces, one dim line per document, under the table.

    Not a column: the trace is a mapping of five to seven keys and a table cell
    cannot hold it legibly. Not rendered at all when nothing carries one, so the
    default read is unchanged.
    """
    traced = [(view, view.get("explain")) for view in views]
    if not any(isinstance(trace, Mapping) for _view, trace in traced):
        return
    console.print()
    for view, trace in traced:
        if not isinstance(trace, Mapping):
            continue
        terms = " ".join(f"{key}={value}" for key, value in trace.items())
        console.print(f"[dim]{view.get('id')}[/]  [dim]{terms}[/]")


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
    governs = _join(view.get("code"))
    if governs:
        lines.append(f"[dim]governs:[/] {governs}")
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
    # Only when some hit matched through a section: on a corpus of short
    # documents the column would be empty in every row, and a column of dashes
    # reads as a missing feature rather than as "nothing matched that way".
    has_section = any(view.get("matched_section") for view in views)
    if has_section:
        table.add_column("matched section", overflow="fold")
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
        if has_section:
            row.append(str(view.get("matched_section") or "-"))
        table.add_row(*row)
    console.print(table)
    _render_traces(views)


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


def _count(entry: object) -> int:
    """A finding's ``count``, tolerant of a payload that has been round-tripped."""
    value = entry.get("count") if isinstance(entry, Mapping) else None
    return value if isinstance(value, int) else 0


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


def render_schema_valid(result: Mapping[str, object]) -> None:
    """Confirm a schema file parsed, and say what it costs the corpus.

    Takes the same payload the JSON branch emits — the convention `render_init`
    follows — so the two views cannot report different numbers.

    ``soft_wrap`` keeps a long store path on one line — Rich's default hard wrap
    breaks it mid-token, which makes the path unusable when copied.

    The corpus lines are yellow, never red, and never change the exit code: the
    file is valid and the documents are what moved. They go to stdout with the
    rest of the result because they *are* the result — the person who just
    edited the schema is the one who needs them.
    """
    console.print(
        f"[green]schema valid[/] [dim]({result.get('types')} types)[/] {result.get('path')}",
        soft_wrap=True,
    )
    unreadable = result.get("unreadable") or 0
    if isinstance(unreadable, int) and unreadable:
        console.print(
            f"[yellow]{unreadable} file(s) under the docs root do not parse[/] "
            f"[dim]and were not measured — `docir check` names them[/]"
        )
    findings = result.get("findings")
    documents = result.get("documents")
    if not isinstance(findings, Sequence) or not findings:
        console.print(f"[dim]{documents} document(s) conform[/]")
        return
    rows = [entry for entry in findings if isinstance(entry, Mapping)]
    console.print(
        f"[yellow]{result.get('affected')} of {documents} document(s) do not fit this schema[/]"
    )
    for entry in rows:
        count = _count(entry)
        sample = entry.get("sample")
        listed = _join(sample)
        more = count - (len(sample) if isinstance(sample, list | tuple) else 0)
        if more > 0:
            listed = f"{listed}, +{more} more" if listed else f"{more} more"
        console.print(f"  [yellow]{entry.get('kind')}[/] [bold]{count}[/] [dim]{listed}[/]")
    console.print("[dim]`docir check` lists them all; the schema itself is fine[/]")


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
    colors = {"created": "green", "updated": "cyan", "unchanged": "dim", "skipped": "dim"}
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


def render_release_status(status: Mapping[str, object]) -> None:
    """Render ``docir self status``: what is installed, and whether it is current."""
    installed = status.get("installed")
    latest = status.get("latest")
    if latest is None:
        line = f"[cyan]docir {installed}[/]  [dim]newest release unknown — nothing checked yet[/]"
    elif status.get("update_available"):
        line = f"[cyan]docir {installed}[/]  [yellow]{latest} is available[/]"
    else:
        line = f"[cyan]docir {installed}[/]  [green]up to date[/]"
    checked = status.get("checked_on")
    console.print(line + (f"  [dim](checked {checked})[/]" if checked else ""))
    command = status.get("upgrade_command")
    if isinstance(command, Sequence) and not isinstance(command, str) and command:
        rendered = " ".join(str(part) for part in command)
        console.print(f"[dim]{status.get('method')}:[/] `{rendered}`")
    else:
        console.print(f"[dim]{status.get('method')}: {status.get('explanation')}[/]")
    embedder = status.get("embedder")
    if embedder:
        console.print(f"[dim]embedder:[/] {embedder}")


def render_bench(result: Mapping[str, object]) -> None:
    """Render ``docir bench``: one row per strategy, then what was not scored."""
    strategies = result.get("strategies")
    rows = list(strategies) if isinstance(strategies, Sequence) else []
    if not rows:
        console.print("[dim]nothing scored — every task named only unknown ids[/]")
    else:
        limit = result.get("limit")
        table = Table(show_header=True, header_style="bold")
        table.add_column("strategy")
        table.add_column(f"recall@{limit}", justify="right")
        table.add_column(f"prec@{limit}", justify="right")
        table.add_column("MRR", justify="right")
        table.add_column("tasks", justify="right")
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            table.add_row(
                str(row.get("name", "")),
                f"{_as_float(row.get('recall')):.2f}",
                f"{_as_float(row.get('precision')):.2f}",
                f"{_as_float(row.get('mrr')):.2f}",
                str(row.get("tasks", 0)),
            )
        console.print(table)
        console.print(
            "[dim]`context` is the shipped default; `--expand 0` removes graph expansion, "
            "and the pair is what isolates the semantic signal from it.[/]"
        )

    # Named, never counted away: a fixture outlives the corpus it judges, and
    # dropping an id quietly shrinks recall's denominator — which *raises* the
    # score for the wrong reason.
    unresolved = result.get("unresolved")
    if isinstance(unresolved, Sequence) and not isinstance(unresolved, str) and unresolved:
        listed = ", ".join(str(item) for item in unresolved)
        console.print(f"[yellow]no document carries[/] {listed}")
    dropped = result.get("dropped")
    if isinstance(dropped, Sequence) and not isinstance(dropped, str) and dropped:
        listed = ", ".join(str(item) for item in dropped)
        console.print(f"[yellow]not scored, every id unknown:[/] {listed}")


def _as_float(value: object) -> float:
    """A score as a float; ``0.0`` for anything the payload did not carry."""
    return float(value) if isinstance(value, int | float) else 0.0


def render_upgrade(
    reindex: Mapping[str, object],
    agents: Sequence[Mapping[str, object]],
    findings: Sequence[Mapping[str, object]],
    upgraded_from: str | None = None,
) -> None:
    """Render the outcome of ``docir self upgrade``, step by step.

    Each line names the command it stands in for, because that is what the user
    would otherwise have run — and still can, when only one of them is what they
    need.
    """
    if upgraded_from is not None:
        # Equal means the installer had nothing to do — worth saying, because
        # "package 0.11.0 → 0.11.0" reads like a failed upgrade.
        moved = upgraded_from != __version__
        console.print(
            f"[cyan]package[/]   {upgraded_from} → {__version__}"
            if moved
            else f"[cyan]package[/]   {__version__} [dim](already the newest build)[/]"
        )
    skipped = reindex.get("documents_skipped")
    embedded = reindex.get("embeddings_recomputed")
    vectors = reindex.get("vectors_written")
    indexed = reindex.get("documents_indexed", 0)
    console.print(
        f"[cyan]reindex[/]   {indexed} documents, "
        f"{reindex.get('tags_indexed', 0)} tags"
        # The re-embedding always happened here; saying so is what stops the
        # next reader reaching for `reindex --embeddings` on top (issue-b24e14474820).
        # Both numbers, because they answer different questions and are ~4x apart:
        # the queue is keyed by document, while the runtime is linear in vectors —
        # each document writes one per `##` section as well as its own
        # (adr-927aa43d9635), so 315 re-embedded is 1,326 vectors.
        + (f", {embedded} re-embedded" if embedded else "")
        # Suppressed when the two agree, which is a corpus whose documents have
        # no `##` sections: "1 re-embedded (1 vectors)" carries no information
        # and is not even grammatical.
        + (f" ({vectors} vectors)" if embedded and vectors and vectors != embedded else "")
        # Same reason the package line spells out "already the newest build":
        # `upgrade` resyncs, so it re-saves nothing when this build already
        # indexed the store and no file moved — and a bare "0 documents" reads
        # like the rebuild failed rather than like there was none to do.
        + ("" if indexed else " [dim](index already built by this version)[/]")
        + (f"  [yellow]{skipped} skipped[/]" if skipped else "")
    )
    render_setup(agents)
    render_findings(findings, empty="no structural issues")


def render_doctor(report: Mapping[str, object]) -> None:
    """Render ``docir doctor``: the facts first, then what is wrong with them.

    Facts before findings, and never findings alone. Half of what doctor reports
    is only legible against the state that produced it — "12 documents have no
    current vector" is routine under the real model and an emergency under a
    leftover DOCIR_EMBEDDER — so the sections are printed even when nothing is
    wrong with them.
    """
    _doctor_section("install", _doctor_install(_submap(report, "installation")))
    _doctor_section("store", _doctor_store(_submap(report, "store")))
    _doctor_section("embed", _doctor_embedding(_submap(report, "embedding"), report.get("probe")))
    _doctor_section("daemon", _doctor_daemon(_submap(report, "daemon")))
    for peer in _maps(report.get("peers")):
        reason = str(peer.get("unavailable", ""))
        state = f"[yellow]{reason}[/]" if reason else "[green]readable[/]"
        _doctor_section("peer", f"{peer.get('home')} · {state}")
    findings = _maps(report.get("findings"))
    console.print("")
    if not findings:
        console.print("[green]nothing to report[/]")
        return
    for finding in findings:
        colour = "red" if finding.get("severity") == "error" else "yellow"
        console.print(f"[{colour}]{finding.get('kind')}[/]: {finding.get('message')}")
        fix = finding.get("fix")
        if fix:
            console.print(f"  [dim]->[/] {fix}")


def _doctor_section(label: str, line: str) -> None:
    console.print(f"[cyan]{label:<7}[/] {line}")


def _doctor_install(install: Mapping[str, object]) -> str:
    latest = install.get("latest")
    if latest is None:
        # Absent is *unknown*, never "up to date" — the rule every three-valued
        # field in docir follows.
        currency = "[dim]newest release unknown[/]"
    elif install.get("update_available"):
        currency = f"[yellow]{latest} available[/]"
    else:
        currency = "[green]current[/]"
    embedder = "" if install.get("fastembed_installed") else "  [red]fastembed not installed[/]"
    return f"docir {install.get('version')} [dim]({install.get('method')})[/]  {currency}{embedder}"


def _doctor_store(store: Mapping[str, object]) -> str:
    if not store.get("schema_loads"):
        return f"{store.get('home')}  [red]schema will not load[/]"
    if not store.get("index_present"):
        return f"{store.get('home')}  [red]no index[/]"
    documents = store.get("documents")
    on_disk = store.get("documents_on_disk")
    # Both numbers whenever they disagree: "179 documents" alone reads as a
    # healthy corpus in exactly the case where the index is behind the files.
    corpus = (
        f"{documents} documents"
        if documents == on_disk
        else f"[yellow]{documents} indexed of {on_disk} on disk[/]"
    )
    stale = store.get("stale_index_build")
    built = f"[yellow]built by {stale}[/]" if stale else "[green]built by this version[/]"
    drift = _count(store.get("schema_drift"))
    return f"{store.get('home')} [dim]({store.get('home_origin')})[/]  {corpus} · {built}" + (
        f" · [yellow]{drift} schema change(s)[/]" if drift else ""
    )


def _doctor_embedding(embedding: Mapping[str, object], probe: object) -> str:
    line = str(embedding.get("model", "?"))
    if embedding.get("env"):
        line += f"  [yellow](forced by DOCIR_EMBEDDER={embedding.get('env')})[/]"
    if isinstance(probe, Mapping):
        seconds = _as_float(probe.get("seconds"))
        line += (
            f"  [green]probe ok[/] [dim]({probe.get('dimensions')}d, {seconds:.1f}s)[/]"
            if probe.get("ok")
            else "  [red]probe failed[/]"
        )
    return line


def _doctor_daemon(daemon: Mapping[str, object]) -> str:
    if daemon.get("disabled_by_env"):
        return "[yellow]disabled by DOCIR_NO_DAEMON[/] [dim](model loads cold every command)[/]"
    if not daemon.get("running"):
        # Past tense: the snapshot is taken before this command dispatches, and
        # dispatching is what starts one. Saying "not running" in the present
        # would describe a moment that had already passed when it was printed.
        return "[dim]was not running when this command started[/]"
    served = daemon.get("serving") or "an unknown build"
    state = (
        f"[yellow]was serving stale code ({served}) — replaced by this command[/]"
        if daemon.get("stale_code")
        else f"[green]serving {served}[/]"
    )
    watching = "" if daemon.get("watching") else "  [dim]not watching docs/[/]"
    return f"pid {daemon.get('pid')} · {state}{watching}"


def _submap(report: Mapping[str, object], key: str) -> dict[str, object]:
    value = report.get(key)
    if not isinstance(value, Mapping):
        return {}
    return {str(name): item for name, item in value.items()}


def _maps(value: object) -> list[dict[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return []
    return [
        {str(name): entry for name, entry in item.items()}
        for item in value
        if isinstance(item, Mapping)
    ]


def render_message(message: str) -> None:
    console.print(message)
