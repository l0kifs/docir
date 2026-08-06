"""Daemon process lifecycle: PID file, spawn, readiness, stop, status.

The daemon is disposable — if it is not running, killed, its socket is stale,
or it is serving code that is no longer installed, the client transparently
respawns it, so no command hard-fails just because the daemon was not up yet.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from docir import __version__
from docir.config.settings import Settings
from docir.platform.errors import DaemonError
from docir.platform.transport.client import DaemonClient

_READY_TIMEOUT = 10.0
_EXIT_TIMEOUT = 5.0
_POLL_INTERVAL = 0.05

#: The installed package's source tree — this file sits at
#: ``<package>/entry_points/daemon/lifecycle.py``.
_PACKAGE_ROOT = Path(__file__).resolve().parents[2]


def _client(settings: Settings) -> DaemonClient:
    """A client for this store, carrying the configured reply timeout."""
    return DaemonClient(settings.socket_path, request_timeout=settings.request_timeout)


@dataclass(frozen=True, slots=True)
class CodeStamp:
    """Which build of docir a process loaded.

    The version alone cannot tell an edit apart from the release it was made
    on — nothing bumps ``__version__`` between commits — so the newest mtime
    across the package's sources rides along, which is what catches a change
    to ``src/`` during development. An installed wheel stamps its files at
    install time, so the pair also moves on ``uv sync`` / ``pip install -U``.
    """

    version: str
    source_mtime_ns: int


@dataclass(frozen=True, slots=True)
class PidRecord:
    """What the pid file says: the daemon's pid and the build it is serving."""

    pid: int
    stamp: CodeStamp | None


@dataclass(frozen=True, slots=True)
class DaemonStatus:
    """A snapshot of the daemon's state for ``docir daemon status``."""

    running: bool
    pid: int | None
    socket_path: str
    version: str | None
    stale_code: bool


def _newest_source_mtime(root: Path) -> int:
    """The most recent modification time across the package's Python sources."""
    return max((path.stat().st_mtime_ns for path in root.rglob("*.py")), default=0)


@cache
def current_stamp() -> CodeStamp:
    """The stamp of the code *this* process loaded, computed once and frozen.

    The caching is what makes the daemon's answer honest: it must report the
    build it started with, not whatever happens to be on disk later.
    """
    return CodeStamp(version=__version__, source_mtime_ns=_newest_source_mtime(_PACKAGE_ROOT))


def read_pid_record(settings: Settings) -> PidRecord | None:
    """Parse the pid file, tolerating a truncated or older-format one."""
    try:
        raw = settings.pid_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    try:
        data = json.loads(raw)
        pid = int(data["pid"])
        stamp = CodeStamp(
            version=str(data["version"]),
            source_mtime_ns=int(data["source_mtime_ns"]),
        )
    except (KeyError, TypeError, ValueError):
        return _unstamped_record(raw)
    return PidRecord(pid=pid, stamp=stamp)


def _unstamped_record(raw: str) -> PidRecord | None:
    """A pid file written before the stamp existed holds a bare integer.

    Its build is unknown, which never matches — correctly so: that daemon
    predates the version check and is exactly what the check exists to replace.
    """
    try:
        return PidRecord(pid=int(raw), stamp=None)
    except ValueError:
        return None


def read_pid(settings: Settings) -> int | None:
    """Return the PID recorded in the pid file, if there is a valid one."""
    record = read_pid_record(settings)
    return record.pid if record is not None else None


def write_pid(settings: Settings) -> None:
    """Record the current process id and the build it is serving."""
    stamp = current_stamp()
    settings.pid_path.parent.mkdir(parents=True, exist_ok=True)
    settings.pid_path.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "version": stamp.version,
                "source_mtime_ns": stamp.source_mtime_ns,
            }
        ),
        encoding="utf-8",
    )


def clear_pid(settings: Settings) -> None:
    """Remove the pid file (best effort)."""
    settings.pid_path.unlink(missing_ok=True)


def process_alive(pid: int) -> bool:
    """Whether a process with ``pid`` currently exists."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def is_running(settings: Settings) -> bool:
    """Whether a usable daemon (live process + accepting socket) exists."""
    pid = read_pid(settings)
    if pid is None or not process_alive(pid):
        return False
    return _client(settings).is_available()


def serves_current_code(settings: Settings) -> bool:
    """Whether the recorded daemon loaded the build this process is running."""
    record = read_pid_record(settings)
    return record is not None and record.stamp == current_stamp()


def wait_until_ready(settings: Settings, timeout: float = _READY_TIMEOUT) -> bool:
    """Poll the socket until the daemon accepts connections or time runs out."""
    client = _client(settings)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if client.is_available():
            return True
        time.sleep(_POLL_INTERVAL)
    return client.is_available()


def spawn(settings: Settings) -> int:
    """Launch the daemon as a detached background process; return its PID."""
    env = dict(os.environ)
    env["DOCIR_HOME"] = str(settings.home)
    settings.ensure_directories()
    log_file = settings.log_path.open("ab")
    process = subprocess.Popen(
        [sys.executable, "-m", "docir", "daemon", "serve"],
        stdout=log_file,
        stderr=log_file,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        env=env,
    )
    return process.pid


def ensure_running(settings: Settings) -> None:
    """Start the daemon unless one is already serving *this* build.

    A live daemon running different code is stopped and replaced. It loaded
    docir once and lives on, so after an upgrade or an edit to ``src/`` it
    keeps answering from the old code — and a stale answer is indistinguishable
    from a correct one, which is what makes it worth a restart rather than a
    warning (issue-aaa512e9c58f).
    """
    if is_running(settings):
        if serves_current_code(settings):
            return
        stop(settings)
    else:
        clear_pid(settings)
        settings.socket_path.unlink(missing_ok=True)
    spawn(settings)
    if not wait_until_ready(settings):
        raise DaemonError("daemon failed to become ready in time")


def stop(settings: Settings) -> bool:
    """Stop the daemon; return whether one was running."""
    from docir.platform.transport.messages import Request

    was_running = False
    client = _client(settings)
    if client.is_available():
        was_running = True
        with contextlib.suppress(DaemonError):
            client.send(Request(command="shutdown"))
    pid = read_pid(settings)
    if pid is not None and process_alive(pid):
        was_running = True
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, 15)
        _await_exit(pid)
    clear_pid(settings)
    settings.socket_path.unlink(missing_ok=True)
    return was_running


def _await_exit(pid: int, timeout: float = _EXIT_TIMEOUT) -> None:
    """Block until a signalled daemon has actually gone.

    Its own teardown clears the pid file and unlinks the socket, so a
    replacement spawned while it is still winding down can have both removed
    out from under it — leaving a healthy daemon that no client can find.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and process_alive(pid):
        time.sleep(_POLL_INTERVAL)


def status(settings: Settings) -> DaemonStatus:
    """Return a snapshot of the daemon's current state.

    Reports the build being served, so a stale daemon is inspectable rather
    than something you can only infer from an answer that looks wrong.
    """
    running = is_running(settings)
    record = read_pid_record(settings) if running else None
    stamp = record.stamp if record is not None else None
    return DaemonStatus(
        running=running,
        pid=record.pid if record is not None else None,
        socket_path=str(settings.socket_path),
        version=stamp.version if stamp is not None else None,
        stale_code=running and stamp != current_stamp(),
    )
