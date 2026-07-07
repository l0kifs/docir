"""A thin Unix-socket client for talking to the daemon."""

from __future__ import annotations

import socket
from pathlib import Path

from docir.application.executor import Request, Response
from docir.domain.errors import DaemonError
from docir.infrastructure.daemon.protocol import recv_json, send_json

_CONNECT_TIMEOUT = 5.0


class DaemonClient:
    """Connects to the daemon socket and performs one request per call."""

    def __init__(self, socket_path: Path) -> None:
        self._socket_path = socket_path

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
        """Send a request and return the daemon's response."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(_CONNECT_TIMEOUT)
        try:
            sock.connect(str(self._socket_path))
            send_json(sock, request.to_dict())
            reply = recv_json(sock)
        except OSError as exc:
            raise DaemonError(f"daemon socket error: {exc}") from exc
        finally:
            sock.close()
        if reply is None:
            raise DaemonError("daemon closed the connection without responding")
        return Response.from_dict(reply)
