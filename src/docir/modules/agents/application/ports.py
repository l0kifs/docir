"""The ports the agent-setup use case depends on — a template source and a sink.

Both are trivially fakeable so the service is testable without touching disk or
the packaged wheel. The infra layer supplies the real implementations
(:mod:`docir.modules.agents.infra`).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

#: The file a skill's directory is entered through — the one an assistant loads
#: by its frontmatter, and the only file a skill is guaranteed to have. It lives
#: beside the port rather than in ``domain`` because it *is* the port's contract:
#: the key :meth:`TemplateProvider.template` must return. That also keeps the
#: adapter implementing it off ``agents.domain``, which the module boundary
#: forbids (adr-e18250eb3081).
ENTRY_FILE = "SKILL.md"


class TemplateProvider(Protocol):
    """Yields the instruction templates shipped with docir, by name."""

    def template(self, name: str) -> Mapping[str, str]:
        """Return every file of skill ``name``, verbatim.

        Keyed by ``/``-separated path relative to the skill's own directory, so
        the entry point is :data:`ENTRY_FILE` and a bundled reference is e.g.
        ``reference/schema.md``. A skill is a
        directory rather than a file because one file cannot both stay under the
        size an assistant loads eagerly and carry everything docir can do.
        """
        ...


class FileSink(Protocol):
    """Reads and writes instruction files in the target tree."""

    def read(self, path: Path) -> str | None:
        """Return the file's text, or ``None`` if it does not exist."""
        ...

    def write(self, path: Path, content: str) -> None:
        """Write ``content`` to ``path``, creating parent directories."""
        ...

    def markdown_files(self, directory: Path) -> tuple[Path, ...]:
        """Every ``.md`` file under ``directory``, recursively; empty if absent.

        The input to the sweep: an install compares this against what it wrote.
        """
        ...

    def remove(self, path: Path) -> None:
        """Delete ``path``, and its parent directory if that leaves it empty.

        Missing is success — the caller is asserting the file should not exist,
        not that it did. The parent is pruned one level only, which is enough to
        clear a ``reference/`` a release emptied without ever walking upwards out
        of the tree the caller named.
        """
        ...
