"""The real :class:`TemplateProvider` — reads the skill template from the wheel.

The canonical instruction guide ships as ``templates/skill.md`` inside this
package and is loaded via ``importlib.resources`` so it resolves identically from
an editable checkout and from an installed wheel. This one packaged file is the
single source of truth for what every target embeds (see adr-3a2d5ee7bc84).
"""

from __future__ import annotations

from importlib import resources

_TEMPLATE_PACKAGE = "docir.modules.agents.infra.templates"
_TEMPLATE_NAME = "skill.md"


class PackagedTemplateProvider:
    """Serves the skill template bundled with the docir distribution."""

    def skill_template(self) -> str:
        resource = resources.files(_TEMPLATE_PACKAGE).joinpath(_TEMPLATE_NAME)
        return resource.read_text(encoding="utf-8")
