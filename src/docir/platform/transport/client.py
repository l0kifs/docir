"""A thin Unix-socket client for talking to the daemon.

Two timeouts, on purpose. ``_CONNECT_TIMEOUT`` bounds reaching the socket — a
local ``AF_UNIX`` connect either succeeds immediately or the daemon is not there,
so a few seconds is already generous. The *reply* is bounded separately by
``request_timeout``, because it arrives only once the daemon has finished the
work, and one request can legitimately be a whole ``reindex``. Reusing the
connect budget for the reply made every command slower than five seconds fail
while the daemon completed it perfectly well.

``request_timeout`` bounds the gap *between frames*, not the work. The daemon
sends a keepalive every few seconds while a request runs, and each frame re-arms
the socket timeout, so the budget expires only on silence. This is what a fixed
budget could never express: the most expensive request docir makes is the
``reindex`` that ``docir self upgrade`` runs, whose cost is the size of the
corpus, and it was bounded by a number chosen for an ordinary command — past
roughly 1,500 documents the upgrade could not finish at all (adr-56d29d521620).
"""

from __future__ import annotations

import socket
from pathlib import Path

from docir.platform.errors import DaemonError, DaemonTimeoutError
from docir.platform.transport.messages import Request, Response
from docir.platform.transport.protocol import is_keepalive, recv_json, send_json

_CONNECT_TIMEOUT = 5.0


class DaemonClient:
    """Connects to the daemon socket and performs one request per call.

    ``request_timeout`` is required rather than defaulted: the default belongs to
    :data:`docir.config.settings.DEFAULT_REQUEST_TIMEOUT`, and this module stays
    a dependency leaf that knows nothing about settings.
    """

    def __init__(self, socket_path: Path, *, request_timeout: float) -> None:
        self._socket_path = socket_path
        self._request_timeout = request_timeout

    def is_available(self) -> bool:
        """Whether the daemon socket accepts a connection right now."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(_CONNECT_TIMEOUT)
        try:
            sock.connect(str(self._socket_path))
            return True
        except OSError:
            return False
        finally:
            sock.close()

    def send(self, request: Request) -> Response:
        """Send a request and return the daemon's response.

        Raises :class:`DaemonError` when the request never landed (no socket,
        refused, peer gone) — safe for the caller to respawn and retry — and
        :class:`DaemonTimeoutError` when it landed and the daemon then went
        silent, which is not safe to retry.
        """
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.settimeout(_CONNECT_TIMEOUT)
            try:
                sock.connect(str(self._socket_path))
            except OSError as exc:
                raise DaemonError(f"daemon socket error: {exc}") from exc
            # Past this point the daemon owns the request, so its own clock
            # applies rather than the connect budget.
            sock.settimeout(self._request_timeout)
            try:
                send_json(sock, request.to_dict())
                reply = self._await_response(sock)
            except TimeoutError as exc:
                raise DaemonTimeoutError(
                    f"the daemon went silent on '{request.command}': no frame for "
                    f"{self._request_timeout:g}s. A running command sends a keepalive every "
                    "few seconds, so this is a wedged or killed daemon rather than a slow "
                    "one — a long `reindex` on a large corpus does not land here. Check "
                    "`docir daemon status` and re-read the store before retrying, or pass "
                    "--no-daemon to run the command in-process."
                ) from exc
            except OSError as exc:
                raise DaemonError(f"daemon socket error: {exc}") from exc
        finally:
            sock.close()
        if reply is None:
            raise DaemonError("daemon closed the connection without responding")
        return Response.from_dict(reply)

    @staticmethod
    def _await_response(sock: socket.socket) -> dict[str, object] | None:
        """Read frames until the response arrives, discarding keepalives.

        Each ``recv_json`` re-arms the socket's timeout, so the budget applies
        per frame. That is the whole mechanism: the deadline is never computed,
        it is simply never reached while the daemon keeps talking.
        """
        while True:
            reply = recv_json(sock)
            if reply is None or not is_keepalive(reply):
                return reply
