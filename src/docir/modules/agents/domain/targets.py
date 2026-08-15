"""The catalogue of AI-assistant instruction targets docir can install.

A *target* is one place an AI coding assistant reads its instructions from, plus
the *form* those instructions take there. docir ships three — two skills and the
index that lists them (adr-3a2d5ee7bc84, adr-735ba7f6209b):

- ``claude`` — a standalone Claude Code *skill* file the assistant auto-loads by
  its frontmatter ``description``. Installable per-project or globally.
- ``claude-writing`` — a second skill, opt-in, covering how to write the
  documents rather than how to drive the CLI (adr-735ba7f6209b).
- ``agents`` — a marker-delimited block merged into the cross-assistant
  ``AGENTS.md`` convention at the repo root. Project-only (no global equivalent).

The ``agents`` block **points at** the skills instead of inlining them: it
carries each skill's description verbatim plus the repo-relative path to the
file. So ``points_to`` is both the pointer's floor and its dependency —
selecting ``agents`` installs the skill it names, because a pointer to a file
that was never written is worse than no pointer at all. Skills installed *beside*
those are indexed too, without being dragged in; that is the application
service's job, since only it can see what is on disk.

Everything here is pure data: which file, in which form, from which template,
what it points at, and whether a global install location exists. The *rendering*
of each form lives in :mod:`docir.modules.agents.domain.rendering`; the *choice*
of what to write lives in the application service.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class AgentForm(enum.Enum):
    """How a target's instructions are materialised on disk."""

    #: A standalone file that is entirely docir's (frontmatter + body); always
    #: rewritten wholesale on install/update.
    SKILL = "skill"
    #: A marker-delimited block, merged into a file that may hold other content,
    #: that *refers* to the skill files rather than restating them; only docir's
    #: block is replaced, the rest is preserved.
    POINTER = "pointer"


@dataclass(frozen=True)
class AgentTarget:
    """One installable instruction location."""

    #: Stable target name selected on the CLI via ``--agent``.
    name: str
    #: How the instructions are written (a whole file vs. a pointer block).
    form: AgentForm
    #: Path components relative to the install root (project root or home).
    relative_path: tuple[str, ...]
    #: Whether a ``--global`` (``~/``-rooted) install location exists.
    supports_global: bool
    #: For a skill: which packaged template it installs (``<stem>.md``). Read
    #: only for :data:`AgentForm.SKILL`; a pointer renders from what it names.
    template: str = ""
    #: For a pointer: the ``SKILL``-form targets it always names, which installing
    #: this target therefore also writes. Empty for a skill.
    points_to: tuple[str, ...] = ()

    @property
    def posix_path(self) -> str:
        """The install-root-relative path, always ``/``-separated.

        A pointer block naming this file is committed and read on every OS, so
        the separator is part of the content and cannot come from ``os.sep``.
        """
        return "/".join(self.relative_path)


CLAUDE = AgentTarget(
    name="claude",
    form=AgentForm.SKILL,
    relative_path=(".claude", "skills", "docir", "SKILL.md"),
    supports_global=True,
    template="skill",
)
CLAUDE_WRITING = AgentTarget(
    name="claude-writing",
    form=AgentForm.SKILL,
    relative_path=(".claude", "skills", "docir-writing", "SKILL.md"),
    supports_global=True,
    template="writing",
)
AGENTS = AgentTarget(
    name="agents",
    form=AgentForm.POINTER,
    relative_path=("AGENTS.md",),
    supports_global=False,
    points_to=(CLAUDE.name,),
)

#: Every target docir knows how to install, keyed by ``--agent`` name. Order is
#: install order: skills before the pointer that indexes them.
AGENT_TARGETS: dict[str, AgentTarget] = {
    target.name: target for target in (CLAUDE, CLAUDE_WRITING, AGENTS)
}

#: What ``docir agent install`` writes when no ``--agent`` is given. The writing
#: skill is deliberately absent: both skills match on the same work, so a repo
#: that does not want the second one should not pay its context on every session.
DEFAULT_AGENTS: tuple[str, ...] = (CLAUDE.name,)
