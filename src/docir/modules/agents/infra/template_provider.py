"""The real :class:`TemplateProvider` — reads instruction templates from the wheel.

Each skill ships as the *directory* ``templates/<name>/`` inside this package —
``SKILL.md`` plus whatever reference files it links to — and is loaded via
``importlib.resources`` so it resolves identically from an editable checkout and
from an installed wheel. These packaged files are the single source of truth for
what every target installs (adr-3a2d5ee7bc84): ``skill/`` is the CLI guide,
``writing/`` the documentation-writing rules (adr-735ba7f6209b).

It is a directory rather than a single file because the CLI guide outgrew what an
assistant loads eagerly (adr-e18250eb3081): the entry point stays small and links to the rest, which
costs nothing until read. Only ``.md`` files are served — the installed skill is
swept against exactly this listing, so anything else here would be written on
every install and is better added deliberately than by dropping a file in.

Names come from the static target catalogue, never from user input, so an
unknown one is a packaging mistake rather than a runtime condition — it surfaces
as the underlying read error, and the suite loads every catalogue target's
template to catch it before release. Whether what came back is a *usable* skill
is the service's question, not this adapter's: reading files is all this does,
and `agents.infra` is a leaf that may not reach the error taxonomy.
"""

from __future__ import annotations

from importlib import resources
from importlib.resources.abc import Traversable

_TEMPLATE_PACKAGE = "docir.modules.agents.infra.templates"


class PackagedTemplateProvider:
    """Serves the instruction templates bundled with the docir distribution."""

    def template(self, name: str) -> dict[str, str]:
        root = resources.files(_TEMPLATE_PACKAGE).joinpath(name)
        return dict(self._collect(root, prefix=""))

    def _collect(self, node: Traversable, *, prefix: str) -> list[tuple[str, str]]:
        """Every ``.md`` under ``node``, keyed by its path relative to the root."""
        found: list[tuple[str, str]] = []
        for child in node.iterdir():
            # Always ``/``: the key becomes a path in the installed tree and a
            # link inside the rendered markdown, both read on every OS.
            key = f"{prefix}{child.name}"
            if child.is_dir():
                found.extend(self._collect(child, prefix=f"{key}/"))
            elif child.name.endswith(".md"):
                found.append((key, child.read_text(encoding="utf-8")))
        return sorted(found)
