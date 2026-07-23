"""End-to-end tests for the daemon transport and lifecycle.

Covers the wire protocol, an in-thread server/client round-trip, and a real
detached daemon spawned as a subprocess and driven over the Unix socket.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator

import pytest

from docir.config.settings import Settings
from docir.entry_points.composition import Container, InProcessExecutor
from docir.entry_points.daemon import lifecycle
from docir.entry_points.daemon.socket_executor import SocketExecutor
from docir.platform.transport.client import DaemonClient
from docir.platform.transport.messages import Request
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
        client = DaemonClient(settings.socket_path)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not client.is_available():
            time.sleep(0.02)
        try:
            yield settings
        finally:
            client.send(Request(command="shutdown"))
            thread.join(timeout=5)

    def test_ping(self, running_server: Settings) -> None:
        client = DaemonClient(running_server.socket_path)
        response = client.send(Request(command="ping"))
        assert response.ok
        assert response.data == {"pong": True}

    def test_command_and_error(self, running_server: Settings) -> None:
        client = DaemonClient(running_server.socket_path)
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
            client = DaemonClient(running_server.socket_path)
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
        assert DaemonClient(settings.socket_path).is_available() is False

    def test_send_to_missing_socket_raises(self, settings: Settings) -> None:
        from docir.platform.errors import DaemonError

        with pytest.raises(DaemonError):
            DaemonClient(settings.socket_path).send(Request(command="ping"))


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
