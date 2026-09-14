"""Tests for the real infra adapters — packaged template + filesystem sink."""

from __future__ import annotations

import re
from pathlib import Path

from docir.modules.agents.api import AGENT_NAMES, FEEDBACK_AGENT, build_agent_service
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
        assert set(AGENT_NAMES) == {"claude", "claude-writing", "claude-feedback", "agents"}

    def test_feedback_agent_names_a_real_target(self) -> None:
        # The CLI prints this name inside a command it tells a human to run.
        assert FEEDBACK_AGENT in AGENT_NAMES

    def test_build_and_install_end_to_end(self, tmp_path: Path) -> None:
        service = build_agent_service("3.1.4")
        service.install(InstallRequest(project_root=tmp_path, global_root=tmp_path / "home"))
        skill = tmp_path / ".claude" / "skills" / "docir" / "SKILL.md"
        assert skill.exists()
        assert "<!-- docir:v3.1.4" in skill.read_text(encoding="utf-8")


class TestFeedbackTemplate:
    """The packaged upstream-feedback skill (adr-7144cf291b1a).

    This template is the only one whose failure mode is other people's data and
    other people's inboxes, so its load-bearing sentences are asserted rather
    than trusted to survive an edit.
    """

    def _text(self) -> str:
        return PackagedTemplateProvider().template("feedback")[ENTRY_FILE]

    def test_it_is_a_loadable_skill(self) -> None:
        text = self._text()
        assert text.startswith("---\nname: docir-feedback")
        assert rendering.parse_description(text)

    def test_the_description_fires_before_the_workaround_is_written(self) -> None:
        """What this skill is *for*: it has to load while the agent is still
        deciding, not after the wrapper script exists. A description that only
        described reporting would arrive too late to prevent anything."""
        description = rendering.parse_description(self._text()) or ""
        assert "before you write a wrapper script" in description

    def test_it_names_the_workaround_signals(self) -> None:
        text = self._text()
        for signal in ("wrapper", "CLAUDE.md", "pinning an older docir", "second source of truth"):
            assert signal in text, f"the workaround signal {signal!r} is no longer named"

    def test_it_reproduces_away_from_the_user_corpus(self) -> None:
        text = self._text()
        assert "scratch store" in text
        assert "mktemp" in text
        assert "never on this corpus" in text.lower()

    def test_it_unblocks_the_user_before_it_prohibits_anything(self) -> None:
        """Measured, not guessed: with the skill loaded, Sonnet refused the task in
        3 of 3 runs — "I won't hand you a wrapper script or project rule" — where its
        baseline diagnosed the bug and offered a way forward. The permission existed,
        eight paragraphs below seven prohibitions, and the model kept the prohibition.
        So the grant has to come first, in the section's own heading.
        """
        text = self._text()
        section = text.split("## Unblock them first, then report it")[1]
        grant = section.index("Give the user the working answer")
        first_prohibition = section.index("What you must not do")
        assert grant < first_prohibition, "the prohibition leads again; the refusal returns"

    def test_the_gates_do_not_gate_helping(self) -> None:
        """The other half of the same refusal: "Pass all four or stop" read as a gate
        on answering at all, so a run with no shell stopped instead of handing over
        what it had."""
        section = self._text().split("## Four gates")[1].split("\n1. ")[0]
        assert "never gate the answer you owe the user" in section
        assert "hand over" in section

    def test_the_disclosure_sits_inside_the_body_the_agent_copies(self) -> None:
        """It landed in roughly one run in three when it was only a separate section:
        the model reproduces the fenced skeleton, so the line has to be in it."""
        skeleton = self._text().split("````markdown")[1].split("````")[0]
        assert "Drafted by an AI coding agent" in skeleton

    def test_the_scratch_recipe_never_runs_init(self) -> None:
        """Found by following the skill instead of re-reading it (adr-7d9fbbf976e8).

        The recipe opened with `docir init .`, and running it from a repo root
        resolves against the *current directory*: the "throwaway store" step
        re-initialized the user's own store. The store is created by the first
        write, so the line was never needed either.
        """
        block = self._text().split("## Reproduce on a scratch store")[1].split("```bash")[1]
        block = block.split("```")[0]
        assert "docir init" not in block, "the scratch recipe would touch the real store"
        assert "DOCIR_HOME" in block and "mktemp" in block

    def test_the_draft_location_comes_from_a_command_that_answers_when_empty(self) -> None:
        """The second one the walkthrough caught: the skill said to read the
        store path from the `store` field of any reply, and a query matching
        nothing returns `[]` — no path, and no way for the agent to recover
        one. `docir doctor` reports `store.home` in an empty store."""
        section = self._text().split("## Draft the file")[1].split("## Redact")[0]
        assert "docir doctor" in section
        assert "store.home" in section

    def test_it_never_files_by_itself(self) -> None:
        """Draft-only is the decision; the agent prints a command, the human runs it."""
        text = self._text()
        assert "**The human runs that command.**" in text
        assert "no edit to the title or body after their approval" in text

    def test_it_carries_the_redaction_checklist_and_the_disclosure(self) -> None:
        text = self._text()
        assert "## Redact before you hand it over" in text
        assert "Drafted by an AI coding agent" in text

    def test_it_routes_a_vulnerability_away_from_a_public_issue(self) -> None:
        text = self._text()
        assert "never a public issue" in text


class TestDefaultSkillPushesBack:
    def test_troubleshooting_points_at_the_optional_feedback_skill(self) -> None:
        """The counter-pressure has to reach repos that never install it.

        Without this line an agent in a default install meets a docir defect
        with no instruction but its own judgement, which is what produces the
        silent workaround in the first place.
        """
        files = PackagedTemplateProvider().template("skill")
        text = files["reference/troubleshooting.md"]
        assert "docir agent install --agent claude-feedback" in text
        assert "do not route around it" in text
