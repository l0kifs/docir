"""Tests for the request/response boundary and the in-process executor."""

from __future__ import annotations

import pytest

from docir.application.dispatcher import Dispatcher
from docir.application.executor import InProcessExecutor, Request, Response
from docir.domain.errors import DocirError


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


def test_dispatch_unknown_command(dispatcher: Dispatcher) -> None:
    with pytest.raises(DocirError, match="unknown command"):
        dispatcher.dispatch("bogus", {})
