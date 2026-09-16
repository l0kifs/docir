"""Rebuilding, checking and reporting: the commands that are not the write path.

``reindex`` restores the derived index from the files, ``check`` and ``lint``
are the two non-blocking finding tiers, ``doctor`` reports the environment,
and ``bench`` scores this store's own retrieval.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer
import yaml

from docir import __version__
from docir.entry_points import doctor as doctor_report
from docir.entry_points.cli import emit, rendering
from docir.entry_points.cli.runner import execute, get_state, run_local, try_execute, use_json
from docir.modules.documents.api import DEFAULT_CONTEXT_EXPAND, STORE_FORMAT
from docir.platform.errors import ValidationError


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
        typer.Option(
            "--fix",
            help="Repair what can be repaired (duplicate ids, dead edges) and file the "
            "evidence nothing else can: code baselines, and the store format the schema "
            "needs.",
        ),
    ] = False,
) -> None:
    """Tier 1 structural checks (cycles, orphans, layering, dangling, dup ids).

    Findings carry a severity. `error` means the corpus is broken — a duplicate
    id hiding a document, an edge pointing at nothing, a file that will not
    parse. `warning` describes shape or age: orphans, cycles, layering, staleness,
    unknown types, and a `code` glob that no longer matches anything (checked
    only when the store sits in a repository — there is nothing to resolve a
    pattern against otherwise).

    One warning is about no document at all. `store-format-undeclared` means
    `docs-schema.yaml` uses something a docir older than it cannot parse — and a
    schema resolves before anything opens, so that build refuses the *whole*
    store, with a message about a key rather than about versions. `docir check
    --fix` records `store_format:` so the refusal names the version instead:

        docir check | jq -r '.[] | select(.kind == "store-format-undeclared") | .message'
        docir check --fix   # writes the line, keeps the file's comments

    Run it once after adopting a store an older docir wrote, and whenever you
    edit `docs-schema.yaml`. The damage it predicts never lands on you — it
    lands on a teammate's build, or on a repository reading this store as a
    peer, neither of which is here to complain.

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

    The `compat` section is facts rather than findings — how this store and this
    build relate, and what this build is going to stop doing:

        docir doctor | jq '.compat'
        {
          "store_format": {"declared": 2, "required": 2, "supported": 2},
          "deprecations": [{"subject": "--include-resolved",
                            "replacement": "--include-inactive",
                            "sunset": "2027-03-01", "overdue": false}]
        }

    `store_format` answers "can my teammate read this store" without running the
    experiment: compare `required` against their docir's `supported`. Each
    deprecation carries the date it stops working, so "is this urgent" is
    answerable here rather than by asking. A future date is data and raises no
    finding; a date that has passed is an error, because the removal it named
    was not made.

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
        # How this store and this build relate, as facts rather than findings:
        # the two numbers a teammate compares against their own docir, and every
        # surface this build has announced it will stop accepting. Dated, so
        # "is this urgent" is answerable without asking anybody
        # (adr-6d4d43d44075).
        "compat": {
            "store_format": {
                "declared": environment.store_format_declared,
                "required": environment.store_format_required,
                "supported": STORE_FORMAT,
            },
            "deprecations": [
                {
                    "subject": entry.subject,
                    "replacement": entry.replacement,
                    "sunset": entry.sunset.isoformat(),
                    "overdue": overdue,
                    "note": entry.note,
                }
                for entry, overdue in environment.deprecations
            ],
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


def register(app: typer.Typer) -> None:
    """Register these commands on the root app, in the order `--help` prints them."""
    app.command()(reindex)
    app.command()(check)
    app.command()(doctor)
    app.command()(lint)
    app.command()(bench)
    app.command()(embed)
