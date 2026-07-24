"""Public surface of the agents module.

Installs and refreshes the AI-assistant instruction files that teach a coding
agent to drive docir (a Claude Code skill and/or an ``AGENTS.md`` block). This
module owns no index or database state — it is a local scaffolding operation over
the filesystem and the packaged instruction template (see ADR-0008), so it runs
in-process and never touches the daemon or the shared unit-of-work.

Consumers build a service through :func:`build_agent_service` and drive it with
:class:`InstallRequest` / :class:`UpdateRequest`; the concrete adapters stay
private to the module.
"""

from __future__ import annotations

from docir.modules.agents.application.service import (
    AgentSetupService,
    InstallRequest,
    SetupResult,
    UpdateRequest,
)
from docir.modules.agents.domain.results import InstallAction, InstalledFile
from docir.modules.agents.domain.targets import AGENT_TARGETS, DEFAULT_AGENTS
from docir.modules.agents.infra.file_sink import FilesystemSink
from docir.modules.agents.infra.template_provider import PackagedTemplateProvider

#: Valid ``--agent`` names, for CLI validation / help.
AGENT_NAMES: tuple[str, ...] = tuple(AGENT_TARGETS)


def build_agent_service(version: str) -> AgentSetupService:
    """Wire the agent-setup service for one process (``version`` is stamped in)."""
    return AgentSetupService(PackagedTemplateProvider(), FilesystemSink(), version)


__all__ = [
    "AGENT_NAMES",
    "DEFAULT_AGENTS",
    "AgentSetupService",
    "InstallAction",
    "InstallRequest",
    "InstalledFile",
    "SetupResult",
    "UpdateRequest",
    "build_agent_service",
]
