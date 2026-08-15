"""Application-level tests for :class:`AgentSetupService` with in-memory ports."""

from __future__ import annotations

from pathlib import Path

import pytest

from docir.modules.agents.application.service import (
    AgentSetupService,
    InstallRequest,
    SetupResult,
    UpdateRequest,
)
from docir.modules.agents.domain.results import InstallAction, InstalledFile
from docir.platform.errors import AgentSetupError

TEMPLATE = "---\nname: docir\ndescription: drive docir\n---\n# docir — Agent Guide\n\nbody line\n"
WRITING = "---\nname: w\ndescription: write well\n---\n# docir — Writing Rules\n\nrule line\n"
TEMPLATES = {"skill": TEMPLATE, "writing": WRITING}

PROJECT = Path("/proj")
HOME = Path("/home")
SKILL_PATH = PROJECT / ".claude" / "skills" / "docir" / "SKILL.md"
WRITING_PATH = PROJECT / ".claude" / "skills" / "docir-writing" / "SKILL.md"
GLOBAL_SKILL_PATH = HOME / ".claude" / "skills" / "docir" / "SKILL.md"
AGENTS_PATH = PROJECT / "AGENTS.md"


class FakeTemplates:
    def template(self, name: str) -> str:
        return TEMPLATES[name]


class FakeSink:
    def __init__(self) -> None:
        self.files: dict[Path, str] = {}

    def read(self, path: Path) -> str | None:
        return self.files.get(path)

    def write(self, path: Path, content: str) -> None:
        self.files[path] = content


def make(
    version: str = "1.0.0", sink: FakeSink | None = None
) -> tuple[AgentSetupService, FakeSink]:
    sink = sink or FakeSink()
    return AgentSetupService(FakeTemplates(), sink, version), sink


def install_req(**kw: object) -> InstallRequest:
    return InstallRequest(project_root=PROJECT, global_root=HOME, **kw)  # type: ignore[arg-type]


def update_req(**kw: object) -> UpdateRequest:
    return UpdateRequest(project_root=PROJECT, global_root=HOME, **kw)  # type: ignore[arg-type]


def by_target(result: SetupResult) -> dict[str, InstalledFile]:
    return {file.target: file for file in result.files}


#: An ``AGENTS.md`` block in the pre-pointer shape — the guide inlined, no
#: ``docir:pointer`` marker. This is what is on disk in repos that installed the
#: ``agents`` target before adr-6ed847e02fe5.
LEGACY_AGENTS_MD = (
    "<!-- docir:start -->\n"
    "<!-- docir:v0.9.0 — generated file, do not edit by hand; "
    "refresh with `docir agent update` after upgrading docir -->\n\n"
    "# docir — Agent Guide\n\nbody line\n"
    "<!-- docir:end -->\n"
)


