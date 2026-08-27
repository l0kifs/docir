"""Every parameter `docir --help` shows must say what it does.

`--help` is the whole discovery surface. docir's own README sells the CLI as the
agent contract, and an agent reading `--help` to decide whether `--flush` is
what it wants gets a flag name and a blank column. Forty parameters across
fourteen commands were in that state at once — `query --tag`, `add --status`,
`update --replace-body`, every `doc_id` argument — because nothing checked.

An audit finds them; only a test keeps them gone. The oracle is the command tree
Click builds, the same object `--help` renders from, so a parameter added without
`help=` fails here in the commit that adds it rather than on the day somebody
reads the output.

Hidden parameters are exempt: they are deliberately absent from `--help`, so
there is no text for a user to miss.
"""

from __future__ import annotations

from typing import Any

import typer.main

from docir.entry_points.cli.app import app


def _undocumented() -> list[str]:
    """Every `<command> <param>` the help output would show with no description."""
    missing: list[str] = []

    def walk(command: Any, path: list[str]) -> None:
        subcommands = getattr(command, "commands", None)
        if subcommands:
            for name, sub in subcommands.items():
                walk(sub, [*path, name])
            return
        for param in getattr(command, "params", ()):
            if getattr(param, "hidden", False) or param.name == "help":
                continue
            if getattr(param, "help", None):
                continue
            flag = param.opts[0] if getattr(param, "opts", None) else param.name
            missing.append(f"{' '.join(path) or 'docir'} {flag}")

    walk(typer.main.get_command(app), [])
    return missing


def test_every_visible_parameter_has_help() -> None:
    undocumented = _undocumented()
    assert not undocumented, (
        "these parameters appear in `--help` with no description:\n  " + "\n  ".join(undocumented)
    )
