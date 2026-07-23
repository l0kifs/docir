"""The Unix-socket daemon server loop.

Owns the socket and serves one request at a time (write operations are thereby
serialized, resolving most write-conflict races). Shuts itself down on an
explicit ``shutdown`` request or after ``idle_timeout`` seconds with no
connection, so it never lingers as a forgotten background process.
"""

from __future__ import annotations

import socket
from pathlib import Path

from docir.platform.transport.messages import Request, RequestExecutor, Response
from docir.platform.transport.protocol import recv_json, send_json

_BACKLOG = 16


class DaemonServer:
    """A blocking, single-connection-at-a-time Unix-socket server."""

    def __init__(
        self,
        socket_path: Path,
        executor: RequestExecutor,
        *,
        idle_timeout: float,
    ) -> None:
        self._socket_path = socket_path
        self._executor = executor
        self._idle_timeout = idle_timeout
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
        response = self._executor.execute(request)
        send_json(conn, response.to_dict())
