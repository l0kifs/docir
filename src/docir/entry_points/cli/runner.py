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

from docir import __version__
from docir.config.settings import Settings
from docir.entry_points.cli import rendering
from docir.entry_points.composition import Container, build_in_process_executor, peer_status
from docir.entry_points.federation import (
    FEDERATED_COMMANDS,
    LOCAL_ONLY_KEY,
    STORES_KEY,
    peer_homes,
    resolve_extra,
)
from docir.modules.release.api import build_release_service
from docir.platform.errors import DocirError
from docir.platform.transport.messages import Request, RequestExecutor, Response


@dataclass
class CliState:
    """Resolved global CLI options for the current invocation."""

    settings: Settings
    json_output: bool = False
    pretty: bool = False
    trim: bool = True
    #: Extra peer stores for this invocation (``--store``), added to whatever
    #: ``stores.yaml`` declares. Reads only — every write goes to the one
    #: resolved home (adr-fb938175f72a).
    stores: tuple[str, ...] = ()


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

    Both halves go through :func:`run_local`, and both need to.

    Building the executor is not error-free: it loads the schema, so an invalid
    ``docs-schema.yaml`` raises before any request is dispatched. Left unwrapped,
    that surfaced as a raw Python traceback and exit 1 while ``docir schema
    validate`` — the same error, on the same file — printed a clean message and
    exit 3.

    Dispatching is not error-free either, and that half was left outside the
    handler when the first was fixed. A ``DocirError`` raised *client-side* by
    the transport — an unreachable daemon, one that will not start, a request
    that goes unanswered — escaped Typer the same way, so the default execution
    mode reported its failures as a stack trace and exit 1 rather than the
    message and the exit code the error carries. Errors the daemon *returns*
    were never affected: they arrive as a `Response` and go through
    :func:`_unwrap`, which is why this survived (issue-06f48d8f239f).
    """
    state = get_state()
    payload = _with_peers(state, command, payload)
    executor, closer = run_local(lambda: _build_executor(state.settings))
    try:
        response = run_local(lambda: executor.execute(Request(command=command, payload=payload)))
        if state.settings.schema_notice and command != "check":
            _warn_about_schema_drift(executor)
    finally:
        if closer is not None:
            closer.close()
    warn_about_a_newer_release(state.settings)
    return _unwrap(response)


def try_execute(command: str, payload: dict[str, object]) -> tuple[object, str]:
    """Run one command, returning ``(data, "")`` or ``(None, message)``.

    :func:`execute` turns a domain error into a process exit, which is correct
    for every command whose job needs the store to work. ``docir doctor``'s job
    is to *report* that it does not: a schema that will not parse or a daemon
    that will not start is the finding, and exiting there would leave the rest
    of the diagnosis — the environment half, which is still readable — unprinted
    at exactly the moment somebody needs it.

    Client-side errors and returned ones are folded together on purpose. Whether
    a broken schema raises while the container is built (in-process) or comes
    back as a failed `Response` (daemon) is a fact about the transport, and the
    caller is asking about the store.
    """
    state = get_state()
    try:
        executor, closer = _build_executor(state.settings)
    except DocirError as exc:
        return None, str(exc)
    try:
        response = executor.execute(Request(command=command, payload=payload))
    except DocirError as exc:
        return None, str(exc)
    finally:
        if closer is not None:
            closer.close()
    if response.ok:
        return response.data, ""
    # Only reached when a failed response carries no message; naming the store is
    # the difference between a sentence the caller can act on and one it cannot.
    fallback = f"the store at {state.settings.home} could not be opened, and reported no reason"
    return None, str((response.error or {}).get("message") or fallback)


def _with_peers(state: CliState, command: str, payload: dict[str, object]) -> dict[str, object]:
    """Attach this invocation's ad-hoc peers, and warn about unreachable ones.

    The warning is client-side for the reason the schema notice is: with the
    daemon, the process that discovers an unreadable peer is the daemon, and its
    stderr is a log nobody is reading. The daemon skips the same peers
    independently — both ask :func:`peer_status`, so they cannot disagree about
    what "unavailable" means.

    A peer is dropped from the read, never fatal to it: a peer is someone else's
    repository, and its index is derived and gitignored, so a colleague's fresh
    clone would otherwise be everyone's outage.
    """
    if command not in FEDERATED_COMMANDS or payload.get(LOCAL_ONLY_KEY):
        return payload
    # Resolved here, against *this* process's working directory: a `--store`
    # path is one a person typed at a shell, and with the daemon the process
    # that reads it is a different one that started somewhere else entirely.
    extra = resolve_extra(state.stores)
    homes = peer_homes(state.settings.home, extra)
    if not homes:
        return payload
    for home in homes:
        reason = peer_status(home)
        if reason:
            rendering.render_warning(f"skipping peer store {home}: {reason}")
    return {**payload, STORES_KEY: extra}


def warn_about_a_newer_release(settings: Settings) -> None:
    """Say on stderr that a newer docir exists (``DOCIR_UPDATE_CHECK=1``).

    Reads the cached answer and never the network: the fetch is the daemon's
    job, once a day, so the notice costs one file read and a command still works
    offline. Absent or unreadable means *unknown*, and unknown says nothing.
    """
    if not settings.update_check:
        return
    status = build_release_service(__version__, settings.release_cache_path).status()
    if status.update_available:
        rendering.render_warning(
            f"docir {status.latest} is available (this is {status.installed}) — "
            "run `docir self upgrade`"
        )


def _warn_about_schema_drift(executor: RequestExecutor) -> None:
    """Print schema drift to stderr after a command (``DOCIR_SCHEMA_NOTICE=1``).

    Client-side, and it has to be: with the daemon, the process that first loads
    a changed schema is the daemon, whose stderr is a log file nobody is reading.
    So this is one more request through the same executor rather than a print
    from wherever the schema happened to be parsed — the boundary every other
    command crosses, which is also why it works identically in both modes.

    Skipped for ``check``, which already reports the drift as a finding; two
    reports of one change in one command's output is how a warning becomes
    scenery.

    Failures are swallowed. This is a notice about something *else* being wrong;
    letting it turn a working command into a failing one would be the worst
    possible trade, and the drift is still reported by `check` either way.
    """
    try:
        response = executor.execute(Request(command="schema_drift", payload={}))
    except DocirError:
        return
    if not response.ok or not isinstance(response.data, dict):
        return
    lines = response.data.get("drift")
    if isinstance(lines, list) and lines:
        rendering.render_schema_drift([str(line) for line in lines])


def with_executor[T](action: Callable[[RequestExecutor], T]) -> T:
    """Run an action that issues several requests over one executor.

    :func:`execute` builds an executor and tears it down per call, which is
    right for a command that sends one request. A command that sends several —
    ``self upgrade`` reindexes and then checks — would otherwise build the whole
    in-process container once per step, parsing the schema and loading the
    embedding model each time.
    """
    state = get_state()
    executor, closer = run_local(lambda: _build_executor(state.settings))
    try:
        return run_local(lambda: action(executor))
    finally:
        if closer is not None:
            closer.close()


def execute_with(executor: RequestExecutor, command: str, payload: dict[str, object]) -> object:
    """Run one request on an existing executor, unwrapping errors as :func:`execute` does."""
    response = executor.execute(Request(command=command, payload=payload))
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
