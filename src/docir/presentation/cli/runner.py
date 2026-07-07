"""Per-command execution: build an executor, run one request, handle errors.

Holds the CLI's resolved global options (home dir, daemon vs in-process, JSON
output) and turns each command into a single request/response round-trip,
mapping a domain error's exit code onto the process exit code.
"""

from __future__ import annotations

from dataclasses import dataclass

import typer

from docir.application.executor import Request, RequestExecutor, Response
from docir.infrastructure.config.settings import Settings
from docir.presentation.cli import rendering
from docir.presentation.composition import Container, build_in_process_executor


@dataclass
class CliState:
    """Resolved global CLI options for the current invocation."""

    settings: Settings
    json_output: bool = False


_state: CliState | None = None


def set_state(state: CliState) -> None:
    global _state
    _state = state


def get_state() -> CliState:
    assert _state is not None, "CLI state was not initialized"
    return _state


def execute(command: str, payload: dict[str, object]) -> object:
    """Run one command and return its result data, or exit on a domain error."""
    state = get_state()
    executor, closer = _build_executor(state.settings)
    try:
        response = executor.execute(Request(command=command, payload=payload))
    finally:
        if closer is not None:
            closer.close()
    return _unwrap(response)


def _build_executor(
    settings: Settings,
) -> tuple[RequestExecutor, Container | None]:
    if settings.use_daemon:
        from docir.infrastructure.daemon.executor import SocketExecutor

        return SocketExecutor(settings), None
    executor, container = build_in_process_executor(settings)
    return executor, container


def _unwrap(response: Response) -> object:
    if response.ok:
        return response.data
    error = response.error or {}
    rendering.render_error(error)
    code = error.get("exit_code", 1)
    raise typer.Exit(code=code if isinstance(code, int) else 1)
