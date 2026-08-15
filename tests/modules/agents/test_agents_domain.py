"""Unit tests for the pure rendering/target primitives of the agents module."""

from __future__ import annotations

import pytest

from docir.modules.agents.domain import rendering
from docir.modules.agents.domain.targets import AGENT_TARGETS, DEFAULT_AGENTS, AgentForm

TEMPLATE = "---\nname: docir\ndescription: drive docir\n---\n# docir — Agent Guide\n\nbody line\n"

SKILL_PATH = ".claude/skills/docir/SKILL.md"
POINTERS = (rendering.SkillPointer(description="drive docir", path=SKILL_PATH),)


class TestTargets:
    def test_the_registered_targets(self) -> None:
        assert set(AGENT_TARGETS) == {"claude", "claude-writing", "agents"}
        assert DEFAULT_AGENTS == ("claude",)

    def test_skills_come_before_the_index_that_lists_them(self) -> None:
        # Catalogue order is install order: the pointer reads what is on disk,
        # so a skill written in the same run has to be written first.
        names = list(AGENT_TARGETS)
        assert names.index("agents") == len(names) - 1

    def test_forms_and_global_support(self) -> None:
        assert AGENT_TARGETS["claude"].form is AgentForm.SKILL
        assert AGENT_TARGETS["claude"].supports_global is True
        assert AGENT_TARGETS["claude-writing"].form is AgentForm.SKILL
        assert AGENT_TARGETS["claude-writing"].supports_global is True
        assert AGENT_TARGETS["agents"].form is AgentForm.POINTER
        assert AGENT_TARGETS["agents"].supports_global is False

    def test_each_skill_names_a_distinct_template_and_path(self) -> None:
        skills = [t for t in AGENT_TARGETS.values() if t.form is AgentForm.SKILL]
        assert len({t.template for t in skills}) == len(skills)
        assert len({t.posix_path for t in skills}) == len(skills)

    def test_the_pointer_names_the_skill_it_depends_on(self) -> None:
        # points_to is both the block's content and the install dependency
        # (adr-6ed847e02fe5) — they cannot drift because there is one field.
        assert AGENT_TARGETS["agents"].points_to == ("claude",)
        assert AGENT_TARGETS["claude"].points_to == ()

    def test_posix_path_never_uses_the_os_separator(self) -> None:
        # The block is committed and read on Windows too, so the separator is
        # content, not a local detail.
        assert AGENT_TARGETS["claude"].posix_path == ".claude/skills/docir/SKILL.md"


class TestStamp:
    def test_stamp_carries_version(self) -> None:
        assert "docir:v9.9.9" in rendering.stamp("9.9.9")

    def test_parse_version_round_trips(self) -> None:
        assert rendering.parse_version(rendering.stamp("1.2.3")) == "1.2.3"

    def test_parse_version_absent(self) -> None:
        assert rendering.parse_version("no stamp here") is None


class TestParseDescription:
    def test_lifts_the_description(self) -> None:
        assert rendering.parse_description(TEMPLATE) == "drive docir"

    def test_folded_scalar_is_joined_into_one_line(self) -> None:
        # A list item cannot hold a newline, so continuation lines must collapse.
        template = "---\nname: d\ndescription: first\n  second\n---\nbody\n"
        assert rendering.parse_description(template) == "first second"

    def test_quotes_are_stripped(self) -> None:
        template = '---\nname: d\ndescription: "quoted"\n---\nbody\n'
        assert rendering.parse_description(template) == "quoted"

    def test_body_description_is_not_mistaken_for_frontmatter(self) -> None:
        # Only the frontmatter is searched: prose starting with `description:`
        # would otherwise become the pointer's text.
        template = "---\nname: d\ndescription: real\n---\ndescription: prose\n"
        assert rendering.parse_description(template) == "real"

    @pytest.mark.parametrize(
        "template",
        ["# no frontmatter\n", "---\nname: d\n---\nbody\n", "---\nname: d\ndescription:\n---\nb\n"],
    )
    def test_a_template_without_one_reports_absence(self, template: str) -> None:
        # Absence, not an empty string — the application layer is what refuses to
        # render a pointer that never says when to open the file it names.
        assert rendering.parse_description(template) is None


