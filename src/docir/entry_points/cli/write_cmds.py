"""The document write path: ``add``, ``update``, ``archive``, ``unarchive``, ``delete``.

The CLI is the only sanctioned way to change a file, so these five are the
whole of it. Each assembles a JSON payload and hands it to the executor;
the rules they enforce live in the documents module, not here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from docir.entry_points.cli import emit, rendering
from docir.entry_points.cli.body_input import resolve_body
from docir.entry_points.cli.runner import execute


def add(
    type: Annotated[str, typer.Option("--type", help="Document type.")],
    title: Annotated[str, typer.Option("--title", help="Document title.")],
    description: Annotated[
        str, typer.Option("--description", help="One-line summary, shown in every skeleton.")
    ],
    tags: Annotated[
        list[str] | None,
        typer.Option("--tags", help="Comma-separated, or repeat the flag."),
    ] = None,
    related: Annotated[
        list[str] | None,
        typer.Option(
            "--related",
            help="Comma-separated <id> or <id>:<kind> typed edges, or repeat the flag.",
        ),
    ] = None,
    status: Annotated[
        str | None,
        typer.Option("--status", help="Initial status; defaults to the type's default status."),
    ] = None,
    owner: Annotated[str | None, typer.Option("--owner", help="Steward for staleness.")] = None,
    code: Annotated[
        list[str] | None,
        typer.Option(
            "--code",
            help="Comma-separated repo-relative globs this document governs, or repeat "
            "the flag. Whatever the repository's .gitignore excludes is skipped, so a "
            "glob over a source tree "
            "does not drift when a build writes beside it; a '!' exclusion is refused, "
            'because these are pathlib globs where "!" is a literal. '
            'Example: --code "src/auth/**,src/api/routes.py"',
        ),
    ] = None,
    isolated: Annotated[
        str | None,
        typer.Option(
            "--isolated",
            help="Why this document is meant to carry no relations; exempts it from `orphan`.",
        ),
    ] = None,
    id: Annotated[
        str | None,
        typer.Option(
            "--id",
            help="Adopt an existing id (migrating a numbered corpus) instead of allocating.",
        ),
    ] = None,
    body: Annotated[
        str | None, typer.Option("--body", help="Body markdown as a literal string.")
    ] = None,
    body_file: Annotated[
        Path | None,
        typer.Option("--body-file", help="Read the body markdown from this UTF-8 file."),
    ] = None,
    stdin: Annotated[
        bool,
        typer.Option("--stdin", help="Read the body markdown from stdin; avoids shell escaping."),
    ] = False,
    wait_embeddings: Annotated[
        bool, typer.Option("--wait-embeddings", help="Block until embeddings are recomputed.")
    ] = False,
) -> None:
    """Create a new document with valid frontmatter.

    Ids are allocated for you. `--id` adopts one instead, for the single case it
    exists for: migrating a repository whose ADRs are already numbered, where
    dropping `adr-0007` breaks every historical cross-reference. It is refused if
    the id is taken or its prefix does not match the type, and the next
    allocation still lands past it.

    `--code` records the code this document governs, as repo-relative globs
    (`src/docir/platform/persistence/**`). Only the shape is validated — a
    pattern that matches nothing today is allowed, because a decision is often
    written before the code it decides, or after that code moved.

    A glob is watched from the moment you write it: docir records what each one
    matches now, and `docir check` reports `code-drifted` once that code moves.
    Nothing further is needed to turn this on —

        docir add --type decision --title "Ids come from a counter" \\
          --description "Why ids are allocated, never scanned for." \\
          --code "src/docir/modules/documents/application/services/id_*.py" \\
          --body "..."
        # edit that file, then:
        docir check | jq '.[] | select(.kind == "code-drifted") | .message'

    — and `docir update <id> --verified` upgrades the watch: from then on the
    finding is `code-changed`, which says the code moved since somebody *read*
    the document rather than since it declared the glob.

    A type may declare a body ceiling, and a create over it is refused with exit
    9 before anything is written:

        error: body is 9120 chars, over the 8000-char limit for type 'issue'
        — split it into linked documents, or raise `max_body_chars` for
        'issue' in docs-schema.yaml

    No type ships with one — set `max_body_chars: 8000` on a type in
    `docs-schema.yaml` to turn it on, `max_body_chars_enforce: false` beside it
    to warn instead of refuse. `docir schema show` prints the ceiling in force.
    """
    payload: dict[str, object] = {
        "type": type,
        "title": title,
        "description": description,
        "tags": emit.split_csv(tags),
        "related": emit.split_csv(related),
        "status": status,
        "owner": owner,
        "code": emit.split_csv(code),
        "isolated": isolated,
        "id": id,
        "body": resolve_body(body, body_file, stdin),
        "wait_embeddings": wait_embeddings,
    }
    emit.warn_on_global_fallback()
    data = execute("add", payload)
    _warn_on_body_limit(data)
    emit.emit_document(data)


def update(
    doc_id: Annotated[str, typer.Argument(help="Document id.")],
    status: Annotated[
        str | None, typer.Option("--status", help="Move the document to this status.")
    ] = None,
    set_type: Annotated[
        str | None,
        typer.Option("--type", help="Retype the document. The id never changes."),
    ] = None,
    set_title: Annotated[str | None, typer.Option("--set-title", help="Replace the title.")] = None,
    set_description: Annotated[
        str | None, typer.Option("--set-description", help="Replace the one-line summary.")
    ] = None,
    set_tags: Annotated[
        list[str] | None,
        typer.Option(
            "--set-tags",
            help='Replace the tags, comma-separated or repeated (pass "" to clear them).',
        ),
    ] = None,
    set_related: Annotated[
        list[str] | None,
        typer.Option(
            "--set-related",
            help="Replace the typed edges: comma-separated <id> or <id>:<kind>, or repeat "
            "the flag.",
        ),
    ] = None,
    set_owner: Annotated[str | None, typer.Option("--set-owner", help="Staleness steward.")] = None,
    set_isolated: Annotated[
        str | None,
        typer.Option(
            "--set-isolated",
            help=(
                "Why this document is meant to carry no relations; exempts it from `orphan`. "
                'Pass "" to withdraw the exemption and put it back in the queue.'
            ),
        ),
    ] = None,
    set_code: Annotated[
        list[str] | None,
        typer.Option(
            "--set-code",
            help="Comma-separated or repeated repo-relative globs this document governs "
            '(pass "" to clear them). A glob this adds is watched from now; one '
            "it keeps holds the baseline it already had, so re-declaring a "
            "pattern never clears a drift nobody has read. Ignored files are "
            "skipped and a '!' exclusion is refused, as for --code.",
        ),
    ] = None,
    verified: Annotated[
        bool,
        typer.Option(
            "--verified",
            help=(
                "Stamp today as the last-verified date, and record what the "
                "document's `code` globs match right now — upgrading them from "
                "`code-drifted` (moved since declared) to `code-changed` (moved "
                "since somebody read this). Stamp it only if you did read it."
            ),
        ),
    ] = False,
    clear_verified: Annotated[
        bool,
        typer.Option(
            "--clear-verified",
            help=(
                "Withdraw the verification, leaving no review window: the "
                "document ages from `created` again. Use it when a stamp asserts "
                "a review nobody did. Refused when none is standing."
            ),
        ),
    ] = False,
    append_section: Annotated[
        str | None,
        typer.Option("--append-section", help="Append the body text under this heading."),
    ] = None,
    replace_section: Annotated[
        str | None,
        typer.Option(
            "--replace-section", help="Overwrite this heading's section with the body text."
        ),
    ] = None,
    remove_section: Annotated[
        str | None,
        typer.Option("--remove-section", help="Delete this heading and the text under it."),
    ] = None,
    replace_body: Annotated[
        bool, typer.Option("--replace-body", help="Overwrite the whole body. Requires --force.")
    ] = False,
    body: Annotated[
        str | None, typer.Option("--body", help="The edit's text, as a literal string.")
    ] = None,
    body_file: Annotated[
        Path | None, typer.Option("--body-file", help="Read the edit's text from this UTF-8 file.")
    ] = None,
    stdin: Annotated[
        bool,
        typer.Option("--stdin", help="Read the edit's text from stdin; avoids shell escaping."),
    ] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Allow --replace-body to overwrite the existing body.")
    ] = False,
    override: Annotated[
        bool,
        typer.Option(
            "--override",
            help="Force an illegal status transition (warns; last resort).",
        ),
    ] = False,
    wait_embeddings: Annotated[
        bool, typer.Option("--wait-embeddings", help="Block until embeddings are recomputed.")
    ] = False,
) -> None:
    """Update a document (metadata patch and/or a body edit).

    --type retypes the document. Its id is left alone, prefix included: the id is
    the only address the corpus has for it, so `adr-3f9a2b1c7d4e` stays `adr-3f9a2b1c7d4e`
    under a type whose prefix is something else. A prefix records which type
    minted an id, not which type owns it now. The file moves into the new type's
    directory, keeping its filename.

    The status is carried over if the new type declares it, and the write is
    refused if it does not — pass --status alongside --type to say what it
    becomes. That is a membership check, not a transition: the type being left
    has no say over the statuses of the one being entered.

    Retyping works even when the current type is one the schema no longer
    declares, which is how a corpus leaves a type that `disable_types:` removed.

    A body edit takes at most one mode. --append-section and --replace-section
    both write the heading line themselves, so --body carries only the text that
    goes *under* it: pasting back what `get --section` returned — which does
    include the heading — is refused rather than writing the heading twice.

    --remove-section deletes a heading and everything under it, and takes no
    --body — passing one is refused, since "delete this text" is not what it
    does. It is the way out of a body that already spells one heading twice,
    which --replace-section cannot undo (it keeps the first heading line by
    contract) and --append-section only adds to:

        docir update adr-3f9a2b1c7d4e --remove-section "Notes"

    A repeated heading resolves to the first, here as everywhere, so removing the
    second of two means running it twice. `docir lint --deep` names the documents
    that have one.

    --verified stamps today; --clear-verified takes the stamp back, erasing
    `verified` and stamping `revoked` in its place. Editing the title, the
    description or the body of a verified document does the same thing by
    itself: the review covered that content, the content moved, so the
    verification is withdrawn and the cadence restarts from the day it was:

        docir update adr-3f9a2b1c7d4e --verified          # verified: 2026-09-05
        docir update adr-3f9a2b1c7d4e --append-section H --body "..."
                                                          # revoked: 2026-09-05
        docir update adr-3f9a2b1c7d4e --clear-verified    # a stamp nobody earned
                                                          # -> ages from `created`

    Pass --verified alongside the edit to keep the stamp — that is "I rewrote it
    and re-read it". A status, tag, type or edge change is not a content change
    and leaves the verification standing. `docir query --stale` lists what the
    cadence has caught up with; `docir query --expr "revoked"` lists what lapsed.

    --verified also digests the text it covered, so `docir check` reports
    (`verification-outdated`) a document edited *around* the CLI — a hand-edit, a
    merge, or an older docir — where the stamp still stands over text nobody
    read. Clear it by re-reading and stamping again, or by withdrawing it.

    When the type declares `max_body_chars`, an edit that leaves the body over
    that ceiling **and longer than it already was** is refused with exit 9:

        docir update adr-3f9a2b1c7d4e --append-section "Notes" --body "..."
        error: body is 9120 chars, over the 8000-char limit for type 'decision'

    Growth is the trigger, not size. A document already over its ceiling still
    takes --set-title, --status, --set-tags, --type and a *shorter*
    --replace-body, so the edit that fixes it is never the edit that is blocked.
    `max_body_chars_enforce: false` on the type warns instead, on stderr and as
    `body_limit_notice` in the JSON.
    """
    body_text = resolve_body(body, body_file, stdin, default="")
    payload: dict[str, object] = {
        "doc_id": doc_id,
        "status": status,
        "set_type": set_type,
        "set_title": set_title,
        "set_description": set_description,
        "set_tags": None if set_tags is None else emit.split_csv(set_tags),
        "set_related": None if set_related is None else emit.split_csv(set_related),
        "set_owner": set_owner,
        "set_isolated": set_isolated,
        "set_code": None if set_code is None else emit.split_csv(set_code),
        "mark_verified": verified,
        "clear_verified": clear_verified,
        "append_section": [append_section, body_text] if append_section else None,
        "replace_section": [replace_section, body_text] if replace_section else None,
        "remove_section": remove_section,
        # Carried whole as well as folded into a mode above: --remove-section
        # consumes no text, and the dispatcher refuses it rather than dropping
        # it silently.
        "body": body_text,
        "replace_body": body_text if replace_body else None,
        "force": force,
        "allow_transition_override": override,
        "wait_embeddings": wait_embeddings,
    }
    emit.warn_on_global_fallback()
    data = execute("update", payload)
    forced = data.get("forced_transition") if isinstance(data, dict) else None
    if forced:
        # Loud at the moment of the bypass, but not written to the file: git
        # records the status change, and docir has no actors to attribute it to.
        rendering.render_warning(f"forced illegal transition {forced}")
    _warn_on_body_limit(data)
    emit.emit_document(data)


def _warn_on_body_limit(data: object) -> None:
    """Say so when a write went over a ceiling the type declined to enforce.

    The write succeeded, so this is stderr rather than an exit code — but it is
    louder than nothing, because `max_body_chars_enforce: false` is a store
    saying "tell me", not "ignore it". The JSON payload carries the same string
    in `body_limit_notice`, so an agent on either transport sees it.
    """
    notice = data.get("body_limit_notice") if isinstance(data, dict) else None
    if notice:
        rendering.render_warning(str(notice))


def archive(doc_id: Annotated[str, typer.Argument(help="Document id.")]) -> None:
    """Soft-remove a document from active search."""
    emit.emit_document(execute("archive", {"doc_id": doc_id}))


def unarchive(doc_id: Annotated[str, typer.Argument(help="Document id.")]) -> None:
    """Restore an archived document to active search."""
    emit.emit_document(execute("unarchive", {"doc_id": doc_id}))


def delete(
    doc_id: Annotated[str, typer.Argument(help="Document id.")],
    force: Annotated[
        bool,
        typer.Option(
            "--force", help="Delete even while documents relate to it, stripping those edges."
        ),
    ] = False,
) -> None:
    """Hard-delete a document's file and index rows.

    A forced delete also strips the edge from every document that referenced this
    one, and names them — a delete that silently rewrites other people's files
    would be worse than one that refuses.

    An id that **more than one file claims** is refused whatever flags you pass,
    naming the files. `--force` overrides inbound references, not ambiguity about
    which document is meant — the edges it would strip cannot be told apart by
    id. That state is what a merge of two branches on sequential ids produces;
    `docir check` reports it as `duplicate-id` and `docir check --fix` repairs
    it, re-issuing all but one and renaming the file to match:

        docir check | jq -r '.[] | select(.kind=="duplicate-id") | .message'
        docir check --fix
        docir delete <id>
    """
    data = execute("delete", {"doc_id": doc_id, "force": force})
    raw = data.get("unlinked") if isinstance(data, dict) else None
    unlinked = [str(item) for item in raw] if isinstance(raw, list) else []
    message = f"deleted {doc_id}"
    if unlinked:
        message += f"; unlinked from {', '.join(unlinked)}"
    emit.emit_or_message(data, message)


def register(app: typer.Typer) -> None:
    """Register these commands on the root app, in the order `--help` prints them."""
    app.command()(add)
    app.command()(update)
    app.command()(archive)
    app.command()(unarchive)
    app.command()(delete)
