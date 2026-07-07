"""Resolve document body text from ``--body`` / ``--body-file`` / ``--stdin``.

``--stdin`` is the most agent-friendly option: it avoids shell-escaping issues
with multi-line markdown.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer


def resolve_body(
    body: str | None,
    body_file: Path | None,
    read_stdin: bool,
    *,
    default: str = "",
) -> str:
    """Return the body text from exactly one of the three sources."""
    sources = [body is not None, body_file is not None, read_stdin]
    if sum(sources) > 1:
        raise typer.BadParameter("use only one of --body, --body-file, --stdin")
    if body is not None:
        return body
    if body_file is not None:
        return body_file.read_text(encoding="utf-8")
    if read_stdin:
        return sys.stdin.read()
    return default
