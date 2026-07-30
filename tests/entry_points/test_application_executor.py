"""Tests for the request/response boundary and the in-process executor."""

from __future__ import annotations

import pytest
import typer

from docir.config.settings import Settings
from docir.entry_points.cli import runner
from docir.entry_points.cli.runner import CliState
from docir.entry_points.composition import InProcessExecutor
from docir.entry_points.dispatch import Dispatcher
from docir.platform.errors import DaemonError, DaemonTimeoutError, DocirError
from docir.platform.transport.messages import Request, Response


class TestRequestResponse:
    def test_request_round_trip(self) -> None:
        request = Request(command="get", payload={"doc_id": "adr-0001"})
        restored = Request.from_dict(request.to_dict())
        assert restored == request

    def test_request_from_dict_without_payload(self) -> None:
        assert Request.from_dict({"command": "ping"}).payload == {}

    def test_request_from_dict_bad_payload(self) -> None:
        assert Request.from_dict({"command": "ping", "payload": 5}).payload == {}

    def test_response_round_trip(self) -> None:
        response = Response(ok=True, data={"x": 1})
        assert Response.from_dict(response.to_dict()).data == {"x": 1}

    def test_raise_for_error_success(self) -> None:
        assert Response(ok=True, data=42).raise_for_error() == 42

    def test_raise_for_error_failure(self) -> None:
        response = Response(ok=False, error={"message": "boom"})
        with pytest.raises(DocirError, match="boom"):
            response.raise_for_error()

    def test_response_from_dict_bad_error(self) -> None:
        assert Response.from_dict({"ok": False, "error": "nope"}).error is None


class TestInProcessExecutor:
    def test_success(self, dispatcher: Dispatcher) -> None:
        executor = InProcessExecutor(dispatcher)
        response = executor.execute(Request(command="ping"))
        assert response.ok
        assert response.data == {"pong": True}

    def test_domain_error_is_captured(self, dispatcher: Dispatcher) -> None:
        executor = InProcessExecutor(dispatcher)
        response = executor.execute(Request(command="get", payload={"doc_id": "x-0001"}))
        assert not response.ok
        assert response.error is not None
        assert response.error["type"] == "DocumentNotFoundError"
        assert response.error["exit_code"] == 4


class TestTransportErrorsReachTheUser:
    """GAP-052: a `DocirError` raised client-side by the transport escaped Typer.

    `runner.execute` wrapped only the *construction* of the executor in the
    handler that maps a domain error onto its exit code, so an unreachable
    daemon, one that would not start, or an unanswered request printed a Python
    traceback and exited 1 instead of the message and code the error carries.
    """

    class _Failing:
        def __init__(self, exc: BaseException) -> None:
            self._exc = exc

        def execute(self, request: Request) -> Response:
            raise self._exc

    def _run(self, settings: Settings, monkeypatch: pytest.MonkeyPatch, exc: BaseException):
        monkeypatch.setattr(runner, "_build_executor", lambda _settings: (self._Failing(exc), None))
        runner.set_state(CliState(settings=settings))
        with pytest.raises(typer.Exit) as raised:
            runner.execute("add", {"type": "decision"})
        return raised.value

    def test_a_daemon_error_exits_with_its_own_code(
        self,
        settings: Settings,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        exit_ = self._run(settings, monkeypatch, DaemonError("socket is gone"))
        assert exit_.exit_code == DaemonError.exit_code == 7
        assert "socket is gone" in capsys.readouterr().err

    def test_a_reply_timeout_reaches_the_user_as_a_message(
        self,
        settings: Settings,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # The message names the escape hatches; it is worthless in a traceback.
        exit_ = self._run(settings, monkeypatch, DaemonTimeoutError("no answer; try --no-daemon"))
        assert exit_.exit_code == 7
        assert "--no-daemon" in capsys.readouterr().err

    def test_an_error_the_daemon_returns_still_uses_its_payload_code(
        self, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The path that always worked, pinned so the fix cannot regress it: a
        # served error comes back as a Response and is unwrapped, not raised.
        class _Returning:
            def execute(self, request: Request) -> Response:
                return Response(ok=False, error={"message": "nope", "exit_code": 4})

        monkeypatch.setattr(runner, "_build_executor", lambda _settings: (_Returning(), None))
        runner.set_state(CliState(settings=settings))
        with pytest.raises(typer.Exit) as raised:
            runner.execute("get", {"doc_id": "adr-9999"})
        assert raised.value.exit_code == 4


def test_dispatch_unknown_command(dispatcher: Dispatcher) -> None:
    with pytest.raises(DocirError, match="unknown command"):
        dispatcher.dispatch("bogus", {})
