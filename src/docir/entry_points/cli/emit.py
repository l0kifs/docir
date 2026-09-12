"""Rendering the executor's replies, and the coercions that precede it.

Every command ends the same way — take the JSON the executor returned, and
either print it verbatim for an agent or render it for a person. These are the
handful of shapes that reply comes in, kept together so a command module holds
its flags and its docstring and nothing else.

They were private helpers in :mod:`app` while it was the only caller. Splitting
the commands out made them cross a module boundary, and a name should say so.
"""

from __future__ import annotations

from docir.entry_points.cli import rendering
from docir.entry_points.cli.runner import get_state, use_json


def split_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def wants_inactive(include_inactive: bool, include_resolved: bool) -> bool:
    """Resolve the flag and its deprecated alias, warning on the old spelling.

    The flag was `--include-resolved`, but the concept it controls is the
    schema's `inactive_statuses` — `rejected`/`superseded` for a decision,
    `deprecated` for architecture, `retired` for a policy. `resolved` is a
    status of only two of the fifteen shipped types, so the name described the
    minority case and gave a user querying decisions no reason to guess which
    flag surfaces superseded ones. The wire field was already `include_inactive`.

    The old spelling keeps working (hidden, undocumented) because it appears in
    scripts and in agent instructions installed before this release. The notice
    goes to stderr so a captured JSON payload on stdout is untouched.
    """
    if include_resolved:
        rendering.render_warning(
            "--include-resolved is deprecated; use --include-inactive "
            "(it covers every inactive status, not just `resolved`)."
        )
    return include_inactive or include_resolved


def as_list(data: object) -> list[dict[str, object]]:
    # Tuples too, not just lists: ``dataclasses.asdict`` preserves the field's
    # container type, so a DTO with ``tuple`` fields arrives as a tuple in-process
    # and as a JSON array over the daemon. Accepting only ``list`` made the table
    # renderer silently show nothing while ``--json`` printed the full payload.
    if not isinstance(data, list | tuple):
        return []
    result: list[dict[str, object]] = []
    for item in data:
        if isinstance(item, dict):
            result.append({str(key): value for key, value in item.items()})
    return result


def as_mapping(data: object) -> dict[str, object]:
    """One response object, or an empty mapping if the payload was not one."""
    return {str(key): value for key, value in data.items()} if isinstance(data, dict) else {}


def as_mappings(data: object) -> list[dict[str, object]]:
    """Coerce a dispatcher payload into typed mappings, dropping anything else.

    The executor's return type is deliberately ``object`` — one boundary, many
    commands — so every caller that wants fields has to narrow. Rebuilding the
    dicts rather than casting keeps the key type honest: the wire is JSON, where
    keys are strings whatever the producer thought.

    Tuples count as lists here: in-process a dataclass field arrives as the
    tuple it was declared as, and over the socket the same field arrives as a
    JSON array. Accepting only one of the two makes a command work in one mode
    and silently return nothing in the other.
    """
    if not isinstance(data, list | tuple):
        return []
    return [
        {str(key): value for key, value in row.items()} for row in data if isinstance(row, dict)
    ]


def with_store(row: dict[str, object]) -> dict[str, object]:
    """Name the store a deep read came from, without overwriting a peer's.

    Federation stamps a document with the store that answered for it, so the
    local home may only fill the gap when nothing did — writing it unconditionally
    told the reader that a peer's document lived here.
    """
    return {"store": str(get_state().settings.home), **row}


def emit_document(data: object) -> None:
    state = get_state()
    if isinstance(data, dict):
        data = with_store(as_mapping(data))
    if use_json(state):
        rendering.emit_json(data, trim=state.trim)
    elif isinstance(data, dict):
        rendering.render_document({str(key): value for key, value in data.items()})


def emit_batch(data: object) -> None:
    """Render a batched deep read: the documents, then the addresses that missed.

    The misses go to stderr in the human view and stay in the payload in the
    JSON one. They are not an error — the request succeeded and most of it
    resolved — but they are the half a reader would otherwise have to notice by
    counting the panels.
    """
    state = get_state()
    payload = as_mapping(data)
    documents = [with_store(row) for row in as_mappings(payload.get("documents"))]
    missing = as_mappings(payload.get("missing"))
    if use_json(state):
        rendering.emit_json({"documents": documents, "missing": missing}, trim=state.trim)
        return
    for row in documents:
        rendering.render_document(row)
    for row in missing:
        rendering.render_warning(f"{row.get('ref')}: {row.get('error')}")


def emit_document_list(data: object) -> None:
    state = get_state()
    if use_json(state):
        rendering.emit_json(data, trim=state.trim)
    else:
        rendering.render_document_list(as_list(data))


def emit_or_message(data: object, message: str) -> None:
    state = get_state()
    if use_json(state):
        rendering.emit_json(data, trim=state.trim)
    else:
        rendering.render_message(message)


def warn_on_global_fallback() -> None:
    """Say so when a command is about to use the global store from inside a repo.

    Called on reads as well as writes. The read paths deliberately do *not* carry
    the `store` field the write paths do: it is one absolute path, identical for
    every row, and a list response has nowhere to put it once — per-row it would
    cost far more than the 4.7% one small field added to `context`. A stderr
    warning answers the same question ("am I reading the corpus I think I am?")
    for nothing on stdout.

    The reported `path` is relative to the *store*, so in a repository that was
    never `docir init`-ed it reads as repo-local while the file goes to the
    user's home directory — ungitted and invisible to teammates, with no error
    at any point. Only this case warns: outside a repository the global store is
    unambiguous, and warning on correct usage is how a check gets ignored.
    """
    settings = get_state().settings
    if not settings.is_unintended_global_fallback():
        return
    rendering.render_warning(
        f"using the global store {settings.home} — this directory is inside a "
        "git repository with no .docir/. Run `docir init` to scope docs to the repo, "
        "or set DOCIR_HOME to silence this."
    )
