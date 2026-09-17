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
    written_before = _log_size(settings)
    spawn(settings)
    if not wait_until_ready(settings):
        raise DaemonError(_not_ready_message(settings, written_before))


#: Lines of the daemon's own output quoted when it does not come up.
#:
#: Few on purpose, and measured against the case this exists for: a traceback's
#: *last* line is the exception, and everything above it is frames. Twelve lines
#: put ten frames in front of the one sentence naming the cause, which buries it
#: as effectively as the bare timeout did. Six keeps the exception, the line
#: that raised it, and a frame of context. The whole file is still there.
_LOG_TAIL_LINES = 6

#: Characters kept from those lines. A daemon that fails in a loop can write a
#: great deal before the deadline, and an error message is read in a terminal.
_LOG_TAIL_CHARS = 1200


def _log_size(settings: Settings) -> int:
    """Bytes already in the daemon log, so a failure quotes only what follows.

    The log is appended to across every spawn this store has ever done, so
    quoting its tail unconditionally would attribute last week's traceback to
    this morning's timeout — a wrong cause stated with confidence, which is
    worse than the bare timeout this is replacing.
    """
    try:
        return settings.log_path.stat().st_size
    except OSError:
        return 0


def _not_ready_message(settings: Settings, written_before: int) -> str:
    """The timeout, plus whatever the daemon itself said while failing.

    The client cannot see why a daemon died: it spawns one, waits, and all it
    knows is that nothing started answering (issue-1e310cf366b8). The reason is
    in the log, because `spawn` points the child's stdout and stderr there — so
    the honest thing is to carry it across rather than to report the wait as if
    it were the diagnosis.

    Quoted as *what it said*, never as the cause. A daemon can also miss this
    deadline while perfectly healthy — a cold model load on a slow disk — and
    then these lines are progress, not an error. The reader is the one who can
    tell; this is here so there is something to tell it from.

    Silence is its own answer, and the message says so: a daemon that wrote
    nothing at all did not get as far as failing out loud, which points at the
    spawn rather than at the store.
    """
    tail = _recent_log(settings, written_before)
    if not tail:
        return (
            f"daemon failed to become ready in time, and wrote nothing to "
            f"{settings.log_path} — it may not have started at all"
        )
    return f"daemon failed to become ready in time; it last wrote:\n{tail}"


def _worth_quoting(line: str) -> bool:
    """Whether a log line carries anything, once the pointers are dropped.

    Blank lines, and the ``^^^^``/``~~~~`` rows a Python traceback draws under
    the expression it blames. Those point at a column in a line the reader
    cannot see here, and each one costs a slot in a window sized for the
    sentence that names the cause.
    """
    stripped = line.strip()
    return bool(stripped) and bool(stripped.strip("^~"))


def _recent_log(settings: Settings, written_before: int) -> str:
    """The daemon's output since ``written_before``, trimmed and indented.

    Never raises: this runs inside the construction of an error message, and an
    error about reading the log would replace the error the reader came for.
    """
    try:
        with settings.log_path.open("rb") as handle:
            handle.seek(written_before)
            fresh = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    lines = [line.rstrip() for line in fresh.splitlines() if _worth_quoting(line)]
    if not lines:
        return ""
    trimmed = "\n".join(f"    {line}" for line in lines[-_LOG_TAIL_LINES:])
    if len(trimmed) > _LOG_TAIL_CHARS:
        trimmed = f"    ...\n{trimmed[-_LOG_TAIL_CHARS:]}"
    return trimmed


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
