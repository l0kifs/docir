"""The request/response boundary crossing the execution transport.

Every command is turned into a :class:`Request` (a command name plus a
JSON-serializable payload) and run through a :class:`RequestExecutor`. The
in-process executor (wired at the composition root) dispatches locally; the
daemon's socket client is an alternate executor that sends the same Request
over a Unix socket. Keeping the boundary this thin is what lets the CLI stay a
stateless client whether or not a daemon is running.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from docir.platform.errors import DocirError


@dataclass(frozen=True, slots=True)
class Request:
    """A command invocation crossing the execution boundary."""

    command: str
    payload: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {"command": self.command, "payload": self.payload}

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Request:
        raw = data.get("payload")
        payload: dict[str, object] = (
            {str(key): value for key, value in raw.items()} if isinstance(raw, dict) else {}
        )
        return cls(command=str(data["command"]), payload=payload)


@dataclass(frozen=True, slots=True)
class Response:
    """The result of executing a :class:`Request`."""

    ok: bool
    data: object = None
    error: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        return {"ok": self.ok, "data": self.data, "error": self.error}

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Response:
        error = data.get("error")
        error_dict: dict[str, object] | None = None
        if isinstance(error, dict):
            error_dict = {str(key): value for key, value in error.items()}
        return cls(ok=bool(data.get("ok")), data=data.get("data"), error=error_dict)

    def raise_for_error(self) -> object:
        """Return ``data`` on success, or re-raise the carried domain error."""
        if self.ok:
            return self.data
        error = self.error or {}
        raise DocirError(str(error.get("message", "unknown error")))


class RequestExecutor(ABC):
    """Executes a :class:`Request` and returns a :class:`Response`."""

    @abstractmethod
    def execute(self, request: Request) -> Response:
        """Run the command and return its response."""


class SerializingExecutor(RequestExecutor):
    """Runs one request at a time, whichever thread asks.

    The daemon's socket loop already serializes *clients* — it handles one
    connection at a time. The file watcher is a second caller on another
    thread, and SQLite has exactly one writer, so a background reindex racing a
    client ``add`` is a locked database rather than a queue.

    Wrapping once and handing the same instance to both is what makes the lock
    shared. Two wrappers would each be internally consistent and collectively
    useless, which is the failure this class exists to make hard to write.
    """

    def __init__(self, inner: RequestExecutor) -> None:
        self._inner = inner
        self._lock = threading.Lock()

    def execute(self, request: Request) -> Response:
        with self._lock:
            return self._inner.execute(request)
