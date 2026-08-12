"""End-to-end tests for the daemon transport and lifecycle.

Covers the wire protocol, an in-thread server/client round-trip, and a real
detached daemon spawned as a subprocess and driven over the Unix socket.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import threading
import time
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import pytest

from docir import __version__
from docir.config.settings import DEFAULT_REQUEST_TIMEOUT, Settings
from docir.entry_points.composition import Container, InProcessExecutor, build_container
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

    def test_pid_file_carries_the_build_being_served(self, settings: Settings) -> None:
        settings.ensure_directories()
        lifecycle.write_pid(settings)
        record = lifecycle.read_pid_record(settings)
        assert record is not None
        assert record.pid == os.getpid()
        assert record.stamp == lifecycle.current_stamp()

    def test_bare_integer_pid_file_still_reads(self, settings: Settings) -> None:
        # Written by a docir that predates the stamp: the pid is usable, the
        # build is unknown.
        settings.ensure_directories()
        settings.pid_path.write_text("4242", encoding="utf-8")
        assert lifecycle.read_pid_record(settings) == lifecycle.PidRecord(pid=4242, stamp=None)

    @pytest.mark.parametrize("content", ["", "  ", '{"pid": "nope"}', "[1, 2]", "{}"])
    def test_unusable_pid_file_reads_as_absent(self, settings: Settings, content: str) -> None:
        settings.ensure_directories()
        settings.pid_path.write_text(content, encoding="utf-8")
        assert lifecycle.read_pid_record(settings) is None
        assert lifecycle.read_pid(settings) is None

    def test_process_alive(self) -> None:
        assert lifecycle.process_alive(os.getpid()) is True
        assert lifecycle.process_alive(999999) is False

    def test_status_not_running(self, settings: Settings) -> None:
        assert lifecycle.status(settings).running is False

    def test_stop_when_not_running(self, settings: Settings) -> None:
        assert lifecycle.stop(settings) is False


class TestCodeStamp:
    def test_the_stamp_moves_when_a_source_file_changes(self, tmp_path: Path) -> None:
        # The version half cannot see this: nothing bumps `__version__`
        # between commits, so an edit to `src/` during development is visible
        # only through the mtime.
        root = tmp_path / "pkg"
        (root / "sub").mkdir(parents=True)
        (root / "sub" / "a.py").write_text("x = 1", encoding="utf-8")
        before = lifecycle._newest_source_mtime(root)
        assert before > 0

        edited = root / "sub" / "a.py"
        edited.write_text("x = 2", encoding="utf-8")
        os.utime(edited, ns=(before + 10**9, before + 10**9))
        assert lifecycle._newest_source_mtime(root) > before

    def test_a_tree_with_no_sources_stamps_zero(self, tmp_path: Path) -> None:
        assert lifecycle._newest_source_mtime(tmp_path) == 0

    def test_current_stamp_describes_the_installed_package(self) -> None:
        stamp = lifecycle.current_stamp()
        assert stamp.version == __version__
        assert stamp.source_mtime_ns > 0


def _stamp_pid_file(settings: Settings, *, pid: int, version: str, mtime_ns: int) -> None:
    settings.pid_path.write_text(
        json.dumps({"pid": pid, "version": version, "source_mtime_ns": mtime_ns}),
        encoding="utf-8",
    )


class TestDaemonOnOtherCodeIsReplaced:
    """A daemon serves the code it loaded, and a stale answer looks correct.

    OBSERVED during the fix for issue-44875a5a6ca6: `docir check` reported 117
    cycle findings and `docir --no-daemon check` reported 0, because a daemon
    started before the edit was still answering. Nothing in either output said
    which code produced it (issue-aaa512e9c58f).
    """

    @pytest.fixture
    def spy(self, monkeypatch: pytest.MonkeyPatch, settings: Settings) -> Counter[str]:
        calls: Counter[str] = Counter()

        def spawn(_: Settings) -> int:
            calls["spawn"] += 1
            return 4242

        def stop(_: Settings) -> bool:
            calls["stop"] += 1
            return True

        settings.ensure_directories()
        monkeypatch.setattr(lifecycle, "is_running", lambda _: True)
        monkeypatch.setattr(lifecycle, "spawn", spawn)
        monkeypatch.setattr(lifecycle, "stop", stop)
        monkeypatch.setattr(lifecycle, "wait_until_ready", lambda _, timeout=0.0: True)
        return calls

    def test_a_daemon_on_this_build_is_left_alone(
        self, settings: Settings, spy: Counter[str]
    ) -> None:
        lifecycle.write_pid(settings)
        lifecycle.ensure_running(settings)
        assert spy == Counter()

    def test_an_upgraded_version_replaces_it(self, settings: Settings, spy: Counter[str]) -> None:
        stamp = lifecycle.current_stamp()
        _stamp_pid_file(settings, pid=os.getpid(), version="0.0.1", mtime_ns=stamp.source_mtime_ns)
        lifecycle.ensure_running(settings)
        assert spy == Counter(stop=1, spawn=1)

    def test_an_edited_source_tree_replaces_it(self, settings: Settings, spy: Counter[str]) -> None:
        stamp = lifecycle.current_stamp()
        _stamp_pid_file(
            settings,
            pid=os.getpid(),
            version=stamp.version,
            mtime_ns=stamp.source_mtime_ns - 1,
        )
        lifecycle.ensure_running(settings)
        assert spy == Counter(stop=1, spawn=1)

    def test_an_unstamped_daemon_replaces_it(self, settings: Settings, spy: Counter[str]) -> None:
        settings.pid_path.write_text(str(os.getpid()), encoding="utf-8")
        lifecycle.ensure_running(settings)
        assert spy == Counter(stop=1, spawn=1)

    def test_an_absent_daemon_is_started_without_a_stop(
        self, settings: Settings, spy: Counter[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Nothing is serving, so there is nothing to shut down first.
        monkeypatch.setattr(lifecycle, "is_running", lambda _: False)
        lifecycle.ensure_running(settings)
        assert spy == Counter(spawn=1)


class TestStatusReportsTheServedBuild:
    @pytest.fixture
    def running(self, monkeypatch: pytest.MonkeyPatch, settings: Settings) -> Settings:
        settings.ensure_directories()
        monkeypatch.setattr(lifecycle, "is_running", lambda _: True)
        return settings

    def test_current_daemon_reports_its_version(self, running: Settings) -> None:
        lifecycle.write_pid(running)
        snapshot = lifecycle.status(running)
        assert snapshot.version == __version__
        assert snapshot.stale_code is False

    def test_stale_daemon_reports_the_version_it_still_serves(self, running: Settings) -> None:
        _stamp_pid_file(running, pid=os.getpid(), version="0.0.1", mtime_ns=1)
        snapshot = lifecycle.status(running)
        assert snapshot.version == "0.0.1"
        assert snapshot.stale_code is True

    def test_unstamped_daemon_has_no_version_and_is_stale(self, running: Settings) -> None:
        running.pid_path.write_text(str(os.getpid()), encoding="utf-8")
        snapshot = lifecycle.status(running)
        assert snapshot.version is None
        assert snapshot.stale_code is True

    def test_a_stopped_daemon_reports_no_build(self, settings: Settings) -> None:
        snapshot = lifecycle.status(settings)
        assert snapshot.version is None
        assert snapshot.stale_code is False


class TestDaemonStatusOutput:
    """`daemon status` printed the socket and nothing about the code served."""

    def _render(self, monkeypatch: pytest.MonkeyPatch, snapshot: lifecycle.DaemonStatus) -> str:
        from typer.testing import CliRunner

        from docir.entry_points.cli.app import app

        monkeypatch.setenv("COLUMNS", "200")
        monkeypatch.setattr(lifecycle, "status", lambda _: snapshot)
        result = CliRunner().invoke(app, ["daemon", "status"])
        assert result.exit_code == 0
        return result.stdout

    def test_the_served_version_is_printed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        output = self._render(
            monkeypatch,
            lifecycle.DaemonStatus(
                running=True, pid=7, socket_path="/tmp/s.sock", version="0.9.0", stale_code=False
            ),
        )
        assert "0.9.0" in output
        assert "stale" not in output

    def test_a_stale_daemon_says_so(self, monkeypatch: pytest.MonkeyPatch) -> None:
        output = self._render(
            monkeypatch,
            lifecycle.DaemonStatus(
                running=True, pid=7, socket_path="/tmp/s.sock", version="0.8.0", stale_code=True
            ),
        )
        assert "0.8.0" in output
        assert "stale code" in output

    def test_an_unstamped_daemon_says_the_build_is_unknown(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        output = self._render(
            monkeypatch,
            lifecycle.DaemonStatus(
                running=True, pid=7, socket_path="/tmp/s.sock", version=None, stale_code=True
            ),
        )
        assert "unknown build" in output


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

    def test_reads_federate_over_the_socket(self, settings: Settings, tmp_path: Path) -> None:
        """The peer readers live in the daemon, and nothing else exercises that.

        In-process tests build the fan-out in the test's own process, so they
        cannot show that a peer opens inside a *spawned* daemon, that the
        `stores` payload key survives JSON on the wire, or that the `store`
        stamp comes back through the protocol. Each of those is a place
        federation could be silently local.
        """
        peer_home = tmp_path / "peer" / ".docir"
        peer = build_container(
            Settings.resolve(peer_home, use_daemon=False), background_embeddings=False
        )
        try:
            peer.dispatcher.dispatch(
                "add",
                {
                    "type": "decision",
                    "title": "All services authenticate with mTLS",
                    "description": "Platform-wide transport rule.",
                },
            )
        finally:
            peer.close()

        daemon_settings = Settings.resolve(settings.home, use_daemon=True)
        daemon_settings.ensure_directories()
        try:
            lifecycle.ensure_running(daemon_settings)
            executor = SocketExecutor(daemon_settings)
            local = executor.execute(
                Request(
                    command="add",
                    payload={
                        "type": "issue",
                        "title": "Login endpoint returns 500",
                        "description": "Fails under load.",
                    },
                )
            )
            assert local.ok

            # Ad-hoc first: the peer travels in the payload, as `--store` and the
            # MCP `stores` argument both send it.
            ad_hoc = executor.execute(
                Request(
                    command="query", payload={"limit": 10, "stores": [str(peer_home.resolve())]}
                )
            )
            assert ad_hoc.ok
            rows = ad_hoc.data
            assert isinstance(rows, list)
            assert {row["title"] for row in rows} == {
                "Login endpoint returns 500",
                "All services authenticate with mTLS",
            }
            assert {row["store"] for row in rows} == {
                str(daemon_settings.home),
                str(peer_home.resolve()),
            }

            # Then declared: the daemon re-reads stores.yaml per request, so a
            # file written after it started must still be seen.
            (daemon_settings.home / "stores.yaml").write_text(
                f"stores:\n  - {peer_home.resolve()}\n", encoding="utf-8"
            )
            declared = executor.execute(Request(command="query", payload={"limit": 10}))
            assert declared.ok
            declared_rows = declared.data
            assert isinstance(declared_rows, list)
            assert len(declared_rows) == 2

            # A write still lands in one store, over the socket like everywhere
            # else: the daemon holds the peers, so this is where "writes never
            # federate" would break without anything saying so.
            peer_ids = {
                row["id"] for row in declared_rows if row["store"] == str(peer_home.resolve())
            }
            missing = executor.execute(
                Request(command="update", payload={"doc_id": next(iter(peer_ids)), "status": "x"})
            )
            assert not missing.ok
            assert "no document" in str((missing.error or {}).get("message", ""))
        finally:
            lifecycle.stop(daemon_settings)

    def test_a_live_daemon_on_other_code_is_replaced(self, settings: Settings) -> None:
        daemon_settings = Settings.resolve(settings.home, use_daemon=True)
        try:
            lifecycle.ensure_running(daemon_settings)
            first = lifecycle.read_pid(daemon_settings)
            assert first is not None

            # Stand in for "the code changed under it": the daemon is healthy
            # and answering, it is simply not running this build any more.
            stamp = lifecycle.current_stamp()
            _stamp_pid_file(
                daemon_settings,
                pid=first,
                version=stamp.version,
                mtime_ns=stamp.source_mtime_ns - 1,
            )
            assert not lifecycle.serves_current_code(daemon_settings)

            assert SocketExecutor(daemon_settings).execute(Request(command="ping")).ok

            second = lifecycle.read_pid(daemon_settings)
            assert second is not None and second != first
            assert lifecycle.serves_current_code(daemon_settings)
        finally:
            lifecycle.stop(daemon_settings)