class TestInstall:
    def test_default_installs_claude_skill(self) -> None:
        svc, sink = make()
        result = svc.install(install_req())
        assert [f.target for f in result.files] == ["claude"]
        file = result.files[0]
        assert file.action is InstallAction.CREATED
        assert file.previous_version is None
        assert file.new_version == "1.0.0"
        assert sink.files[SKILL_PATH].startswith("---\nname: docir")
        assert "<!-- docir:v1.0.0" in sink.files[SKILL_PATH]

    def test_reinstall_marks_updated_and_reads_previous_version(self) -> None:
        svc, sink = make("1.0.0")
        svc.install(install_req())
        svc2, _ = make("2.0.0", sink=sink)
        result = svc2.install(install_req())
        assert result.files[0].action is InstallAction.UPDATED
        assert result.files[0].previous_version == "1.0.0"
        assert "<!-- docir:v2.0.0" in sink.files[SKILL_PATH]

    def test_global_installs_under_home(self) -> None:
        svc, sink = make()
        svc.install(install_req(agents=("claude",), use_global=True))
        assert GLOBAL_SKILL_PATH in sink.files
        assert SKILL_PATH not in sink.files

    def test_install_agents_creates_marker_block(self) -> None:
        svc, sink = make()
        result = svc.install(install_req(agents=("agents",)))
        content = sink.files[AGENTS_PATH]
        assert content.startswith("<!-- docir:start -->")
        assert "<!-- docir:end -->" in content
        assert by_target(result)["agents"].action is InstallAction.CREATED

    def test_install_agents_also_writes_the_skill_it_points_at(self) -> None:
        # adr-6ed847e02fe5: the block names a file, so the file has to exist.
        # Before this, `--agent agents` wrote a block and no skill at all.
        svc, sink = make()
        result = svc.install(install_req(agents=("agents",)))
        assert [f.target for f in result.files] == ["claude", "agents"]
        assert SKILL_PATH in sink.files

    def test_the_block_links_the_skill_instead_of_inlining_it(self) -> None:
        svc, sink = make()
        svc.install(install_req(agents=("agents",)))
        block = sink.files[AGENTS_PATH]
        assert "(.claude/skills/docir/SKILL.md)" in block
        assert "drive docir" in block  # the skill's description, verbatim
        assert "body line" not in block  # ...but not its body

    def test_install_agents_preserves_foreign_content(self) -> None:
        svc, sink = make()
        sink.files[AGENTS_PATH] = "# Mine\n\nhouse rules\n"
        result = svc.install(install_req(agents=("agents",)))
        content = sink.files[AGENTS_PATH]
        assert content.startswith("# Mine")
        assert content.count("<!-- docir:start -->") == 1
        assert by_target(result)["agents"].note is not None

    def test_reinstall_agents_replaces_block_not_duplicates(self) -> None:
        svc, sink = make("1.0.0")
        svc.install(install_req(agents=("agents",)))
        svc2, _ = make("2.0.0", sink=sink)
        result = svc2.install(install_req(agents=("agents",)))
        assert sink.files[AGENTS_PATH].count("<!-- docir:start -->") == 1
        assert by_target(result)["agents"].action is InstallAction.UPDATED
        assert by_target(result)["agents"].previous_version == "1.0.0"

    def test_global_agents_is_rejected(self) -> None:
        svc, _ = make()
        with pytest.raises(AgentSetupError):
            svc.install(install_req(agents=("agents",), use_global=True))

    def test_the_writing_skill_is_opt_in(self) -> None:
        # Both skills match the same work, so a repo that did not ask for the
        # second one must not pay its context on every session.
        svc, sink = make()
        assert [f.target for f in svc.install(install_req()).files] == ["claude"]
        assert WRITING_PATH not in sink.files

    def test_installing_the_writing_skill_writes_its_own_template(self) -> None:
        svc, sink = make()
        result = svc.install(install_req(agents=("claude-writing",)))
        assert [f.target for f in result.files] == ["claude-writing"]
        # Its own template, not the CLI guide — the catalogue is keyed per skill.
        assert "# docir — Writing Rules" in sink.files[WRITING_PATH]
        assert SKILL_PATH not in sink.files

    def test_the_index_lists_both_skills_once_both_are_installed(self) -> None:
        svc, sink = make()
        svc.install(install_req(agents=("claude-writing", "agents")))
        block = sink.files[AGENTS_PATH]
        assert "write well" in block and "drive docir" in block
        assert block.count("\n- [") == 2

    def test_adding_a_skill_refreshes_an_installed_index(self) -> None:
        # An index that silently stops listing everything installed is worse
        # than no index: it reads as complete.
        svc, sink = make()
        svc.install(install_req(agents=("agents",)))
        assert "write well" not in sink.files[AGENTS_PATH]
        result = svc.install(install_req(agents=("claude-writing",)))
        # `claude` rides along because writing the index writes what it names.
        assert set(by_target(result)) == {"claude", "claude-writing", "agents"}
        assert "write well" in sink.files[AGENTS_PATH]

    def test_the_index_does_not_drag_in_the_optional_skill(self) -> None:
        svc, sink = make()
        svc.install(install_req(agents=("agents",)))
        assert WRITING_PATH not in sink.files
        assert sink.files[AGENTS_PATH].count("\n- [") == 1

    def test_a_template_without_a_description_is_refused(self) -> None:
        # The pointer's whole content is the description; rendering the block
        # without one would name a file and never say when to open it.
        class Broken:
            def template(self, name: str) -> str:
                return "# no frontmatter\n"

        svc = AgentSetupService(Broken(), FakeSink(), "1.0.0")
        with pytest.raises(AgentSetupError):
            svc.install(install_req(agents=("agents",)))

    def test_unknown_agent_is_rejected(self) -> None:
        """Guards issue-b8220546282c — and this test asserted the opposite.

        `--agent claud` was silently skipped: `[]`, exit 0, nothing written. A
        once-per-repo onboarding command reported success while doing nothing,
        leaving the user believing their agent had been taught to drive docir.
        `docir init --profiles bogus` two files away already raised and listed
        the valid names.

        The old test was named `test_unknown_agent_is_ignored` and asserted the
        empty result, so the suite could never have caught this — the same trap
        as issue-9cb85759076d, issue-40d1792bc9f9 and issue-87a27629f6a6.
        """
        svc, _ = make()
        with pytest.raises(AgentSetupError):
            svc.install(install_req(agents=("bogus",)))

    def test_the_error_lists_the_valid_targets(self) -> None:
        # A typo is the likely cause, so the message has to show the choices.
        svc, _ = make()
        with pytest.raises(AgentSetupError) as excinfo:
            svc.install(install_req(agents=("claud",)))
        message = str(excinfo.value)
        assert "claud" in message and "claude" in message and "agents" in message

    def test_update_rejects_an_unknown_agent_too(self) -> None:
        # `update` resolves through the same path; a typo there would otherwise
        # silently refresh nothing and report success.
        svc, _ = make()
        with pytest.raises(AgentSetupError):
            svc.update(update_req(agents=("bogus",)))

    def test_duplicate_agent_is_collapsed(self) -> None:
        svc, _ = make()
        result = svc.install(install_req(agents=("claude", "claude")))
        assert len(result.files) == 1

    def test_install_both_targets(self) -> None:
        svc, sink = make()
        result = svc.install(install_req(agents=("claude", "agents")))
        assert {f.target for f in result.files} == {"claude", "agents"}
        assert SKILL_PATH in sink.files and AGENTS_PATH in sink.files


