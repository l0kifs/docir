"""The ``docir self`` subcommands: what this installation is, and bringing it current."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Annotated

import typer

from docir import __version__
from docir.config.settings import Settings
from docir.entry_points.cli import rendering
from docir.entry_points.cli.agent_cmds import _setup_file
from docir.entry_points.cli.runner import (
    execute_with,
    get_state,
    run_local,
    use_json,
    with_executor,
)
from docir.entry_points.composition import UpgradeResult, active_embedder_id, upgrade_store
from docir.modules.documents.api import load_schema
from docir.modules.release.api import ReleaseStatus, build_release_service

self_app = typer.Typer(help="Maintain the docir installation itself.", no_args_is_help=True)


@self_app.command("status")
def self_status(
    refresh: Annotated[
        bool,
        typer.Option("--refresh", help="Ask PyPI now instead of reading the last answer."),
    ] = False,
) -> None:
    """Report the docir installation: how it was installed, and whether it is current.

    A file read by default — the newest release is whatever was last fetched, and
    `checked_on` says when that was. `--refresh` asks PyPI (docir's only network
    call), and skips it when the answer is already from today.

    An absent `latest` means *unknown*, never "up to date": nothing has been
    checked, or the check could not reach the index. Set DOCIR_UPDATE_CHECK=1 to
    have the daemon keep it fresh and every command say so on stderr.
    """
    state = get_state()
    service = build_release_service(__version__, state.settings.release_cache_path)
    if refresh:
        # The cached read is instant; only --refresh goes to the network.
        with rendering.progress("asking PyPI for the newest release"):
            status_result = run_local(lambda: service.status(refresh=True))
    else:
        status_result = run_local(lambda: service.status(refresh=False))
    _emit_release_status(status_result)


@self_app.command("upgrade")
def self_upgrade(
    directory: Annotated[Path, typer.Argument(help="Project directory.")] = Path("."),
    no_package: Annotated[
        bool,
        typer.Option("--no-package", help="Skip the package upgrade; only resync this store."),
    ] = False,
    upgraded_from: Annotated[
        str | None,
        typer.Option("--upgraded-from", hidden=True),
    ] = None,
) -> None:
    """Upgrade docir, then bring this store and its generated files in line with it.

    Four things in one command. It upgrades the package where docir owns its
    environment (a uv tool, a pipx install, a virtualenv) — and where it does
    not, says why and carries on. Then it rebuilds the index (derived,
    gitignored, and the only place the schema baseline and the build version are
    recorded), refreshes any installed agent instruction file to the running
    version, and reports what `check` still finds — `check` last, so the findings
    describe the state you are left in.

    The package step re-executes docir before doing the rest, because this
    process is the code being replaced: every step after the install would
    otherwise be the old build's work, starting with the stamp saying which
    version built the index. Pass --no-package to skip the install and only
    resync the store.

    The rebuild is the expensive half — it re-embeds every document it re-saves —
    so it runs in full only when the index carries a different version's build
    stamp. Against a store this build already indexed there is nothing for a full
    pass to recompute, and the run reports 0 documents rather than paying for it.
    """
    if not no_package and upgraded_from is None:
        _upgrade_the_package_then_restart()

    with rendering.progress("rebuilding the store"):
        result = with_executor(
            lambda executor: upgrade_store(
                lambda command, payload: execute_with(executor, command, payload),
                project_root=directory.resolve(),
                version=__version__,
                upgraded_from=upgraded_from,
            )
        )
    _emit_upgrade(result)


def _emit_release_status(status: ReleaseStatus) -> None:
    state = get_state()
    payload: dict[str, object] = {
        "installed": status.installed,
        "latest": status.latest,
        "update_available": status.update_available,
        "checked_on": status.checked_on,
        "method": status.method,
        "upgrade_command": list(status.upgrade_command),
        "explanation": status.explanation,
        "embedder": _active_embedder(state.settings),
    }
    if use_json(state):
        rendering.emit_json(payload, trim=state.trim)
    else:
        rendering.render_release_status(payload)


def _emit_upgrade(result: UpgradeResult) -> None:
    """Emit one report for the three steps, rather than three commands' output."""
    agents = [_setup_file(file) for file in result.agents]
    findings = list(result.findings)
    state = get_state()
    if use_json(state):
        payload: dict[str, object] = {
            "version": result.version,
            "upgraded_from": result.upgraded_from,
            "reindex": result.reindex,
            "agents": agents,
            "findings": findings,
        }
        rendering.emit_json(payload, trim=state.trim)
    else:
        rendering.render_upgrade(result.reindex, agents, findings, result.upgraded_from)


def _upgrade_the_package_then_restart() -> None:
    """Run the installer, then hand off to the docir it just installed.

    Returns normally when nothing was installed — an environment docir does not
    own (a checkout, a lockfile-managed project, an ephemeral `uvx` run), where
    the rest of the command is still worth doing. On a successful install it does
    not return at all: the process is replaced by the new build, carrying
    `--upgraded-from` so the report can still name the version that was here.
    """
    state = get_state()
    service = build_release_service(__version__, state.settings.release_cache_path)
    rendering.render_notice("upgrading the docir package")
    outcome = run_local(service.upgrade_package)
    if not outcome.ran:
        rendering.render_warning(f"package not upgraded — {outcome.message}")
        return
    if not outcome.ok:
        rendering.render_error(
            {"message": f"`{' '.join(outcome.command)}` failed: {outcome.message}"}
        )
        raise typer.Exit(code=1)
    _restart_as_the_new_build()


def _restart_as_the_new_build() -> None:
    """Replace this process with the docir that was just installed.

    `-m docir` rather than `sys.argv[0]`: the console script is a generated
    shebang wrapper, and the interpreter is the one thing that is certainly the
    upgraded environment's.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    argv = [sys.executable, "-m", "docir", *sys.argv[1:], "--upgraded-from", __version__]
    os.execv(sys.executable, argv)


def _active_embedder(settings: Settings) -> str:
    """Which model this store's reads would embed with.

    Reported here because nothing else says it: a store can be configured for a
    different model, or fall back to the hashing embedder, and every read is
    quietly worse with no finding to name it.

    The schema file is read only if it already exists — ``load_schema`` writes
    the default when it does not, and a status command must not create a store
    as a side effect of reporting on one.
    """
    schema_path = settings.schema_path
    model = load_schema(schema_path).embed_model if schema_path.exists() else None
    return active_embedder_id(model)
