"""The :class:`SocketExecutor` — a RequestExecutor backed by the daemon.

Forwards each request over the socket. If the socket turns out stale mid-call,
it respawns once and retries, so a transient daemon outage never hard-fails a
command.

:func:`start_daemon_executor` is how both entry points ask for one: it starts
the daemon and hands back ``None`` rather than raising when it will not start,
so the caller runs in process instead of failing.
"""

from __future__ import annotations

from docir.config.settings import NO_DAEMON_ENV, Settings
from docir.entry_points.daemon.lifecycle import ensure_running, stop
from docir.platform.errors import DaemonError, DaemonTimeoutError
from docir.platform.transport.client import DaemonClient
from docir.platform.transport.messages import Request, RequestExecutor, Response


class SocketExecutor(RequestExecutor):
    """Executes requests by delegating to the long-lived daemon."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = DaemonClient(settings.socket_path, request_timeout=settings.request_timeout)

    def execute(self, request: Request) -> Response:
        ensure_running(self._settings)
        try:
            return self._client.send(request)
        except DaemonTimeoutError:
            # The daemon has the request and may still be executing it. The
            # retry below would kill it mid-write and send the command again —
            # for `add` that is a second document, so surface the timeout.
            raise
        except DaemonError:
            # Stale socket or dead peer: nothing landed, so clean up and
            # respawn once.
            stop(self._settings)
            ensure_running(self._settings)
            return self._client.send(request)


def start_daemon_executor(settings: Settings) -> RequestExecutor | None:
    """A daemon-backed executor, or ``None`` when the daemon will not start.

    The daemon keeps the model warm and serializes writes; it decides nothing.
    Every command it answers, ``--no-daemon`` answers too — which is what makes
    a daemon that cannot be *started* a reason to run in process rather than a
    reason to fail, the way `nx`, `gradle` and `git fsmonitor` treat theirs
    (issue-c4c6349e06d4).

    Started **here**, rather than on first dispatch where :meth:`SocketExecutor.execute`
    used to do it, because the caller is the only one that can fall back: the
    in-process path owns a `Container` somebody has to close, and an executor
    swallowing its own failure mid-request would have nowhere to hand one back
    from. The `ensure_running` inside `execute` is then a no-op on the first
    request and still the respawn guard on later ones.

    Shared by both entry points rather than written twice. The CLI had the
    fallback and the MCP server built its own `SocketExecutor` beside it, which
    is the drift adr-354a4270ecd8 exists to stop — and the same drift that let
    two CLI flags reach no MCP tool in 0.18.0.

    It cost an adopter a whole review round to find: inside a read-only agent
    sandbox `spawn` cannot open the daemon log and `socket_path` cannot even ask
    for a temporary directory, and neither failure is a `DocirError`, so the
    read ended in a Python traceback while `--no-daemon` answered it. The
    reviewer reported that it could not read the design at all.

    `DaemonError` and `OSError`, and nothing wider. A `SchemaError` raised while
    a container loads is not a transport failure — in process it would be raised
    again, and catching it here would dress a broken schema up as a broken
    daemon.

    The verdict is not cached. One process runs one command, and state that
    outlived it would have to live in a file the sandbox this exists for cannot
    write.
    """
    from docir.entry_points.cli import rendering

    try:
        executor = SocketExecutor(settings)
        ensure_running(settings)
    except (DaemonError, OSError) as exc:
        rendering.render_warning(
            f"the daemon could not be started, so this command runs in process "
            f"and loads the embedding model cold; set {NO_DAEMON_ENV}=1 to skip "
            f"the daemon and this notice. Reason: {exc}"
        )
        return None
    return executor
