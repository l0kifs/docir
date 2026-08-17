"""The agent-setup use case — install / refresh AI-assistant instruction files.

``install`` writes the requested targets (default: the Claude skill). ``update``
auto-detects already-installed targets and refreshes them to the running docir
version, and can *add* a target passed explicitly via ``--agent``. Neither ever
clobbers foreign content: a skill file is entirely docir's, and an ``AGENTS.md``
is only touched inside docir's marker block (or appended to when explicitly
adding that target). See adr-3a2d5ee7bc84 and adr-6ed847e02fe5.

A pointer target drags in the skills it names (``points_to``) on both paths, so
the block can never name a file that was not written — including the case where
someone deletes the skill and keeps the block, which ``update`` heals.

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
        root = request.global_root if request.use_global else request.project_root
        names = {t.name for t in self._resolve(request.agents, use_global=request.use_global)}
        # Adding a skill beside an installed index makes that index wrong, so
        # refresh it in the same run rather than waiting for an `update`.
        names |= self._installed(root, use_global=request.use_global, form=AgentForm.POINTER)
        return self._emit(names, root, use_global=request.use_global)

    def update(self, request: UpdateRequest) -> SetupResult:
        # Explicitly-named additions are validated against ``--global`` up front;
        # auto-detected targets are simply skipped when they cannot go global.
        root = request.global_root if request.use_global else request.project_root
        names = {t.name for t in self._resolve(request.agents, use_global=request.use_global)}
        names |= self._installed(root, use_global=request.use_global)
        return self._emit(names, root, use_global=request.use_global)

    # -- internals ----------------------------------------------------------

    def _emit(self, names: set[str], root: Path, *, use_global: bool) -> SetupResult:
        """Write every named target under ``root``, skills before the index.

        Writing a pointer always writes the skills it names, so the index cannot
        link a file this run did not produce — including the case where someone
        deleted the skill and kept the block.
        """
        required = set(names)
        for name in names:
            required.update(AGENT_TARGETS[name].points_to)
        return SetupResult(
            files=tuple(
                self._write(target, root)
                for target in self._local_targets(use_global=use_global)
                if target.name in required
            )
        )

    def _installed(
        self, root: Path, *, use_global: bool, form: AgentForm | None = None
    ) -> set[str]:
        """Names of the targets already present under ``root``."""
        return {
            target.name
            for target in self._local_targets(use_global=use_global)
            if (form is None or target.form is form)
            and self._is_installed(target, self._sink.read(self._path(target, root)))
        }

    def _resolve(self, names: tuple[str, ...], *, use_global: bool) -> list[AgentTarget]:
        """Map ``--agent`` names to targets; reject unknowns, validate global.

        An unknown name used to be skipped silently, so `--agent claud` printed
        `[]`, exited 0 and wrote nothing — a once-per-repo onboarding command
        reporting success while doing nothing, leaving the user to believe their
        agent had been taught to drive docir. `docir init --profiles bogus`
        already raised and listed the valid names; this matches it.
        """
        unknown = sorted({name for name in names if name not in AGENT_TARGETS})
        if unknown:
            available = ", ".join(AGENT_TARGETS)
            raise AgentSetupError(
                f"unknown agent target(s): {', '.join(unknown)}; available: {available}"
            )
        for name in names:
            if use_global and not AGENT_TARGETS[name].supports_global:
                raise AgentSetupError(
                    f"target {name!r} has no global location; drop --global or drop --agent {name}"
                )
        return [target for target in AGENT_TARGETS.values() if target.name in set(names)]

    def _local_targets(self, *, use_global: bool) -> list[AgentTarget]:
        """Targets that can be written under the chosen root, in catalogue order."""
        return [
            target for target in AGENT_TARGETS.values() if target.supports_global or not use_global
        ]

    def _path(self, target: AgentTarget, root: Path) -> Path:
        return root.joinpath(*target.relative_path)

    def _is_installed(self, target: AgentTarget, existing: str | None) -> bool:
        if existing is None:
            return False
        if target.form is AgentForm.POINTER:
            # A foreign AGENTS.md (no docir markers) is not "installed" — leave it.
            return rendering.has_block(existing)
        return True

    def _write(self, target: AgentTarget, root: Path) -> InstalledFile:
        path = self._path(target, root)
        existing = self._sink.read(path)

        if target.form is AgentForm.SKILL:
            content = rendering.render_skill(self._template_of(target), self._version)
            action = InstallAction.UPDATED if existing is not None else InstallAction.CREATED
            note = None
        else:
            block = rendering.render_pointer(self._pointers(target, root), self._version)
            content = rendering.merge_block(existing, block)
            if existing is None:
                action, note = InstallAction.CREATED, None
            elif rendering.has_inlined_guide(existing):
                action, note = InstallAction.UPDATED, "inlined guide replaced by a link to it"
            elif rendering.has_block(existing):
                action, note = InstallAction.UPDATED, None
            else:
                action, note = InstallAction.UPDATED, "docir block appended to existing file"

        # The file is still written — the stamp records which build produced this
        # content, so skipping the write would leave `update` reporting the same
        # transition forever. What changes is the claim made about it.
        if existing is not None and rendering.differs_only_by_stamp(existing, content):
            action = InstallAction.UNCHANGED

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

    def _pointers(self, target: AgentTarget, root: Path) -> tuple[rendering.SkillPointer, ...]:
        """One entry per indexed skill — description verbatim, path linked.

        The index covers what ``target`` names *and* any other skill already
        installed under ``root``: an optional skill should show up in `AGENTS.md`
        once it exists, without the index dragging it in for everyone. Skills are
        written before the pointer in the same run, so one added now is on disk
        by the time this reads.
        """
        names = set(target.points_to) | self._installed(
            root, use_global=False, form=AgentForm.SKILL
        )
        pointers = []
        for skill in AGENT_TARGETS.values():
            if skill.name not in names:
                continue
            description = rendering.parse_description(self._template_of(skill))
            if description is None:
                raise AgentSetupError(
                    f"skill template for {skill.name!r} has no frontmatter 'description'"
                )
            pointers.append(rendering.SkillPointer(description=description, path=skill.posix_path))
        return tuple(pointers)

    def _template_of(self, target: AgentTarget) -> str:
        return self._templates.template(target.template)
