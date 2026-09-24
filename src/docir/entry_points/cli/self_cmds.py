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
from docir.modules.release.api import (
    ReleaseService,
    ReleaseStatus,
    UpgradeOutcome,
    build_release_service,
)

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
    checked, or the check could not reach the index.

    This is the *unthrottled* answer, and it always answers — the ambient notice
    on other commands says a thing once a day, and says nothing at all in an
    installation that cannot upgrade itself (a checkout, a lockfile-managed
    project). Ask here when you want to know rather than to be told.

    Whether the ambient notice runs at all: `update_check: true` in the store's
    `config.yaml`, which `docir init` writes; `DOCIR_UPDATE_CHECK=0` or `=1`
    overrides it for one shell, and a CI run never checks.

        docir self status --refresh
        {"installed":"0.28.0","latest":"0.28.0","update_available":false,
         "checked_on":"2026-09-23","method":"uv-tool",
         "upgrade_command":["uv","tool","upgrade","docir"],...}
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

    Six things in one command. It upgrades the package where docir owns its
    environment (a uv tool, a pipx install, a virtualenv) — and where it does
    not, says why and carries on. Then it rebuilds the index (derived,
    gitignored, and the only place the schema baseline and the build version are
    recorded), refreshes any installed agent instruction file to the running
    version, tops up the store's own `.gitignore` and its `config.yaml` with
    anything this docir writes that they do not yet carry, and reports what
    `check` still finds — `check` last, so the findings describe the state you
    are left in.

    Both top-ups **append and never rewrite**. Your own lines in those files are
    yours; only the entries this build generates and the file lacks are added,
    the `.gitignore` ones under a comment naming the version that added them.
    A `config.yaml` setting already present keeps its value, whatever it is: it
    is an answer somebody gave. The file is committed, so what is added there is
    added for everyone who clones the repo — the command says which keys moved.

    That report is **counted, not listed**: errors print in full, warnings are
    tallied by kind, and `docir check` reads them. An upgrade is exactly the
    event that moves a lot of code at once, so enumerating every finding here
    buries the three lines above it — which are the answer the command was run
    for. `--json` is unaffected and still carries every finding.

    The package step re-executes docir before doing the rest, because this
    process is the code being replaced: every step after the install would
    otherwise be the old build's work, starting with the stamp saying which
    version built the index. Pass --no-package to skip the install and only
    resync the store.

    An installer that exits 0 has not necessarily changed anything, so the
    version is read back afterwards. When it did not move, the command says so,
    quotes what the installer printed — which is where the cause is, and often
    the exact command that clears it — and carries on with the store half rather
    than failing. A `uv tool` install pinned to an exact version is the common
    case; `docir self status` names the method when the installer explains
    nothing.

    The rebuild runs in full only when the index carries a different version's
    build stamp. Against a store this build already indexed there is nothing for a
    full pass to re-read, and the run reports 0 documents rather than paying for
    it. A full pass is no longer expensive by itself either: it queues every
    document it re-saves, and the drain recomputes only the vectors whose model,
    text or chunking moved, so the release that changes none of them re-embeds
    nothing (issue-77dd42e3a03a).
    """
    if not no_package and upgraded_from is None:
        _upgrade_the_package_then_restart()

    with rendering.progress("rebuilding the store"):
        result = with_executor(
            lambda executor: upgrade_store(
                lambda command, payload: execute_with(executor, command, payload),
                project_root=directory.resolve(),
                store_home=get_state().settings.home,
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
            "gitignore_added": list(result.gitignore_added),
            "config_added": list(result.config_added),
            "findings": findings,
        }
        rendering.emit_json(payload, trim=state.trim)
    else:
        rendering.render_upgrade(
            result.reindex,
            agents,
            findings,
            result.upgraded_from,
            result.gitignore_added,
            result.config_added,
        )


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
    if outcome.version_moved is False:
        # Exit 0 and nothing moved. Not a failure — the store still wants
        # resyncing — and not an upgrade either, so there is nothing to hand
        # off to: re-executing here would replace this process with an
        # identical one and lose what the installer said on the way.
        _report_a_stalled_upgrade(outcome, service)
        return
    _restart_as_the_new_build()


def _report_a_stalled_upgrade(outcome: UpgradeOutcome, service: ReleaseService) -> None:
    """Say that the installer ran and changed nothing, and hand over its words.

    docir does **not** diagnose why. The installers it drives already know —
    `uv tool upgrade` on a pinned receipt prints the pin *and* the command that
    clears it — and every cause docir re-derived would be a worse copy of what
    it is standing in front of. So this relays, and adds the one instruction
    that is true whatever the cause.

    The output is printed only here, never on a successful upgrade: a
    `pip install --upgrade` that works prints dozens of lines, and burying the
    report under them is the argument `_render_upgrade_findings` already makes.

    This is also the one moment a network call is worth the wait. The line is
    most useful when it can name the version being missed, and a machine that
    never opted into the release check has nothing cached — so the refresh
    happens here, on a command that has just run an installer, and nowhere else.
    """
    with rendering.progress("asking PyPI for the newest release"):
        latest = run_local(lambda: service.status(refresh=True)).latest
    rendering.render_stalled_upgrade(
        installed=outcome.installed_before,
        latest=latest,
        command=outcome.command,
        said=outcome.message,
    )


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
