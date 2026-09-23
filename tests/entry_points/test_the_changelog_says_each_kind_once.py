"""Every released section of `CHANGELOG.md` names each kind of change once.

`[Unreleased]` accumulates one `### Added` / `### Fixed` group per merged change —
that is the working convention, and the release commit is where they are
consolidated. Nothing used to check that the consolidation happened, so 0.29.0
shipped with four `### Added` blocks and three `### Fixed`, and 0.10.0 had been
carrying the same defect since August. Both were found by a person reading the
file, which is the detection method this replaces.

Scoped to duplicates and nothing else. Heading *order* is deliberately not
checked: 0.28.0 puts `Fixed` before `Changed`, and several releases lead with
`Upgrade notes`, because the section is written to be read top to bottom rather
than to match a fixed list. The vocabulary is not checked either — `Measured and
rejected` and `Internal` are real sections this project writes.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parents[2] / "CHANGELOG.md"

#: The one section allowed to repeat a heading. It is the staging area: a change
#: appends its own group, and the release that ships them merges them. Failing
#: here would make every second merged PR red, which is how a guard gets deleted.
STAGING = "## [Unreleased]"


def _parse(text: str) -> dict[str, list[str]]:
    """Each `## ...` section, and the `### ...` headings under it."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line.strip()
            sections[current] = []
        elif line.startswith("### ") and current is not None:
            sections[current].append(line.strip())
    return sections


def _duplicates(text: str) -> dict[str, list[str]]:
    """The rule: which released sections name a kind twice, and which kinds.

    Takes text rather than reading the file, so the `[Unreleased]` exemption can
    be exercised against a section that actually repeats a heading. Reading the
    real changelog cannot do it — the staging section is empty right after a
    release, and an exemption nothing reaches is an exemption nobody can delete
    safely.
    """
    offenders = {
        name: sorted(head for head, count in Counter(heads).items() if count > 1)
        for name, heads in _parse(text).items()
        if name != STAGING
    }
    return {name: dupes for name, dupes in offenders.items() if dupes}


def _sections() -> dict[str, list[str]]:
    return _parse(CHANGELOG.read_text(encoding="utf-8"))


def test_the_changelog_has_sections_to_check() -> None:
    # A count cannot tell "nothing is duplicated" from "nothing was parsed", and
    # the test below is exactly the shape that goes quiet on its own: rename the
    # heading level and it passes forever on an empty mapping.
    sections = _sections()
    assert len(sections) > 20, sections.keys()
    assert STAGING in sections
    assert any(name.startswith("## [0.29.0]") for name in sections)
    assert sum(len(heads) for heads in sections.values()) > 50


#: A changelog shaped like the defect: both sections repeat a heading, and only
#: one of them is allowed to.
SYNTHETIC = """\
# Changelog

## [Unreleased]

### Added

- something

### Added

- something else

## [9.9.9] - 2026-01-01

### Fixed

- one thing

### Fixed

- another thing
"""


def test_the_staging_section_may_repeat_a_kind_and_a_release_may_not() -> None:
    assert _duplicates(SYNTHETIC) == {"## [9.9.9] - 2026-01-01": ["### Fixed"]}


def test_no_released_section_names_a_kind_twice() -> None:
    offenders = _duplicates(CHANGELOG.read_text(encoding="utf-8"))

    # Which sections and which headings, not how many: the fix is to merge the
    # named blocks, and a bare count sends the reader back to scan the file.
    assert offenders == {}, (
        "a release section repeats a heading — merge the blocks into one "
        f"(the `[Unreleased]` staging section is exempt): {offenders}"
    )
