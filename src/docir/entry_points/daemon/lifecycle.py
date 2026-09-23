"""Daemon process lifecycle: PID file, spawn, readiness, stop, status.

The daemon is disposable — if it is not running, killed, its socket is stale,
or it is serving code that is no longer installed, the client transparently
respawns it, so no command hard-fails just because the daemon was not up yet.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from docir import __version__
from docir.config.settings import NO_DAEMON_ENV, Settings, embed_threads
from docir.platform.errors import DaemonError
from docir.platform.transport.client import DaemonClient

_READY_TIMEOUT = 10.0
_EXIT_TIMEOUT = 5.0
_POLL_INTERVAL = 0.05

#: The installed package's source tree — this file sits at
#: ``<package>/entry_points/daemon/lifecycle.py``.
_PACKAGE_ROOT = Path(__file__).resolve().parents[2]


def socket_path(settings: Settings) -> Path | None:
    """Where this store's daemon listens, or ``None`` if it can listen nowhere.

    The socket lives under the system temp directory, so asking for it asks
    the platform for one — and in a read-only sandbox there may be none, which
    `tempfile` reports by raising. Every command that *dispatches* already
    survives that: the executor falls back to running in process
    (issue-c4c6349e06d4). The two commands that do not dispatch, `doctor` and
    `daemon status`, read the path directly to report it, so they ended in a
    traceback — which lands on the commands somebody runs *to diagnose* the
    first failure (issue-b9800d8265f6).

    ``None`` is a fact about the environment, not a missing value: there is no
    daemon here and there cannot be one, so `is_running` is false and `stop` has
    nothing to unlink. It is never a *default* — `daemon serve` refuses rather
    than guessing a path, because a server with nowhere to bind cannot serve.
    """
    try:
        return settings.socket_path
    except OSError:
        return None


def _client(settings: Settings) -> DaemonClient | None:
    """A client for this store, or ``None`` where no socket path exists."""
    path = socket_path(settings)
    if path is None:
        return None
    return DaemonClient(path, request_timeout=settings.request_timeout)


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
    """What the pid file says: the pid, the build served, and the schema loaded.

    Two inputs, because the container resolves both once and then answers every
    request from them. The build is process-wide; the schema belongs to this
    store, which is why it rides here rather than inside :class:`CodeStamp`.
    """

    pid: int
    stamp: CodeStamp | None
    schema_digest: str | None = None
    #: The embedding thread cap the daemon was spawned with. A third input on
    #: the same argument as the other two: the daemon resolves it once, when it
    #: builds its embedder, and every request it answers afterwards runs the
    #: model that way. Without it here, setting `DOCIR_EMBED_THREADS` changed
    #: nothing until the daemon idled out, while `doctor` — which reads the
    #: *client's* environment — reported the new value the whole time. That is
    #: the trap the setting exists to remove, not one to add.
    embed_threads: int | None = None


@dataclass(frozen=True, slots=True)
class DaemonStatus:
    """A snapshot of the daemon's state for ``docir daemon status``."""

    running: bool
    pid: int | None
    #: ``None`` where the platform offers nowhere to put a socket, which is a
    #: daemon that cannot exist rather than one that is merely down.
    socket_path: str | None
    version: str | None
    stale_code: bool
    stale_schema: bool


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


def schema_digest(settings: Settings) -> str | None:
    """A digest of the store's schema file, or ``None`` when it cannot be read.

    The daemon resolves ``docs-schema.yaml`` once, when it builds its container,
    and every request it answers afterwards reads that one object -- Tier 0
    validation included. So an edit to the file was honoured in-process and
    ignored over the socket until the daemon idled out: a declared check went
    unreported, and worse, a write was validated against a rule the file no
    longer stated, silently and in both directions (issue-c2e8ce341a00).

    Deliberately **not** cached, unlike :func:`current_stamp`. That one is
    cached so the daemon reports the build it started with; this one is the
    client asking what the file says *now*, to compare against what the daemon
    recorded when it started.
    """
    try:
        data = settings.schema_path.read_bytes()
    except OSError:
        return None
    return hashlib.sha256(data).hexdigest()


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
    recorded_threads = data.get("embed_threads")
    recorded_schema = data.get("schema_digest")
    return PidRecord(
        pid=pid,
        stamp=stamp,
        # Absent on a pid file written before the schema rode along, which never
        # matches a store that has one -- the same reading an unknown build gets
        # below, and the same safe direction: replace it.
        schema_digest=str(recorded_schema) if isinstance(recorded_schema, str) else None,
        embed_threads=recorded_threads if isinstance(recorded_threads, int) else None,
    )


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


