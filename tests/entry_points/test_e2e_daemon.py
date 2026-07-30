"""End-to-end tests for the daemon transport and lifecycle.

Covers the wire protocol, an in-thread server/client round-trip, and a real
detached daemon spawned as a subprocess and driven over the Unix socket.
"""

from __future__ import annotations

import contextlib
import socket
import threading
import time
from collections.abc import Iterator

import pytest

from docir.config.settings import DEFAULT_REQUEST_TIMEOUT, Settings
from docir.entry_points.composition import Container, InProcessExecutor
from docir.entry_points.daemon import lifecycle, socket_executor
from docir.entry_points.daemon.socket_executor import SocketExecutor
from docir.platform.errors import DaemonError, DaemonTimeoutError
from docir.platform.transport import client as client_module
from docir.platform.transport.client import DaemonClient
from docir.platform.transport.messages import Request, RequestExecutor, Response
from docir.platform.transport.protocol import recv_json, send_json
from docir.platform.transport.server import DaemonServer


class TestProtocol:
    def test_round_trip(self) -> None:
        left, right = socket.socketpair()
        try:
            send_json(left, {"hello": "world", "n": 1})
            assert recv_json(right) == {"hello": "world", "n": 1}
        finally:
            left.close()
            right.close()

    def test_recv_on_closed_returns_none(self) -> None:
        left, right = socket.socketpair()
        left.close()
        try:
            assert recv_json(right) is None
        finally:
            right.close()


