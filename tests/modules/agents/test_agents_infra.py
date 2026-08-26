"""Tests for the real infra adapters — packaged template + filesystem sink."""

from __future__ import annotations

import re
from pathlib import Path

from docir.modules.agents.api import AGENT_NAMES, build_agent_service
from docir.modules.agents.application.ports import ENTRY_FILE
from docir.modules.agents.application.service import InstallRequest
from docir.modules.agents.domain import rendering
from docir.modules.agents.domain.targets import AGENT_TARGETS, AgentForm
from docir.modules.agents.infra.file_sink import FilesystemSink
from docir.modules.agents.infra.template_provider import PackagedTemplateProvider

#: Anthropic's skill-authoring guidance: keep the eagerly-loaded body under 500
#: lines and split the rest into files that cost nothing until read. The guide
#: was 764 lines when it was one file, which is what forced the directory shape —
#: so this is the number the split exists to hold, not a style preference.
MAX_ENTRY_LINES = 500


class TestPackagedTemplate:
    def test_ships_the_guide_with_frontmatter(self) -> None:
        files = PackagedTemplateProvider().template("skill")
        text = files[ENTRY_FILE]
        assert text.startswith("---")
        assert "name: docir" in text
        assert "# docir — Agent Guide" in text

    def test_ships_the_reference_files_the_guide_links(self) -> None:
        """The entry point is an index; a link it cannot resolve teaches nothing.

        Asserts the *names*, not a count: a template directory that shipped zero
        reference files would satisfy "every link resolves" vacuously, which is
        indistinguishable from a wheel that dropped its data files.
        """
        files = PackagedTemplateProvider().template("skill")
        linked = set(re.findall(r"\(([\w./-]+\.md)\)", files[ENTRY_FILE]))
        assert linked, f"{ENTRY_FILE} links no reference file — it is not an index"
        assert linked <= set(files), f"links nothing shipped: {sorted(linked - set(files))}"

    def test_the_entry_point_stays_small_enough_to_load_eagerly(self) -> None:
        files = PackagedTemplateProvider().template("skill")
        lines = len(files[ENTRY_FILE].splitlines())
        assert lines <= MAX_ENTRY_LINES, (
            f"{ENTRY_FILE} is {lines} lines; move a section into reference/ instead"
        )

    def test_reference_files_are_one_level_deep(self) -> None:
        """A reference reached only through another reference is read partially.

        Claude previews a nested file (`head -100`) rather than reading it whole,
        so every reference file must be reachable straight from the entry point.
        """
        files = PackagedTemplateProvider().template("skill")
        entry_links = set(re.findall(r"\(([\w./-]+\.md)\)", files[ENTRY_FILE]))
        unreachable = sorted(set(files) - entry_links - {ENTRY_FILE})
        assert not unreachable, f"not linked from {ENTRY_FILE}: {unreachable}"

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
            text = provider.template(skill.template)[ENTRY_FILE]
            assert text.startswith("---"), f"{skill.name}: template has no frontmatter"
            assert rendering.parse_description(text), f"{skill.name}: template has no description"

    def test_the_provider_only_reads(self) -> None:
        """It serves what is there; whether that is a usable skill is the service's call.

        `agents.infra` is a leaf and may not reach the error taxonomy, so a
        directory with no entry point comes back as its files, not as a raise.
        """
        assert ENTRY_FILE not in PackagedTemplateProvider().template("skill/reference")


class TestFilesystemSink:
    def test_read_missing_returns_none(self, tmp_path: Path) -> None:
        assert FilesystemSink().read(tmp_path / "nope.md") is None

    def test_write_creates_parents_and_round_trips(self, tmp_path: Path) -> None:
        sink = FilesystemSink()
        path = tmp_path / "a" / "b" / "c.md"
        sink.write(path, "hello")
        assert sink.read(path) == "hello"

    def test_markdown_files_walks_subdirectories_and_ignores_the_rest(self, tmp_path: Path) -> None:
        sink = FilesystemSink()
        sink.write(tmp_path / "SKILL.md", "a")
        sink.write(tmp_path / "reference" / "schema.md", "b")
        sink.write(tmp_path / "scripts" / "tool.py", "c")
        assert sink.markdown_files(tmp_path) == (
            tmp_path / "SKILL.md",
            tmp_path / "reference" / "schema.md",
        )

    def test_markdown_files_of_a_missing_directory_is_empty(self, tmp_path: Path) -> None:
        assert FilesystemSink().markdown_files(tmp_path / "nope") == ()

    def test_remove_prunes_the_directory_it_empties_but_no_further(self, tmp_path: Path) -> None:
        sink = FilesystemSink()
        sink.write(tmp_path / "reference" / "gone.md", "x")
        sink.remove(tmp_path / "reference" / "gone.md")
        assert not (tmp_path / "reference").exists()
        assert tmp_path.exists(), "pruning walked out of the tree it was given"

    def test_remove_keeps_a_directory_that_still_holds_something(self, tmp_path: Path) -> None:
        sink = FilesystemSink()
        sink.write(tmp_path / "reference" / "gone.md", "x")
        sink.write(tmp_path / "reference" / "stays.md", "y")
        sink.remove(tmp_path / "reference" / "gone.md")
        assert (tmp_path / "reference" / "stays.md").exists()

    def test_remove_of_a_missing_file_is_success(self, tmp_path: Path) -> None:
        FilesystemSink().remove(tmp_path / "never-existed.md")


class TestApiBuilder:
    def test_agent_names(self) -> None:
        assert set(AGENT_NAMES) == {"claude", "claude-writing", "agents"}

    def test_build_and_install_end_to_end(self, tmp_path: Path) -> None:
        service = build_agent_service("3.1.4")
        service.install(InstallRequest(project_root=tmp_path, global_root=tmp_path / "home"))
        skill = tmp_path / ".claude" / "skills" / "docir" / "SKILL.md"
        assert skill.exists()
        assert "<!-- docir:v3.1.4" in skill.read_text(encoding="utf-8")
