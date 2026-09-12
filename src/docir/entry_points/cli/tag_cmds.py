"""The ``docir tag`` subcommands: the registry every document's tags resolve against."""

from __future__ import annotations

from typing import Annotated

import typer

from docir.entry_points.cli import emit, rendering
from docir.entry_points.cli.runner import execute, get_state, use_json
from docir.modules.tags.api import DEFAULT_TAG_PAGE

tag_app = typer.Typer(help="Manage the tag registry.", no_args_is_help=True)


@tag_app.command("add")
def tag_add(
    key: Annotated[str, typer.Argument(help="Tag key to register.")],
    description: Annotated[
        str, typer.Option("--description", help="What the tag means; shown by `tag list`.")
    ],
) -> None:
    """Register a new tag."""
    data = execute("tag_add", {"key": key, "description": description})
    emit.emit_or_message(data, f"registered tag {key}")


@tag_app.command("list")
def tag_list(
    limit: Annotated[
        int, typer.Option("--limit", help="Maximum tags to return.")
    ] = DEFAULT_TAG_PAGE,
    offset: Annotated[int, typer.Option("--offset", help="Tags to skip; page with --limit.")] = 0,
) -> None:
    """List registered tags, key-ordered, with a usage count each.

    `usage` counts the indexed documents carrying the tag, archived included —
    the same set `tag rm` refuses to remove over, so `0` means the tag is dead
    and `tag rm` will take it without --force.

    Paged: a page shorter than --limit means you have reached the end. There is
    no total in the response — it is a bare JSON array, and a wrapper to carry
    one would break every existing caller.
    """
    data = execute("tag_list", {"limit": limit, "offset": offset})
    state = get_state()
    if use_json(state):
        rendering.emit_json(data, trim=state.trim)
    else:
        rendering.render_tags(emit.as_list(data))


@tag_app.command("rename")
def tag_rename(
    old: Annotated[str, typer.Argument(help="Existing tag key.")],
    new: Annotated[str, typer.Argument(help="New tag key.")],
    merge: Annotated[
        bool,
        typer.Option("--merge", help="Fold `old` into an existing `new` instead of failing."),
    ] = False,
) -> None:
    """Rename a tag across the registry and all documents.

    Renaming onto a tag that already exists is refused unless you pass --merge,
    which folds the two together: every document carrying `old` gets `new`, a
    document carrying both keeps one, and `new`'s description survives. Without
    the flag the refusal stands — a merge discards a description, which is not
    what someone fixing a typo means.
    """
    data = execute("tag_rename", {"old": old, "new": new, "merge": merge})
    touched = data.get("documents") if isinstance(data, dict) else None
    count = len(touched) if isinstance(touched, list) else 0
    verb = "merged" if merge else "renamed"
    emit.emit_or_message(data, f"{verb} {old} -> {new} across {count} document(s)")


@tag_app.command("rm")
def tag_rm(
    key: Annotated[str, typer.Argument(help="Tag key to remove.")],
    force: Annotated[
        bool, typer.Option("--force", help="Remove even while documents still carry the tag.")
    ] = False,
) -> None:
    """Remove a tag (blocked while in use unless forced)."""
    data = execute("tag_remove", {"key": key, "force": force})
    stripped = data.get("documents") if isinstance(data, dict) else None
    count = len(stripped) if isinstance(stripped, list) else 0
    message = f"removed tag {key}"
    if count:
        message += f"; stripped it from {count} document(s)"
    emit.emit_or_message(data, message)
