"""Public surface of the agents module.

Installs and refreshes the AI-assistant instruction files that teach a coding
agent to drive docir (a Claude Code skill and/or an ``AGENTS.md`` block). This
module owns no index or database state — it is a local scaffolding operation over
the filesystem and the packaged instruction template (see adr-3a2d5ee7bc84), so it runs
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
from docir.modules.agents.domain.targets import (
    AGENT_TARGETS,
    CLAUDE_FEEDBACK,
    DEFAULT_AGENTS,
)
from docir.modules.agents.infra.file_sink import FilesystemSink
from docir.modules.agents.infra.template_provider import PackagedTemplateProvider

#: Valid ``--agent`` names, for CLI validation / help.
AGENT_NAMES: tuple[str, ...] = tuple(AGENT_TARGETS)

#: The opt-in upstream-feedback skill (adr-7144cf291b1a). Exported because the
#: CLI *suggests* it in human output and must name it exactly; a literal in the
#: renderer would survive a rename of the target and print a command that fails.
FEEDBACK_AGENT: str = CLAUDE_FEEDBACK.name


def build_agent_service(version: str) -> AgentSetupService:
    """Wire the agent-setup service for one process (``version`` is stamped in)."""
    return AgentSetupService(PackagedTemplateProvider(), FilesystemSink(), version)


__all__ = [
    "AGENT_NAMES",
    "DEFAULT_AGENTS",
    "FEEDBACK_AGENT",
    "AgentSetupService",
    "InstallAction",
    "InstallRequest",
    "InstalledFile",
    "SetupResult",
    "UpdateRequest",
    "build_agent_service",
]
