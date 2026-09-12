"""The ``docir schema`` subcommands: show the merged schema, validate the file."""

from __future__ import annotations

from dataclasses import asdict

import typer

from docir.entry_points.cli import rendering
from docir.entry_points.cli.runner import get_state, run_local, use_json
from docir.entry_points.composition import SchemaValidation, validate_schema
from docir.modules.documents.api import describe_schema, load_schema

schema_app = typer.Typer(help="Inspect and validate the document schema.", no_args_is_help=True)


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
    """Check docs-schema.yaml parses and merges cleanly; exit nonzero if not.

    Rejects a status name that no type declares — a transition target, a
    `default_status`, or an `inactive_statuses` entry. That typo used to load
    happily and surface later as "invalid transition 'open' -> 'closed'",
    naming a status that IS declared and pointing at the write rather than the
    schema.

    A "dead end" warning (a live status with no outgoing transitions) was built
    and then dropped: measured against the bundled profiles it fired on 5 of the
    15 shipped types — `release_note.published`, `postmortem.published`,
    `experiment.complete`, `hypothesis.supported`, `obligation.breached` — every
    one a correct terminal state for a document that stays relevant. A warning
    that fires on the product's own defaults is issue-40d1792bc9f9 again.

    It also reports what the schema costs the corpus: how many documents carry a
    type, status, required field or relation kind this schema does not accept.
    That is `docir check`'s answer, given by the command you actually run after
    editing the schema — which used to say `valid: true` while a corpus fell out
    of the type system. The exit code does not change: the file is valid, and it
    is the documents that have moved. Read from the files rather than the index,
    since a schema edit is a hand edit and that is exactly when the index is
    behind.
    """
    settings = get_state().settings
    payload = _validation_payload(run_local(lambda: validate_schema(settings)))
    state = get_state()
    if use_json(state):
        rendering.emit_json(payload, trim=state.trim)
    else:
        rendering.render_schema_valid(payload)


def _validation_payload(result: SchemaValidation) -> dict[str, object]:
    """`docir schema validate` as JSON. `valid` stays first and stays a bool."""
    return {
        "valid": True,
        "path": str(result.path),
        "types": result.types,
        "documents": result.corpus.documents,
        "unreadable": result.corpus.unreadable,
        "affected": result.corpus.affected,
        "findings": [asdict(finding) for finding in result.corpus.findings],
    }


def _emit_schema(data: dict[str, object]) -> None:
    state = get_state()
    if use_json(state):
        rendering.emit_json(data, trim=state.trim)
    else:
        rendering.render_schema(data)