class TestServerClientInThread:
    @pytest.fixture
    def running_server(self, container: Container, settings: Settings) -> Iterator[Settings]:
        server = DaemonServer(
            settings.socket_path,
            InProcessExecutor(container.dispatcher),
            idle_timeout=30.0,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        client = DaemonClient(settings.socket_path, request_timeout=30.0)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not client.is_available():
            time.sleep(0.02)
        try:
            yield settings
        finally:
            client.send(Request(command="shutdown"))
            thread.join(timeout=5)

    def test_ping(self, running_server: Settings) -> None:
        client = DaemonClient(running_server.socket_path, request_timeout=30.0)
        response = client.send(Request(command="ping"))
        assert response.ok
        assert response.data == {"pong": True}

    def test_command_and_error(self, running_server: Settings) -> None:
        client = DaemonClient(running_server.socket_path, request_timeout=30.0)
        ok = client.send(Request(command="tag_add", payload={"key": "auth", "description": "A"}))
        assert ok.ok
        missing = client.send(Request(command="get", payload={"doc_id": "adr-9999"}))
        assert not missing.ok
        assert missing.error is not None

    def test_concurrent_writes_are_serialized(self, running_server: Settings) -> None:
        # F4: the daemon serves one request at a time, so concurrent adds must
        # each get a distinct id (the "writes are serialized" guarantee).
        import concurrent.futures

        def add(i: int):
            client = DaemonClient(running_server.socket_path, request_timeout=30.0)
            return client.send(
                Request(
                    command="add",
                    payload={"type": "decision", "title": f"T{i}", "description": "d"},
                )
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            responses = list(pool.map(add, range(12)))

        assert all(r.ok for r in responses)
        ids = [r.data["id"] for r in responses]  # type: ignore[index]
        assert len(set(ids)) == 12  # no collisions, no interleaved allocation


class TestClientUnavailable:
    def test_is_available_false_when_no_socket(self, settings: Settings) -> None:
        assert DaemonClient(settings.socket_path, request_timeout=30.0).is_available() is False

    def test_send_to_missing_socket_raises(self, settings: Settings) -> None:
        with pytest.raises(DaemonError):
            DaemonClient(settings.socket_path, request_timeout=30.0).send(Request(command="ping"))


class _SlowExecutor(RequestExecutor):
    """Stands in for a request whose work takes real time (a large reindex)."""

    def __init__(self, delay: float) -> None:
        self._delay = delay
        self.calls = 0

    def execute(self, request: Request) -> Response:
        self.calls += 1
        time.sleep(self._delay)
        return Response(ok=True, data={"slept": True})


class TestReplyTimeoutIsSeparateFromConnect:
    """The connect budget used to bound the reply too.

    Found by running `docir reindex` over docir's own 65-document store: the
    command took ~10s, the client gave up at 5s with "daemon socket error:
    timed out", and the daemon completed the rebuild regardless.
    """

    @contextlib.contextmanager
    def _serving(self, settings: Settings, executor: RequestExecutor) -> Iterator[None]:
        settings.ensure_directories()
        server = DaemonServer(settings.socket_path, executor, idle_timeout=30.0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        probe = DaemonClient(settings.socket_path, request_timeout=30.0)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not probe.is_available():
            time.sleep(0.02)
        try:
            yield
        finally:
            with contextlib.suppress(DaemonError):
                probe.send(Request(command="shutdown"))
            thread.join(timeout=5)

    def test_work_outlasting_the_connect_timeout_still_returns(
        self, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Shrink the connect budget rather than sleeping past the real 5s: with
        # one shared timeout this send raises after 0.2s instead of answering.
        monkeypatch.setattr(client_module, "_CONNECT_TIMEOUT", 0.2)
        executor = _SlowExecutor(0.6)
        with self._serving(settings, executor):
            response = DaemonClient(settings.socket_path, request_timeout=30.0).send(
                Request(command="ping")
            )
        assert response.ok
        assert executor.calls == 1

    def test_unanswered_request_raises_daemon_timeout(self, settings: Settings) -> None:
        # A peer that accepts and never answers is the "daemon still working"
        # case: the request landed, so the error must not be a plain DaemonError
        # that the executor would happily resend.
        settings.ensure_directories()
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(settings.socket_path))
        listener.listen(1)
        held: list[socket.socket] = []
        thread = threading.Thread(target=lambda: held.append(listener.accept()[0]), daemon=True)
        thread.start()
        try:
            with pytest.raises(DaemonTimeoutError) as raised:
                DaemonClient(settings.socket_path, request_timeout=0.15).send(
                    Request(command="reindex")
                )
            assert "reindex" in str(raised.value)
            assert "--no-daemon" in str(raised.value)
        finally:
            thread.join(timeout=5)
            for conn in held:
                conn.close()
            listener.close()
            settings.socket_path.unlink(missing_ok=True)


class _ScriptedClient:
    """A DaemonClient stand-in that raises a scripted sequence of errors."""

    def __init__(self, *outcomes: BaseException | Response) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    def send(self, request: Request) -> Response:
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class TestSocketExecutorRetryPolicy:
    @pytest.fixture
    def no_lifecycle(self, monkeypatch: pytest.MonkeyPatch) -> list[Settings]:
        stopped: list[Settings] = []
        monkeypatch.setattr(socket_executor, "ensure_running", lambda settings: None)
        monkeypatch.setattr(socket_executor, "stop", lambda settings: stopped.append(settings))
        return stopped

    def test_timeout_is_not_retried(
        self,
        settings: Settings,
        monkeypatch: pytest.MonkeyPatch,
        no_lifecycle: list[Settings],
    ) -> None:
        # Resending a timed-out write runs it twice — for `add` that is a second
        # document — and `stop` would kill the daemon mid-transaction.
        executor = SocketExecutor(settings)
        client = _ScriptedClient(DaemonTimeoutError("no answer"))
        monkeypatch.setattr(executor, "_client", client)
        with pytest.raises(DaemonTimeoutError):
            executor.execute(Request(command="add"))
        assert client.calls == 1
        assert no_lifecycle == []

    def test_dead_socket_is_retried_once(
        self,
        settings: Settings,
        monkeypatch: pytest.MonkeyPatch,
        no_lifecycle: list[Settings],
    ) -> None:
        executor = SocketExecutor(settings)
        client = _ScriptedClient(DaemonError("stale socket"), Response(ok=True, data={}))
        monkeypatch.setattr(executor, "_client", client)
        assert executor.execute(Request(command="ping")).ok
        assert client.calls == 2
        assert no_lifecycle == [settings]

    def test_configured_timeout_reaches_the_client(self, settings: Settings) -> None:
        assert settings.request_timeout == DEFAULT_REQUEST_TIMEOUT
        executor = SocketExecutor(settings)
        assert executor._client._request_timeout == DEFAULT_REQUEST_TIMEOUT


class TestLifecycleHelpers:
    def test_pid_read_write_clear(self, settings: Settings) -> None:
        settings.ensure_directories()
        assert lifecycle.read_pid(settings) is None
        lifecycle.write_pid(settings)
        assert lifecycle.read_pid(settings) is not None
        lifecycle.clear_pid(settings)
        assert lifecycle.read_pid(settings) is None

    def test_process_alive(self) -> None:
        import os

        assert lifecycle.process_alive(os.getpid()) is True
        assert lifecycle.process_alive(999999) is False

    def test_status_not_running(self, settings: Settings) -> None:
        assert lifecycle.status(settings).running is False

    def test_stop_when_not_running(self, settings: Settings) -> None:
        assert lifecycle.stop(settings) is False


@pytest.mark.slow
class TestDaemonCli:
    def test_start_status_stop(self, settings: Settings) -> None:
        from typer.testing import CliRunner

        from docir.entry_points.cli.app import app

        runner = CliRunner()
        try:
            started = runner.invoke(app, ["daemon", "start"])
            assert started.exit_code == 0
            assert "running" in started.stdout.lower()
            status = runner.invoke(app, ["daemon", "status"])
            assert "running" in status.stdout.lower()
        finally:
            stopped = runner.invoke(app, ["daemon", "stop"])
            assert stopped.exit_code == 0
            assert "stopped" in stopped.stdout.lower()


@pytest.mark.slow
class TestRealDaemon:
    def test_spawn_serve_stop(self, settings: Settings) -> None:
        daemon_settings = Settings.resolve(settings.home, use_daemon=True)
        try:
            lifecycle.ensure_running(daemon_settings)
            assert lifecycle.is_running(daemon_settings)
            assert lifecycle.status(daemon_settings).running is True

            executor = SocketExecutor(daemon_settings)
            assert executor.execute(Request(command="ping")).ok
            added = executor.execute(
                Request(command="tag_add", payload={"key": "auth", "description": "A"})
            )
            assert added.ok
        finally:
            was_running = lifecycle.stop(daemon_settings)
            assert was_running
        assert not lifecycle.is_running(daemon_settings)
