"""The catalogue of AI-assistant instruction targets docir can install.

A *target* is one place an AI coding assistant reads its instructions from, plus
the *form* those instructions take there. docir ships exactly two — mirroring the
smallest proven surface (see ADR-0008):

- ``claude`` — a standalone Claude Code *skill* file the assistant auto-loads by
  its frontmatter ``description``. Installable per-project or globally.
- ``agents`` — a marker-delimited block merged into the cross-assistant
  ``AGENTS.md`` convention at the repo root. Project-only (no global equivalent).

Everything here is pure data: which file, in which form, and whether a global
install location exists. The *rendering* of each form lives in
:mod:`docir.modules.agents.domain.rendering`; the *choice* of what to write lives
in the application service.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class AgentForm(enum.Enum):
    """How a target's instructions are materialised on disk."""

    #: A standalone file that is entirely docir's (frontmatter + body); always
    #: rewritten wholesale on install/update.
    SKILL = "skill"
    #: A marker-delimited block merged into a file that may hold other content;
    #: only docir's block is replaced, the rest is preserved.
    EMBEDDED = "embedded"


@dataclass(frozen=True)
class AgentTarget:
    """One installable instruction location."""

    #: Stable target name selected on the CLI via ``--agent``.
    name: str
    #: How the instructions are written (a whole file vs. an embedded block).
    form: AgentForm
    #: Path components relative to the install root (project root or home).
    relative_path: tuple[str, ...]
    #: Whether a ``--global`` (``~/``-rooted) install location exists.
    supports_global: bool


CLAUDE = AgentTarget(
    name="claude",
    form=AgentForm.SKILL,
    relative_path=(".claude", "skills", "docir", "SKILL.md"),
    supports_global=True,
)
AGENTS = AgentTarget(
    name="agents",
    form=AgentForm.EMBEDDED,
    relative_path=("AGENTS.md",),
    supports_global=False,
)

#: Every target docir knows how to install, keyed by ``--agent`` name.
AGENT_TARGETS: dict[str, AgentTarget] = {target.name: target for target in (CLAUDE, AGENTS)}

#: What ``docir agent install`` writes when no ``--agent`` is given.
DEFAULT_AGENTS: tuple[str, ...] = (CLAUDE.name,)
