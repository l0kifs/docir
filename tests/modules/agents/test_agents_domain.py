"""Unit tests for the pure rendering/target primitives of the agents module."""

from __future__ import annotations

from docir.modules.agents.domain import rendering
from docir.modules.agents.domain.targets import AGENT_TARGETS, DEFAULT_AGENTS, AgentForm

TEMPLATE = "---\nname: docir\ndescription: drive docir\n---\n# docir — Agent Guide\n\nbody line\n"


class TestTargets:
    def test_two_targets_registered(self) -> None:
        assert set(AGENT_TARGETS) == {"claude", "agents"}
        assert DEFAULT_AGENTS == ("claude",)

    def test_forms_and_global_support(self) -> None:
        assert AGENT_TARGETS["claude"].form is AgentForm.SKILL
        assert AGENT_TARGETS["claude"].supports_global is True
        assert AGENT_TARGETS["agents"].form is AgentForm.EMBEDDED
        assert AGENT_TARGETS["agents"].supports_global is False


class TestStamp:
    def test_stamp_carries_version(self) -> None:
        assert "docir:v9.9.9" in rendering.stamp("9.9.9")

    def test_parse_version_round_trips(self) -> None:
        assert rendering.parse_version(rendering.stamp("1.2.3")) == "1.2.3"

    def test_parse_version_absent(self) -> None:
        assert rendering.parse_version("no stamp here") is None


class TestFrontmatter:
    def test_strip_removes_frontmatter(self) -> None:
        assert rendering.strip_frontmatter(TEMPLATE).startswith("# docir — Agent Guide")

    def test_strip_is_noop_without_frontmatter(self) -> None:
        text = "# just a heading\n"
        assert rendering.strip_frontmatter(text) == text


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


class TestBlockAndMerge:
    def test_render_block_wraps_body_without_frontmatter(self) -> None:
        block = rendering.render_block(TEMPLATE, "1.0.0")
        assert block.startswith(rendering.MARK_START)
        assert block.rstrip().endswith(rendering.MARK_END)
        assert "name: docir" not in block  # frontmatter stripped
        assert "body line" in block

    def test_merge_into_missing_file(self) -> None:
        block = rendering.render_block(TEMPLATE, "1.0.0")
        assert rendering.merge_block(None, block).strip() == block.strip()

    def test_merge_appends_to_foreign_file(self) -> None:
        block = rendering.render_block(TEMPLATE, "1.0.0")
        merged = rendering.merge_block("# Mine\n\nhouse rules\n", block)
        assert merged.startswith("# Mine")
        assert merged.count(rendering.MARK_START) == 1

    def test_merge_replaces_existing_block_preserving_surroundings(self) -> None:
        old = rendering.render_block(TEMPLATE, "1.0.0")
        existing = f"# Head\n\n{old}\n\n## Tail\n"
        new = rendering.render_block(TEMPLATE, "2.0.0")
        merged = rendering.merge_block(existing, new)
        assert merged.count(rendering.MARK_START) == 1  # replaced, not duplicated
        assert "# Head" in merged and "## Tail" in merged
        assert rendering.parse_version(merged) == "2.0.0"

    def test_has_block(self) -> None:
        assert rendering.has_block(rendering.render_block(TEMPLATE, "1.0.0"))
        assert not rendering.has_block("# nope")
