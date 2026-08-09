"""How docir was installed, and what upgrading it would take.

Pure: :func:`detect` reads :class:`Evidence` — a few facts about the running
interpreter, gathered by ``infra`` — and returns the one thing the caller needs,
which is *the command to run*, or an honest reason there is none.

The distinction that matters is not "which installer" but **whether docir may
upgrade itself here**. A tool installed into its own environment (uv tool, pipx)
owns that environment and can replace it. A docir installed from a checkout, or
pinned by a project's lockfile, is a dependency of something else: upgrading it
behind that project's back would leave the lockfile describing a version that is
no longer installed. And an ephemeral ``uvx`` run has nothing to upgrade — the
environment is resolved per invocation and thrown away.

A wrong guess is worse than no guess, so the fallthrough case runs nothing and
says so.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: The distribution name to hand an installer.
PACKAGE = "docir"


@dataclass(frozen=True, slots=True)
class Evidence:
    """Facts about the running interpreter, gathered without interpreting them."""

    #: ``sys.prefix`` — the environment docir is installed into.
    prefix: Path
    #: ``sys.executable``, so a pip upgrade targets *this* interpreter.
    executable: Path
    #: A ``uv tool install`` leaves its receipt at the root of the tool's venv.
    has_uv_receipt: bool
    #: pipx writes ``pipx_metadata.json`` beside the venv it manages.
    has_pipx_metadata: bool
    #: The ``direct_url.json`` URL from the installed distribution, if any. A
    #: ``file://`` URL means the package came from a path rather than an index.
    direct_url: str | None
    #: Whether that install is editable (a checkout, wired in place).
    editable: bool
    #: Whether the environment lives inside uv's cache — an ephemeral ``uvx`` run.
    ephemeral: bool


@dataclass(frozen=True, slots=True)
class Installation:
    """How this docir got here, and how to move it forward."""

    #: ``uv-tool`` | ``pipx`` | ``pip`` | ``project`` | ``uvx`` | ``unknown``.
    method: str
    #: The command that upgrades it, or ``()`` when docir will not run one.
    upgrade_command: tuple[str, ...]
    #: Why there is no command, or what the command will do. Always set: the
    #: caller prints this either way, and "nothing happened" needs a reason.
    explanation: str

    @property
    def can_self_upgrade(self) -> bool:
        return bool(self.upgrade_command)


def detect(evidence: Evidence) -> Installation:
    """Classify the installation. Order matters — the specific cases come first."""
    if evidence.has_uv_receipt:
        return Installation(
            method="uv-tool",
            upgrade_command=("uv", "tool", "upgrade", PACKAGE),
            explanation="installed as a uv tool, which owns its environment",
        )
    if evidence.has_pipx_metadata:
        return Installation(
            method="pipx",
            upgrade_command=("pipx", "upgrade", PACKAGE),
            explanation="installed by pipx, which owns its environment",
        )
    if evidence.ephemeral:
        return Installation(
            method="uvx",
            upgrade_command=(),
            explanation=(
                "running from an ephemeral uvx environment — there is nothing here to "
                f"upgrade; name the version instead: `uvx {PACKAGE}@latest ...`"
            ),
        )
    if evidence.editable or _is_local(evidence.direct_url):
        return Installation(
            method="project",
            upgrade_command=(),
            explanation=(
                "installed from a local path, so this docir belongs to a project rather "
                f"than to you; upgrade it there (`uv lock --upgrade-package {PACKAGE}` "
                "then `uv sync`)"
            ),
        )
    if (evidence.prefix / "pyvenv.cfg").exists():
        return Installation(
            method="pip",
            upgrade_command=(
                str(evidence.executable),
                "-m",
                "pip",
                "install",
                "--upgrade",
                PACKAGE,
            ),
            explanation="installed with pip into a virtual environment",
        )
    return Installation(
        method="unknown",
        upgrade_command=(),
        explanation=(
            "cannot tell how docir was installed, and guessing would run the wrong "
            "installer against the wrong environment — upgrade it the way you installed it"
        ),
    )


def _is_local(direct_url: str | None) -> bool:
    """Whether the distribution was installed from a path rather than an index."""
    return bool(direct_url) and str(direct_url).startswith("file:")
