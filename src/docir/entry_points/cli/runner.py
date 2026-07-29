"""Per-command execution: build an executor, run one request, handle errors.

Holds the CLI's resolved global options (home dir, daemon vs in-process, JSON
output) and turns each command into a single request/response round-trip,
mapping a domain error's exit code onto the process exit code.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import typer

from docir.config.settings import Settings
from docir.entry_points.cli import rendering
from docir.entry_points.composition import Container, build_in_process_executor
from docir.platform.errors import DocirError
from docir.platform.transport.messages import Request, RequestExecutor, Response


@dataclass
class CliState:
    """Resolved global CLI options for the current invocation."""

    settings: Settings
    json_output: bool = False
    pretty: bool = False
    trim: bool = True


_state: CliState | None = None


def use_json(state: CliState) -> bool:
    """Whether to emit compact JSON instead of Rich tables/panels.

    Agents capture stdout (a pipe, not a TTY) and so get JSON automatically;
    a human at a terminal gets tables. ``--json`` forces JSON everywhere,
    ``--pretty`` forces tables everywhere.
    """
    if state.pretty:
        return False
    if state.json_output:
        return True
    isatty = getattr(sys.stdout, "isatty", None)
    return not (callable(isatty) and isatty())


def help_wants_json(argv: Sequence[str] | None = None) -> bool:
    """Whether ``--help`` should render as JSON, decided without :class:`CliState`.

    ``--help`` is an *eager* Click parameter: it renders and exits during
    argument parsing, before the app callback runs, so the parsed state does not
    exist yet. The flags are therefore read straight from ``argv`` — same
    precedence as :func:`use_json` (``--pretty`` wins, then ``--json``, then the
    TTY check), so help obeys the contract every other command obeys.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if "--pretty" in args:
        return False
    if "--json" in args:
        return True
    isatty = getattr(sys.stdout, "isatty", None)
    return not (callable(isatty) and isatty())


def set_state(state: CliState) -> None:
    global _state
    _state = state


def get_state() -> CliState:
    assert _state is not None, "CLI state was not initialized"
    return _state


def execute(command: str, payload: dict[str, object]) -> object:
    """Run one command and return its result data, or exit on a domain error.

    Building the executor goes through :func:`run_local` because it is not
    error-free: it loads the schema, so an invalid ``docs-schema.yaml`` raises
    before any request is dispatched. Left unwrapped, that surfaced as a raw
    Python traceback and exit 1 while ``docir schema validate`` — the same error,
    on the same file — printed a clean message and exit 3.
    """
    state = get_state()
    executor, closer = run_local(lambda: _build_executor(state.settings))
    try:
        response = executor.execute(Request(command=command, payload=payload))
    finally:
        if closer is not None:
            closer.close()
    return _unwrap(response)


def run_local[T](action: Callable[[], T]) -> T:
    """Run an in-process action, mapping a domain error onto the exit code.

    For commands that do not go through the daemon/dispatcher (e.g. ``agent``),
    so they still report a domain error the same way :func:`execute` does.
    """
    try:
        return action()
    except DocirError as exc:
        rendering.render_error({"message": str(exc)})
        raise typer.Exit(code=exc.exit_code) from exc


def _build_executor(
    settings: Settings,
) -> tuple[RequestExecutor, Container | None]:
    if settings.use_daemon:
        from docir.entry_points.daemon.socket_executor import SocketExecutor

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