class TestRenderSkill:
    def test_stamp_inserted_after_frontmatter(self) -> None:
        out = rendering.render_skill(TEMPLATE, "1.0.0")
        # Frontmatter still opens the file (skill loader needs it), stamp follows.
        assert out.startswith("---\nname: docir")
        head, _, _ = out.partition("# docir — Agent Guide")
        assert "<!-- docir:v1.0.0" in head
        assert rendering.parse_version(out) == "1.0.0"

    def test_stamp_prepended_when_no_frontmatter(self) -> None:
        out = rendering.render_skill("# bare\n", "2.0.0")
        assert out.startswith("<!-- docir:v2.0.0")


class TestRenderPointer:
    def test_carries_the_description_and_a_link_but_not_the_guide(self) -> None:
        # The whole point of adr-6ed847e02fe5: AGENTS.md refers to the skill
        # instead of holding a second copy of it.
        block = rendering.render_pointer(POINTERS, "1.0.0")
        assert block.startswith(rendering.MARK_START)
        assert block.rstrip().endswith(rendering.MARK_END)
        assert "drive docir" in block
        assert "(.claude/skills/docir/SKILL.md)" in block
        assert "body line" not in block
        assert "name: docir" not in block

    def test_one_entry_per_skill(self) -> None:
        # A second skill adds a line, not another copy of a guide.
        pointers = (*POINTERS, rendering.SkillPointer("write well", ".claude/skills/w/SKILL.md"))
        block = rendering.render_pointer(pointers, "1.0.0")
        assert block.count("\n- [") == 2
        assert "write well" in block

    def test_stays_short_regardless_of_template_size(self) -> None:
        # Guards the regression this change exists to prevent: the block used to
        # grow with the guide, so a 500-line template meant a 500-line AGENTS.md.
        assert len(rendering.render_pointer(POINTERS, "1.0.0").splitlines()) < 15


class TestBlockAndMerge:
    def test_merge_into_missing_file(self) -> None:
        block = rendering.render_pointer(POINTERS, "1.0.0")
        assert rendering.merge_block(None, block).strip() == block.strip()

    def test_merge_appends_to_foreign_file(self) -> None:
        block = rendering.render_pointer(POINTERS, "1.0.0")
        merged = rendering.merge_block("# Mine\n\nhouse rules\n", block)
        assert merged.startswith("# Mine")
        assert merged.count(rendering.MARK_START) == 1

    def test_merge_replaces_existing_block_preserving_surroundings(self) -> None:
        old = rendering.render_pointer(POINTERS, "1.0.0")
        existing = f"# Head\n\n{old}\n\n## Tail\n"
        new = rendering.render_pointer(POINTERS, "2.0.0")
        merged = rendering.merge_block(existing, new)
        assert merged.count(rendering.MARK_START) == 1  # replaced, not duplicated
        assert "# Head" in merged and "## Tail" in merged
        assert rendering.parse_version(merged) == "2.0.0"

    def test_has_block(self) -> None:
        assert rendering.has_block(rendering.render_pointer(POINTERS, "1.0.0"))
        assert not rendering.has_block("# nope")


class TestHasInlinedGuide:
    #: What ``render_block`` produced before the pointer form — the shape on disk
    #: in every repo that installed the ``agents`` target before this release.
    LEGACY = (
        f"{rendering.MARK_START}\n{rendering.stamp('0.9.0')}\n\n"
        f"# docir — Agent Guide\n\nbody line\n{rendering.MARK_END}"
    )

    def test_detects_a_block_written_before_the_pointer_form(self) -> None:
        assert rendering.has_inlined_guide(self.LEGACY)

    def test_a_pointer_block_is_not_one(self) -> None:
        assert not rendering.has_inlined_guide(rendering.render_pointer(POINTERS, "1.0.0"))

    def test_no_block_at_all_is_not_one(self) -> None:
        assert not rendering.has_inlined_guide("# Mine only\n")

    def test_foreign_content_around_a_pointer_block_is_ignored(self) -> None:
        # Keyed on the marker inside the block, so a house-rules file that
        # happens to mention the guide is not misread as legacy.
        block = rendering.render_pointer(POINTERS, "1.0.0")
        assert not rendering.has_inlined_guide(f"# docir — Agent Guide\n\n{block}\n")
