"""Rebuilding, checking and reporting: the commands that are not the write path.

``reindex`` restores the derived index from the files, ``check`` and ``lint``
are the two non-blocking finding tiers, ``doctor`` reports the environment,
and ``bench`` scores this store's own retrieval.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Annotated

import typer
import yaml

from docir import __version__
from docir.entry_points import doctor as doctor_report
from docir.entry_points.cli import emit, rendering
from docir.entry_points.cli.runner import execute, get_state, run_local, try_execute, use_json
from docir.modules.documents.api import DEFAULT_CONTEXT_EXPAND
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

    Every document this run re-saves is queued for embedding and the drain runs
    before it returns, recomputing only the vectors whose inputs — model, text,
    chunking — no longer match what is stored, so an unchanged corpus reports
    `embeddings_recomputed: 0` (issue-77dd42e3a03a). After a model or chunking
    change that is every vector, so a full rebuild is still the way to recompute
    them all — there is no flag for that, because there was nothing for one to
    add (adr-6a4718fa7a7d).
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
    against: Annotated[
        str | None,
        typer.Option(
            "--against",
            metavar="REF",
            help="Also report ids new on this branch that this git ref already uses.",
        ),
    ] = None,
    fix: Annotated[
        bool,
        typer.Option(
            "--fix",
            help="Repair what can be repaired (duplicate ids, dead edges) and file the "
            "evidence nothing else can: the code baselines `code-unwatched` names, and "
            "the store format the schema needs.",
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

    `--against <ref>` turns this into a **pre-merge** gate. Two branches cut from
    one base each allocate the next free sequential id; both are correct on their
    own and neither can see the other, so the collision only surfaces when the
    second one merges — by which point renumbering is a conflict for whoever
    merged second rather than that branch's own cheap edit. Naming the base ref
    asks the question while it is still cheap:

        git fetch origin main
        docir check --against origin/main --strict     # exits 1 on a collision

    Two error findings come from it, and only from it. `branch-id-collision`
    names your id, your file and theirs; there is no renumber command, because
    an id is a document's only address, so the repair is to bring the base in
    and let `--fix` re-issue yours — theirs was committed first, so theirs keeps
    the number:

        git merge origin/main
        docir check --fix
        docir check --against origin/main --strict     # now exits 0

    `unreadable-ref` means the ref could not be read at all — an unknown ref, or
    a clone whose history does not reach it — and it is an error on purpose: a
    pre-merge gate that passed because it could not look is indistinguishable
    from a clean branch.

    One warning is about a *silence*. `code-unwatched` names a `code:` glob that
    exists on disk and that no digest is watching, so no edit to it will ever be
    reported — the state a document lands in when its glob was declared before
    the code it governs was written. `--fix` is the repair, and watching starts
    at the next change rather than recovering the one you missed:

        docir check | jq -r '.[] | select(.kind=="code-unwatched") | .message'
        docir check --fix

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
    if fix and against:
        # Refused rather than ignored: the repair for a collision with another
        # ref is to renumber *here*, deliberately, and `--fix` re-issuing ids
        # locally could mint straight into the same ref again. Silently dropping
        # one of two flags somebody passed is the worse answer.
        raise typer.BadParameter(
            "use --against or --fix, not both: a collision with another ref is "
            "renumbered here on purpose, and --fix cannot see that ref"
        )
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
        data = execute("check", {"against": against} if against else {})
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

    The `embedding` section is where "why is docir eating my CPU" is answered.
    `threads` is the cap in force, and absent means uncapped — fastembed's own
    behaviour, which is every core, and what a laptop notices while the model
    warms, a reindex runs or a `context` query is embedded:

        DOCIR_EMBED_THREADS=2 docir reindex
        docir doctor | jq '.embedding'
        {"model": "fastembed:BAAI/bge-small-en-v1.5",
         "cache": "~/.docir/models", "threads": 2}

    Changing it replaces a running daemon, which resolves the model once at
    spawn — so the cap takes effect on the next command rather than needing
    `docir daemon stop`. This section reports the *environment you are running
    in*, like every other field here, which is the snapshot taken before the
    command dispatches.

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
    # The ordering rule (snapshot before anything dispatches) lives in
    # `build_report`, shared with the MCP tool so the two transports cannot come
    # to disagree about the same machine. The spinner is this caller's, because
    # only a TTY has one: `--probe` is the one thing doctor does that is not
    # instant, since its whole job is to load the model.
    progress = (
        rendering.progress("loading the embedding model (may download ~67MB)")
        if probe
        else contextlib.nullcontext()
    )
    with progress:
        report = run_local(
            lambda: doctor_report.build_report(
                state.settings,
                __version__,
                lambda: try_execute("store_status", {}),
                probe=probe,
            )
        )
    _emit_doctor(report)
    if strict and report.errors:
        raise typer.Exit(code=1)


def lint(
    deep: Annotated[
        bool, typer.Option("--deep", help="Actually run the checks; without it lint does nothing.")
    ] = False,
) -> None:
    """Tier 2 advisory heuristics — suggestions, never rules.

    Nothing here blocks a write or moves an exit code, which is why `--deep` is
    required: every finding is a judgement somebody has to make.

    `duplicate` is the one no other command can answer. It names two documents
    whose whole-document vectors sit at or above **0.90 cosine** — the same
    document written twice, which `docir search` cannot find because the two
    copies share no phrasing. A pair already joined by a `related` edge is never
    reported: the author has said how they relate, so the only findings left are
    the unnoticed ones.

        docir lint --deep | jq -r '.[] | select(.kind=="duplicate") | .message'
        docir get adr-3f9a2b1c7d4e adr-0a1b2c3d4e5f

    Read both, then pick an exit — an edge, not a delete. `--set-related`
    *replaces* the edge list, so carry the edges `docir get` just showed you:

        docir update adr-3f9a2b1c7d4e --set-related "arch-0002:refines,adr-0a1b2c3d4e5f"
        docir update adr-0a1b2c3d4e5f --status superseded

    Linking is also how a false positive is dismissed, since the check stops
    asking about a pair somebody has explained.

    **0.90 is the copy-paste bar, not the paraphrase bar.** Two documents
    recording one decision in independent words measured 0.83 here and are not
    reported. The check that catches those runs *before* the write: `docir
    context "<the description you are about to file>"`, judged on `similarity`.

    docir finds duplication and never finds disagreement — nothing compares two
    claims. Record one yourself with `--set-related <id>:contradicts`; it is
    symmetric and a successor kind, so one edge makes `docir context` and
    `docir get` surface each document from the other from then on.

    The rest are shape: `scope-creep` and `oversized-section` (a document or
    section too big to retrieve well), `ambiguous-heading` (one heading twice,
    so a section read reaches only the first), `unqualified-section-ref`,
    `unresolved-mention`, and `broken-expression` (a `--expr` documented in a
    body that would not run).
    """
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
    """Render the shared payload, as a table or as JSON."""
    payload = doctor_report.as_payload(report)
    state = get_state()
    if use_json(state):
        rendering.emit_json(payload, trim=state.trim)
    else:
        rendering.render_doctor(payload)


def register(app: typer.Typer) -> None:
    """Register these commands on the root app, in the order `--help` prints them."""
    app.command()(reindex)
    app.command()(check)
    app.command()(doctor)
    app.command()(lint)
    app.command()(bench)
    app.command()(embed)
