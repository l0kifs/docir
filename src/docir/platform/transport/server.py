"""The Unix-socket daemon server loop.

Owns the socket and serves one request at a time (write operations are thereby
serialized, resolving most write-conflict races). Shuts itself down on an
explicit ``shutdown`` request or after ``idle_timeout`` seconds with no
connection, so it never lingers as a forgotten background process.

The request runs on a worker thread so the connection stays answerable while it
does: the handler sends a keepalive every :data:`_KEEPALIVE_INTERVAL` seconds
until the work finishes. Requests already run off the main thread — the file
watcher is a second caller through the same ``SerializingExecutor`` — so this
adds a thread, not a concurrency model.
"""

from __future__ import annotations

import socket
import threading
from pathlib import Path

from docir.platform.transport.messages import Request, RequestExecutor, Response
from docir.platform.transport.protocol import keepalive_frame, recv_json, send_json

_BACKLOG = 16

#: How often the daemon says "still working" while a request runs. Its only
#: constraint is being comfortably below any client's reply timeout (the default
#: is 300s), because that timeout now measures the gap between frames.
_KEEPALIVE_INTERVAL = 5.0


class DaemonServer:
    """A blocking, single-connection-at-a-time Unix-socket server."""

    def __init__(
        self,
        socket_path: Path,
        executor: RequestExecutor,
        *,
        idle_timeout: float,
        keepalive_interval: float = _KEEPALIVE_INTERVAL,
    ) -> None:
        self._socket_path = socket_path
        self._executor = executor
        self._idle_timeout = idle_timeout
        self._keepalive_interval = keepalive_interval
        self._running = False

    def serve_forever(self) -> None:
        """Bind the socket and serve until shutdown or idle timeout."""
        server = self._bind()
        self._running = True
        try:
            while self._running:
                try:
                    conn, _ = server.accept()
                except TimeoutError:
                    break  # idle timeout reached — shut down
                with conn:
                    self._handle(conn)
        finally:
            server.close()
            self._socket_path.unlink(missing_ok=True)

    def _bind(self) -> socket.socket:
        self._socket_path.unlink(missing_ok=True)
        self._socket_path.parent.mkdir(parents=True, exist_ok=True)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(self._socket_path))
        server.listen(_BACKLOG)
        server.settimeout(self._idle_timeout)
        return server

    def _handle(self, conn: socket.socket) -> None:
        message = recv_json(conn)
        if message is None:
            return
        request = Request.from_dict(message)
        if request.command == "shutdown":
            send_json(conn, Response(ok=True, data={"stopped": True}).to_dict())
            self._running = False
            return
        response = self._execute_while_answering(conn, request)
        send_json(conn, response.to_dict())

    def _execute_while_answering(self, conn: socket.socket, request: Request) -> Response:
        """Run the request on a worker thread, keeping the connection alive.

        The worker's exception is re-raised here rather than turned into an
        error response, so a crash still closes the connection without a reply —
        which is what tells ``SocketExecutor`` the daemon is broken and the
        request is safe to respawn and retry. Swallowing it into an ``ok=False``
        would make an unhandled crash indistinguishable from a domain error.
        """
        outcome: list[Response] = []
        failure: list[BaseException] = []

        def run() -> None:
            try:
                outcome.append(self._executor.execute(request))
            except BaseException as exc:  # re-raised on the handler thread below
                failure.append(exc)

        worker = threading.Thread(target=run, name="docir-request", daemon=True)
        worker.start()
        answering = True
        while True:
            worker.join(self._keepalive_interval)
            if not worker.is_alive():
                break
            if answering:
                answering = self._keepalive(conn)
        if failure:
            raise failure[0]
        return outcome[0]

    @staticmethod
    def _keepalive(conn: socket.socket) -> bool:
        """Send one keepalive; ``False`` once the client has stopped listening.

        A client that gave up mid-request is not a reason to abandon the work —
        it is one transaction, and killing it halfway is how an index ends up
        describing neither the old corpus nor the new one. So the failure only
        stops the keepalives; the final response still tries to send, and fails
        the way it did before keepalives existed.
        """
        try:
            send_json(conn, keepalive_frame())
        except OSError:
            return False
        return True
