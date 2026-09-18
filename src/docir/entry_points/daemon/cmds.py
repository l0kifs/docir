"""The ``docir daemon`` subcommands: serve (internal), start, status, stop."""

from __future__ import annotations

import typer

from docir.config.settings import Settings
from docir.entry_points.cli import rendering
from docir.entry_points.cli.runner import get_state, run_local
from docir.entry_points.daemon import lifecycle
from docir.entry_points.daemon.release_watch import ReleaseWatcher
from docir.entry_points.daemon.watcher import DocsWatcher
from docir.platform.errors import DaemonError
from docir.platform.transport.messages import SerializingExecutor
from docir.platform.transport.server import DaemonServer

daemon_app = typer.Typer(help="Manage the background daemon.", no_args_is_help=True)


@daemon_app.command("serve", hidden=True)
def serve() -> None:
    """Run the daemon in the foreground (spawned as a detached child)."""
    settings = get_state().settings
    # Through `run_local` like every other command that does not dispatch: it is
    # what turns a typed error into `error: <message>` and the exit code the
    # error carries, instead of a traceback. This one has a refusal to render
    # now (issue-b9800d8265f6), and the client reads the daemon's log when it
    # will not come up — a traceback there buries the sentence naming the cause.
    run_local(lambda: _run_server(settings))


@daemon_app.command("start")
def start() -> None:
    """Ensure the daemon is running, spawning it if necessary."""
    settings = get_state().settings
    # Spawns a detached child and waits for it to answer; the child warms the
    # embedding model before it does.
    with rendering.progress("starting the daemon"):
        lifecycle.ensure_running(settings)
    snapshot = lifecycle.status(settings)
    rendering.render_message(
        f"[green]daemon running[/] (pid {snapshot.pid}) at {snapshot.socket_path}"
    )


#: What `daemon status` says where a socket cannot exist at all. Not "not
#: running", which reads as "start it" and would send the caller round a loop
#: nothing in this environment can close (issue-b9800d8265f6).
_NOWHERE_TO_LISTEN = (
    "[dim]cannot run here[/] — no usable temporary directory for the socket, so "
    "every command runs in process"
)


@daemon_app.command("status")
def status() -> None:
    """Show whether the daemon is running, and which build it is serving."""
    snapshot = lifecycle.status(get_state().settings)
    if snapshot.socket_path is None:
        rendering.render_message(_NOWHERE_TO_LISTEN)
        return
    if not snapshot.running:
        rendering.render_message("[dim]not running[/]")
        return
    served = snapshot.version or "an unknown build"
    if snapshot.stale_code:
        note = " [yellow](stale code — the next command replaces it)[/]"
    elif snapshot.stale_schema:
        note = " [yellow](loaded an older docs-schema.yaml — the next command replaces it)[/]"
    else:
        note = ""
    rendering.render_message(
        f"[green]running[/] (pid {snapshot.pid}) at {snapshot.socket_path} · serving {served}{note}"
    )


@daemon_app.command("stop")
def stop() -> None:
    """Stop the daemon if it is running."""
    with rendering.progress("stopping the daemon"):
        stopped = lifecycle.stop(get_state().settings)
    rendering.render_message(
        "[green]daemon stopped[/]" if stopped else "[dim]daemon was not running[/]"
    )


def _run_server(settings: Settings) -> None:
    from docir.entry_points.composition import InProcessExecutor, build_container

    # Digest the schema *before* the container resolves it. Recording what the
    # file says after the load would stamp a schema this daemon may not be
    # serving, which is the very staleness this closes (issue-c2e8ce341a00).
    schema_digest = lifecycle.schema_digest(settings)
    container = build_container(settings, background_embeddings=True)
    lifecycle.write_pid(settings, schema_digest)
    # Wrapped once, shared by both callers. The server serializes clients; the
    # watcher is a second writer on another thread, and SQLite has one.
    executor = SerializingExecutor(InProcessExecutor(container.dispatcher))
    watcher = DocsWatcher(settings, executor) if settings.watch else None
    # Opt-in, and only here: the CLI reads the answer this leaves behind rather
    # than making a network call of its own (DOCIR_UPDATE_CHECK=1).
    releases = ReleaseWatcher(settings) if settings.update_check else None
    listening_on = lifecycle.socket_path(settings)
    if listening_on is None:
        # The one caller that cannot carry on without a path. A client falls
        # back to running in process; a server with nowhere to bind is not a
        # degraded daemon, it is not a daemon.
        raise DaemonError(
            "no usable temporary directory, so the daemon has nowhere to listen; "
            "set TMPDIR to a writable directory"
        )
    server = DaemonServer(listening_on, executor, idle_timeout=settings.idle_timeout)
    try:
        if watcher is not None:
            watcher.start()
        if releases is not None:
            releases.start()
        server.serve_forever()
    finally:
        if watcher is not None:
            watcher.stop()
        if releases is not None:
            releases.stop()
        container.close()
        lifecycle.clear_pid(settings)
