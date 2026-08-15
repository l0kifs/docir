"""The real :class:`TemplateProvider` — reads instruction templates from the wheel.

Each skill ships as ``templates/<name>.md`` inside this package and is loaded via
``importlib.resources`` so it resolves identically from an editable checkout and
from an installed wheel. These packaged files are the single source of truth for
what every target installs (adr-3a2d5ee7bc84): ``skill.md`` is the CLI guide,
``writing.md`` the documentation-writing rules (adr-735ba7f6209b).

Names come from the static target catalogue, never from user input, so an
unknown one is a packaging mistake rather than a runtime condition — it surfaces
as the underlying read error, and the suite loads every catalogue target's
template to catch it before release.
"""

from __future__ import annotations

from importlib import resources

_TEMPLATE_PACKAGE = "docir.modules.agents.infra.templates"


class PackagedTemplateProvider:
    """Serves the instruction templates bundled with the docir distribution."""

    def template(self, name: str) -> str:
        resource = resources.files(_TEMPLATE_PACKAGE).joinpath(f"{name}.md")
        return resource.read_text(encoding="utf-8")