def write_pid(settings: Settings, schema_digest_at_load: str | None) -> None:
    """Record the process id, the build being served, and the schema loaded.

    ``schema_digest_at_load`` is passed in rather than read here, and the caller
    must take it *before* it builds the container. Reading it afterwards would
    record a digest the container may not have loaded, which is the stale-daemon
    bug in miniature; reading it early can only over-report a mismatch, and that
    costs one respawn.
    """
    stamp = current_stamp()
    settings.pid_path.parent.mkdir(parents=True, exist_ok=True)
    settings.pid_path.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "version": stamp.version,
                "source_mtime_ns": stamp.source_mtime_ns,
                "schema_digest": schema_digest_at_load,
                "embed_threads": embed_threads(),
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
    client = _client(settings)
    return client is not None and client.is_available()


def serves_current_code(settings: Settings) -> bool:
    """Whether the recorded daemon loaded the build this process is running."""
    record = read_pid_record(settings)
    return record is not None and record.stamp == current_stamp()


def serves_current_schema(settings: Settings) -> bool:
    """Whether the recorded daemon loaded the schema this store now declares."""
    record = read_pid_record(settings)
    return record is not None and record.schema_digest == schema_digest(settings)


def serves_current_embed_threads(settings: Settings) -> bool:
    """Whether the recorded daemon runs the model with the cap now in force.

    ``settings`` is unused and taken anyway, so this reads like its two
    siblings at the one call site that composes all three; the cap is a
    property of the environment rather than of the store.
    """
    record = read_pid_record(settings)
    return record is not None and record.embed_threads == embed_threads()


def wait_until_ready(settings: Settings, timeout: float = _READY_TIMEOUT) -> bool:
    """Poll the socket until the daemon accepts connections or time runs out."""
    client = _client(settings)
    if client is None:
        return False
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

    A daemon that loaded a different ``docs-schema.yaml`` is replaced for the
    same reason and by the same mechanism (issue-c2e8ce341a00). The schema is
    resolved once per container, so an edit to it was invisible over the socket
    while being honoured in process — and it decides Tier 0, so the stale answer
    included *refusing a write* the file now permits.
    """
    if is_running(settings):
        if (
            serves_current_code(settings)
            and serves_current_schema(settings)
            and serves_current_embed_threads(settings)
        ):
            return
        stop(settings)
    else:
        clear_pid(settings)
        path = socket_path(settings)
        if path is None:
            # Nowhere to put a socket, so there is nothing to spawn *into*. A
            # typed error rather than the `FileNotFoundError` the property
            # raises, because the caller falls back to running in process and
            # prints this as the reason it is doing so.
            raise DaemonError(
                "no usable temporary directory, so the daemon has nowhere to "
                "listen; set TMPDIR to a writable directory, or "
                f"{NO_DAEMON_ENV}=1 to stop trying"
            )
        path.unlink(missing_ok=True)
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
    if client is not None and client.is_available():
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
    # The pid file still goes, even with nowhere to unlink a socket: it lives
    # under the home and a leftover one outlives the daemon it named.
    path = socket_path(settings)
    if path is not None:
        path.unlink(missing_ok=True)
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
        socket_path=str(path) if (path := socket_path(settings)) is not None else None,
        version=stamp.version if stamp is not None else None,
        stale_code=running and stamp != current_stamp(),
        stale_schema=running
        and (record is None or record.schema_digest != schema_digest(settings)),
    )
