"""The ``docir agent`` subcommands: install and refresh the packaged instructions."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from docir import __version__
from docir.entry_points.cli import rendering
from docir.entry_points.cli.runner import get_state, run_local, use_json
from docir.modules.agents.api import (
    AGENT_NAMES,
    DEFAULT_AGENTS,
    InstalledFile,
    InstallRequest,
    SetupResult,
    UpdateRequest,
    build_agent_service,
)

agent_app = typer.Typer(help="Install AI-assistant instructions for docir.", no_args_is_help=True)


@agent_app.command("install")
def agent_install(
    directory: Annotated[Path, typer.Argument(help="Project directory.")] = Path("."),
    agent: Annotated[
        list[str] | None,
        typer.Option("--agent", help=f"Target(s): {', '.join(AGENT_NAMES)}. Repeatable."),
    ] = None,
    use_global: Annotated[
        bool,
        typer.Option("--global", help="Install the skill under ~/ instead of the project."),
    ] = False,
) -> None:
    """Install docir's agent instructions (a Claude skill; AGENTS.md links to it)."""
    service = build_agent_service(__version__)
    request = InstallRequest(
        project_root=directory.resolve(),
        global_root=Path.home(),
        agents=tuple(agent) if agent else DEFAULT_AGENTS,
        use_global=use_global,
    )
    _emit_setup(run_local(lambda: service.install(request)))


@agent_app.command("update")
def agent_update(
    directory: Annotated[Path, typer.Argument(help="Project directory.")] = Path("."),
    agent: Annotated[
        list[str] | None,
        typer.Option("--agent", help="Add a target that isn't installed yet. Repeatable."),
    ] = None,
    use_global: Annotated[
        bool,
        typer.Option("--global", help="Refresh the skill under ~/ instead of the project."),
    ] = False,
) -> None:
    """Refresh already-installed agent instructions to the current docir version."""
    service = build_agent_service(__version__)
    request = UpdateRequest(
        project_root=directory.resolve(),
        global_root=Path.home(),
        agents=tuple(agent) if agent else (),
        use_global=use_global,
    )
    _emit_setup(run_local(lambda: service.update(request)))


def _setup_file(file: InstalledFile) -> dict[str, object]:
    """The one JSON shape for an installed file — `agent` and `self upgrade` share it.

    There were two of these, and adding a field to one is how `self upgrade`
    came to report an install without saying which reference files it wrote.
    Both commands describe the same event, so one of them describing it
    differently is always a defect, never a choice.
    """
    return {
        "target": file.target,
        "path": file.path,
        "action": file.action.value,
        "previous_version": file.previous_version,
        "new_version": file.new_version,
        "note": file.note,
        # A skill is a directory: `path` is the entry point, so without these the
        # agent reading this JSON cannot see which reference files it now has —
        # nor that an install deleted one.
        "extras": list(file.extras),
        "removed": list(file.removed),
    }


def _emit_setup(result: SetupResult) -> None:
    files = [_setup_file(file) for file in result.files]
    state = get_state()
    if use_json(state):
        rendering.emit_json(files, trim=state.trim)
    else:
        rendering.render_setup(files)