class TestUpdate:
    def test_refreshes_installed_skill_and_reports_transition(self) -> None:
        svc, sink = make("1.0.0")
        svc.install(install_req())
        svc2, _ = make("2.0.0", sink=sink)
        result = svc2.update(update_req())
        by_target = {f.target: f for f in result.files}
        assert by_target["claude"].previous_version == "1.0.0"
        assert by_target["claude"].new_version == "2.0.0"

    def test_nothing_installed_is_a_noop(self) -> None:
        svc, _ = make()
        assert svc.update(update_req()).files == ()

    def test_does_not_touch_foreign_agents_md(self) -> None:
        svc, sink = make("2.0.0")
        sink.files[AGENTS_PATH] = "# Mine only\n"
        result = svc.update(update_req())
        assert "agents" not in {f.target for f in result.files}
        assert sink.files[AGENTS_PATH] == "# Mine only\n"

    def test_refreshes_installed_agents_block(self) -> None:
        svc, sink = make("1.0.0")
        svc.install(install_req(agents=("agents",)))
        svc2, _ = make("2.0.0", sink=sink)
        result = svc2.update(update_req())
        by_target = {f.target: f for f in result.files}
        assert by_target["agents"].previous_version == "1.0.0"
        assert sink.files[AGENTS_PATH].count("<!-- docir:start -->") == 1

    def test_rewrites_a_skill_deleted_from_under_its_pointer(self) -> None:
        # The block names the file, so an update that refreshed only the block
        # would leave AGENTS.md pointing at nothing and report success.
        svc, sink = make("1.0.0")
        svc.install(install_req(agents=("agents",)))
        del sink.files[SKILL_PATH]
        svc2, _ = make("2.0.0", sink=sink)
        result = svc2.update(update_req())
        assert set(by_target(result)) == {"claude", "agents"}
        assert SKILL_PATH in sink.files

    def test_migrates_a_legacy_inlined_block_and_says_so(self) -> None:
        # An update that silently drops ~500 lines from a tracked file is a
        # surprising diff; the note is what explains it (adr-6ed847e02fe5).
        svc, sink = make("2.0.0")
        sink.files[AGENTS_PATH] = LEGACY_AGENTS_MD
        result = svc.update(update_req())
        agents = by_target(result)["agents"]
        assert agents.previous_version == "0.9.0"
        assert agents.note == "inlined guide replaced by a link to it"
        assert "body line" not in sink.files[AGENTS_PATH]
        assert "(.claude/skills/docir/SKILL.md)" in sink.files[AGENTS_PATH]

    def test_a_refreshed_pointer_block_carries_no_migration_note(self) -> None:
        svc, sink = make("1.0.0")
        svc.install(install_req(agents=("agents",)))
        svc2, _ = make("2.0.0", sink=sink)
        assert by_target(svc2.update(update_req()))["agents"].note is None

    def test_can_add_a_new_target(self) -> None:
        svc, sink = make("1.0.0")
        svc.install(install_req())  # only claude
        svc2, _ = make("2.0.0", sink=sink)
        result = svc2.update(update_req(agents=("agents",)))
        assert "agents" in {f.target for f in result.files}
        assert AGENTS_PATH in sink.files

    def test_global_agents_is_rejected(self) -> None:
        svc, _ = make()
        with pytest.raises(AgentSetupError):
            svc.update(update_req(agents=("agents",), use_global=True))

    def test_global_update_refreshes_only_global_skill(self) -> None:
        svc, sink = make("1.0.0")
        svc.install(install_req(agents=("claude",), use_global=True))
        svc2, _ = make("2.0.0", sink=sink)
        result = svc2.update(update_req(use_global=True))
        assert [f.target for f in result.files] == ["claude"]
        assert "<!-- docir:v2.0.0" in sink.files[GLOBAL_SKILL_PATH]
