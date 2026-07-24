"""The agent-setup use case — install / refresh AI-assistant instruction files.

``install`` writes the requested targets (default: the Claude skill). ``update``
auto-detects already-installed targets and refreshes them to the running docir
version, and can *add* a target passed explicitly via ``--agent``. Neither ever
clobbers foreign content: a skill file is entirely docir's, and an ``AGENTS.md``
is only touched inside docir's marker block (or appended to when explicitly
adding that target). See ADR-0008.

The service is pure orchestration over two ports (a template source and a file
sink) plus an injected version string, so it is fully testable in memory.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from docir.modules.agents.application.ports import FileSink, TemplateProvider
from docir.modules.agents.domain import rendering
from docir.modules.agents.domain.results import InstallAction, InstalledFile
from docir.modules.agents.domain.targets import (
    AGENT_TARGETS,
    DEFAULT_AGENTS,
    AgentForm,
    AgentTarget,
)
from docir.platform.errors import AgentSetupError


@dataclass(frozen=True)
class InstallRequest:
    """Where and what ``docir agent install`` should write."""

    project_root: Path
    global_root: Path
    agents: tuple[str, ...] = DEFAULT_AGENTS
    use_global: bool = False


@dataclass(frozen=True)
class UpdateRequest:
    """Refresh installed targets under one root; ``agents`` names targets to add."""

    project_root: Path
    global_root: Path
    agents: tuple[str, ...] = ()
    use_global: bool = False


@dataclass(frozen=True)
class SetupResult:
    """Everything one install/update touched."""

    files: tuple[InstalledFile, ...]


class AgentSetupService:
    """Installs and refreshes docir's AI-assistant instruction files."""

    def __init__(self, templates: TemplateProvider, sink: FileSink, version: str) -> None:
        self._templates = templates
        self._sink = sink
        self._version = version

    def install(self, request: InstallRequest) -> SetupResult:
        targets = self._resolve(request.agents, use_global=request.use_global)
        root = request.global_root if request.use_global else request.project_root
        files = [self._write(target, self._path(target, root)) for target in targets]
        return SetupResult(files=tuple(files))

    def update(self, request: UpdateRequest) -> SetupResult:
        # Explicitly-named additions are validated against ``--global`` up front;
        # auto-detected targets are simply skipped when they cannot go global.
        additions = self._resolve(request.agents, use_global=request.use_global)
        add_names = {target.name for target in additions}
        root = request.global_root if request.use_global else request.project_root

        files: list[InstalledFile] = []
        for target in AGENT_TARGETS.values():
            if request.use_global and not target.supports_global:
                continue
            path = self._path(target, root)
            existing = self._sink.read(path)
            if self._is_installed(target, existing) or target.name in add_names:
                files.append(self._write(target, path, existing))
        return SetupResult(files=tuple(files))

    # -- internals ----------------------------------------------------------

    def _resolve(self, names: tuple[str, ...], *, use_global: bool) -> list[AgentTarget]:
        """Map ``--agent`` names to targets, ignoring unknowns, validating global."""
        resolved: list[AgentTarget] = []
        seen: set[str] = set()
        for name in names:
            target = AGENT_TARGETS.get(name)
            if target is None or target.name in seen:
                continue
            if use_global and not target.supports_global:
                raise AgentSetupError(
                    f"target {name!r} has no global location; drop --global or drop --agent {name}"
                )
            resolved.append(target)
            seen.add(target.name)
        return resolved

    def _path(self, target: AgentTarget, root: Path) -> Path:
        return root.joinpath(*target.relative_path)

    def _is_installed(self, target: AgentTarget, existing: str | None) -> bool:
        if existing is None:
            return False
        if target.form is AgentForm.EMBEDDED:
            # A foreign AGENTS.md (no docir markers) is not "installed" — leave it.
            return rendering.has_block(existing)
        return True

    def _write(self, target: AgentTarget, path: Path, existing: str | None = None) -> InstalledFile:
        if existing is None:
            existing = self._sink.read(path)
        template = self._templates.skill_template()

        if target.form is AgentForm.SKILL:
            content = rendering.render_skill(template, self._version)
            action = InstallAction.UPDATED if existing is not None else InstallAction.CREATED
            note = None
        else:
            block = rendering.render_block(template, self._version)
            content = rendering.merge_block(existing, block)
            if existing is None:
                action, note = InstallAction.CREATED, None
            elif rendering.has_block(existing):
                action, note = InstallAction.UPDATED, None
            else:
                action, note = InstallAction.UPDATED, "docir block appended to existing file"

        previous = rendering.parse_version(existing) if existing is not None else None
        self._sink.write(path, content)
        return InstalledFile(
            target=target.name,
            path=str(path),
            action=action,
            previous_version=previous,
            new_version=self._version,
            note=note,
        )
