"""The :class:`SocketExecutor` — a RequestExecutor backed by the daemon.

Ensures the daemon is running (spawning it on first use), then forwards each
request over the socket. If the socket turns out stale mid-call, it respawns
once and retries, so a transient daemon outage never hard-fails a command.
"""

from __future__ import annotations

from docir.config.settings import Settings
from docir.entry_points.daemon.lifecycle import ensure_running, stop
from docir.platform.errors import DaemonError
from docir.platform.transport.client import DaemonClient
from docir.platform.transport.messages import Request, RequestExecutor, Response


class SocketExecutor(RequestExecutor):
    """Executes requests by delegating to the long-lived daemon."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = DaemonClient(settings.socket_path)

    def execute(self, request: Request) -> Response:
        ensure_running(self._settings)
        try:
            return self._client.send(request)
        except DaemonError:
            # Stale socket or dead peer: clean up and respawn once.
            stop(self._settings)
            ensure_running(self._settings)
            return self._client.send(request)
