"""The ``docir daemon`` subcommands: serve (internal), start, status, stop."""

from __future__ import annotations

import typer

from docir.config.settings import Settings
from docir.entry_points.cli import rendering
from docir.entry_points.cli.runner import get_state
from docir.entry_points.daemon import lifecycle
from docir.platform.transport.server import DaemonServer

daemon_app = typer.Typer(help="Manage the background daemon.", no_args_is_help=True)


@daemon_app.command("serve", hidden=True)
def serve() -> None:
    """Run the daemon in the foreground (spawned as a detached child)."""
    settings = get_state().settings
    _run_server(settings)


@daemon_app.command("start")
def start() -> None:
    """Ensure the daemon is running, spawning it if necessary."""
    settings = get_state().settings
    lifecycle.ensure_running(settings)
    snapshot = lifecycle.status(settings)
    rendering.render_message(
        f"[green]daemon running[/] (pid {snapshot.pid}) at {snapshot.socket_path}"
    )


@daemon_app.command("status")
def status() -> None:
    """Show whether the daemon is running."""
    snapshot = lifecycle.status(get_state().settings)
    if snapshot.running:
        rendering.render_message(
            f"[green]running[/] (pid {snapshot.pid}) at {snapshot.socket_path}"
        )
    else:
        rendering.render_message("[dim]not running[/]")


@daemon_app.command("stop")
def stop() -> None:
    """Stop the daemon if it is running."""
    stopped = lifecycle.stop(get_state().settings)
    rendering.render_message(
        "[green]daemon stopped[/]" if stopped else "[dim]daemon was not running[/]"
    )


def _run_server(settings: Settings) -> None:
    from docir.entry_points.composition import InProcessExecutor, build_container

    container = build_container(settings, background_embeddings=True)
    lifecycle.write_pid(settings)
    server = DaemonServer(
        settings.socket_path,
        InProcessExecutor(container.dispatcher),
        idle_timeout=settings.idle_timeout,
    )
    try:
        server.serve_forever()
    finally:
        container.close()
        lifecycle.clear_pid(settings)
