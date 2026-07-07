"""Length-prefixed JSON framing for the daemon socket.

Each message is a 4-byte big-endian length header followed by the UTF-8 JSON
body. Length prefixing (rather than newline delimiting) is robust to arbitrary
markdown bodies flowing through the payload.
"""

from __future__ import annotations

import json
import socket
import struct

_HEADER = struct.Struct(">I")


def send_json(sock: socket.socket, obj: dict[str, object]) -> None:
    """Send one framed JSON message."""
    body = json.dumps(obj).encode("utf-8")
    sock.sendall(_HEADER.pack(len(body)) + body)


def recv_json(sock: socket.socket) -> dict[str, object] | None:
    """Receive one framed JSON message, or ``None`` if the peer closed."""
    header = _recv_exact(sock, _HEADER.size)
    if header is None:
        return None
    (length,) = _HEADER.unpack(header)
    body = _recv_exact(sock, length)
    if body is None:
        return None
    decoded = json.loads(body.decode("utf-8"))
    return decoded if isinstance(decoded, dict) else None


def _recv_exact(sock: socket.socket, count: int) -> bytes | None:
    chunks: list[bytes] = []
    remaining = count
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            return None
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)
