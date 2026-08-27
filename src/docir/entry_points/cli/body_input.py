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
        # Unwrapped, a missing path or a latin-1 draft escaped as a raw traceback
        # and exit 1, while every other bad argument on the same command printed a
        # message and exit 2. The path is the thing the user typed, so it is what
        # the message has to name.
        try:
            return body_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise typer.BadParameter(f"--body-file {body_file}: no such file") from None
        except IsADirectoryError:
            raise typer.BadParameter(f"--body-file {body_file}: is a directory") from None
        except UnicodeDecodeError:
            raise typer.BadParameter(
                f"--body-file {body_file}: not valid UTF-8; re-save the file as UTF-8"
            ) from None
        except OSError as exc:
            raise typer.BadParameter(f"--body-file {body_file}: {exc.strerror}") from None
    if read_stdin:
        return sys.stdin.read()
    return default
