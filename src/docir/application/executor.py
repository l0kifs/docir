"""The request/response boundary and the in-process executor.

Every CLI command is turned into a :class:`Request` (a command name plus a
JSON-serializable payload) and run through a :class:`RequestExecutor`. The
default :class:`InProcessExecutor` dispatches locally; the daemon's socket
client is an alternate executor that sends the same Request over a Unix socket.
Keeping the boundary this thin is what lets the CLI stay a stateless client
whether or not a daemon is running.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from docir.domain.errors import DocirError

if TYPE_CHECKING:
    from docir.application.dispatcher import Dispatcher


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


class InProcessExecutor(RequestExecutor):
    """Dispatches requests directly against the local use-case services."""

    def __init__(self, dispatcher: Dispatcher) -> None:
        self._dispatcher = dispatcher

    def execute(self, request: Request) -> Response:
        try:
            data = self._dispatcher.dispatch(request.command, request.payload)
            return Response(ok=True, data=data)
        except DocirError as exc:
            return Response(
                ok=False,
                error={
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "exit_code": exc.exit_code,
                },
            )
