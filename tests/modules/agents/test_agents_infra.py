"""Tests for the real infra adapters — packaged template + filesystem sink."""

from __future__ import annotations

from pathlib import Path

from docir.modules.agents.api import AGENT_NAMES, build_agent_service
from docir.modules.agents.application.service import InstallRequest
from docir.modules.agents.domain import rendering
from docir.modules.agents.domain.targets import AGENT_TARGETS, AgentForm
from docir.modules.agents.infra.file_sink import FilesystemSink
from docir.modules.agents.infra.template_provider import PackagedTemplateProvider


class TestPackagedTemplate:
    def test_ships_the_guide_with_frontmatter(self) -> None:
        text = PackagedTemplateProvider().template("skill")
        assert text.startswith("---")
        assert "name: docir" in text
        assert "# docir — Agent Guide" in text

    def test_every_catalogue_skill_has_a_packaged_template(self) -> None:
        """A target naming a template that never shipped fails only on install.

        Names come from the static catalogue, so this is a packaging mistake
        rather than a runtime condition — which means the suite is the only
        place it can be caught before a user hits it.
        """
        provider = PackagedTemplateProvider()
        skills = [t for t in AGENT_TARGETS.values() if t.form is AgentForm.SKILL]
        assert skills, "no skills in the catalogue — the sweep is checking nothing"
        for skill in skills:
            text = provider.template(skill.template)
            assert text.startswith("---"), f"{skill.name}: template has no frontmatter"
            assert rendering.parse_description(text), f"{skill.name}: template has no description"


class TestFilesystemSink:
    def test_read_missing_returns_none(self, tmp_path: Path) -> None:
        assert FilesystemSink().read(tmp_path / "nope.md") is None

    def test_write_creates_parents_and_round_trips(self, tmp_path: Path) -> None:
        sink = FilesystemSink()
        path = tmp_path / "a" / "b" / "c.md"
        sink.write(path, "hello")
        assert sink.read(path) == "hello"


class TestApiBuilder:
    def test_agent_names(self) -> None:
        assert set(AGENT_NAMES) == {"claude", "claude-writing", "agents"}

    def test_build_and_install_end_to_end(self, tmp_path: Path) -> None:
        service = build_agent_service("3.1.4")
        service.install(InstallRequest(project_root=tmp_path, global_root=tmp_path / "home"))
        skill = tmp_path / ".claude" / "skills" / "docir" / "SKILL.md"
        assert skill.exists()
        assert "<!-- docir:v3.1.4" in skill.read_text(encoding="utf-8")
