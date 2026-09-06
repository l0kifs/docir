"""Length-prefixed JSON framing for the daemon socket.

Each message is a 4-byte big-endian length header followed by the UTF-8 JSON
body. Length prefixing (rather than newline delimiting) is robust to arbitrary
markdown bodies flowing through the payload.

A reply is one or more frames: zero or more *keepalives* while the daemon is
still working, then exactly one response. The keepalive carries no information
beyond "I am still here", and exists so the client's reply timeout can bound
*silence* rather than the length of the work — a full ``reindex`` legitimately
runs for many minutes, and no fixed budget can tell that apart from a wedged
daemon. Both ends of a connection always run the same build (the pid file's
code stamp guarantees it), so this is not a versioned wire concern.
"""

from __future__ import annotations

import json
import socket
import struct

_HEADER = struct.Struct(">I")

#: The only key a keepalive frame carries. Chosen so it cannot collide with a
#: response frame, which is always ``ok``/``data``/``error``.
_KEEPALIVE_KEY = "keepalive"


def keepalive_frame() -> dict[str, object]:
    """The frame the daemon sends while a request is still running."""
    return {_KEEPALIVE_KEY: True}


def is_keepalive(message: dict[str, object]) -> bool:
    """Whether a received frame is a keepalive rather than the response."""
    return message.get(_KEEPALIVE_KEY) is True


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
