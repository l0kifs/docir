"""Daemon process lifecycle: PID file, spawn, readiness, stop, status.

The daemon is disposable — if it is not running, killed, or its socket is
stale, the client transparently respawns it, so no command hard-fails just
because the daemon was not up yet.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import time
from dataclasses import dataclass

from docir.domain.errors import DaemonError
from docir.infrastructure.config.settings import Settings
from docir.infrastructure.daemon.client import DaemonClient

_READY_TIMEOUT = 10.0
_POLL_INTERVAL = 0.05


@dataclass(frozen=True, slots=True)
class DaemonStatus:
    """A snapshot of the daemon's state for ``docir daemon status``."""

    running: bool
    pid: int | None
    socket_path: str


def read_pid(settings: Settings) -> int | None:
    """Return the PID recorded in the pid file, if it is a valid integer."""
    try:
        return int(settings.pid_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def write_pid(settings: Settings) -> None:
    """Record the current process id as the daemon PID."""
    settings.pid_path.parent.mkdir(parents=True, exist_ok=True)
    settings.pid_path.write_text(str(os.getpid()), encoding="utf-8")


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
    return DaemonClient(settings.socket_path).is_available()


def wait_until_ready(settings: Settings, timeout: float = _READY_TIMEOUT) -> bool:
    """Poll the socket until the daemon accepts connections or time runs out."""
    client = DaemonClient(settings.socket_path)
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
    """Start the daemon if it is not already serving requests."""
    if is_running(settings):
        return
    clear_pid(settings)
    settings.socket_path.unlink(missing_ok=True)
    spawn(settings)
    if not wait_until_ready(settings):
        raise DaemonError("daemon failed to become ready in time")


def stop(settings: Settings) -> bool:
    """Stop the daemon; return whether one was running."""
    from docir.application.executor import Request

    was_running = False
    client = DaemonClient(settings.socket_path)
    if client.is_available():
        was_running = True
        with contextlib.suppress(DaemonError):
            client.send(Request(command="shutdown"))
    pid = read_pid(settings)
    if pid is not None and process_alive(pid):
        was_running = True
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, 15)
    clear_pid(settings)
    settings.socket_path.unlink(missing_ok=True)
    return was_running


def status(settings: Settings) -> DaemonStatus:
    """Return a snapshot of the daemon's current state."""
    running = is_running(settings)
    return DaemonStatus(
        running=running,
        pid=read_pid(settings) if running else None,
        socket_path=str(settings.socket_path),
    )
