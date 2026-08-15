"""The ports the agent-setup use case depends on — a template source and a sink.

Both are trivially fakeable so the service is testable without touching disk or
the packaged wheel. The infra layer supplies the real implementations
(:mod:`docir.modules.agents.infra`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class TemplateProvider(Protocol):
    """Yields the instruction templates shipped with docir, by name."""

    def template(self, name: str) -> str:
        """Return the raw template ``name`` (frontmatter + body), verbatim."""
        ...


class FileSink(Protocol):
    """Reads and writes instruction files in the target tree."""

    def read(self, path: Path) -> str | None:
        """Return the file's text, or ``None`` if it does not exist."""
        ...

    def write(self, path: Path, content: str) -> None:
        """Write ``content`` to ``path``, creating parent directories."""
        ...
