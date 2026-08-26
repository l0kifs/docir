"""Every `.claude/rules/*.md` must actually load, and be reachable from CLAUDE.md.

CLAUDE.md used to carry the argument behind each invariant inline, at ~21k
tokens a session. It now keeps one imperative line per invariant and defers the
rest to `.claude/rules/`, where a file enters context only when Claude Code
reads a source file its `paths:` frontmatter matches.

That trade buys context and creates one failure mode it did not have before: a
rule reaches its reader through a glob, and a glob that matches nothing fails
*silently*. Nothing errors, nothing warns — the file sits in the tree, reads as
governing the code, and never loads. The invariant it carries then exists only
as the one-liner in CLAUDE.md, which is deliberately not enough to argue with.

So both directions are checked. A pattern must match a real file, or the rule is
unreachable from the code. A rule must be linked from CLAUDE.md, or the code is
unreachable from the rule: an agent planning a change reads the root file first,
and an invariant with no line there is one nothing stops it from breaking.

The `paths:` globs are evaluated the way Claude Code evaluates them, not the way
`pathlib` does. `Path.glob` on Python 3.12 yields *directories* for a trailing
`**`, so `src/docir/modules/agents/**` looks like a hit for a directory that
holds no files, and would look like one for a directory that no longer exists at
all had it not been deleted. `_matches` normalises the pattern and requires a
file, which is what the rule's reader needs.
"""

from __future__ import annotations

import pathlib
import re

import pytest
import yaml

_REPO = pathlib.Path(__file__).resolve().parents[2]
_RULES = _REPO / ".claude" / "rules"

#: Frontmatter is the whole contract: no `---` block, no `paths:`, and the rule
#: loads at launch like CLAUDE.md itself — the cost the split exists to avoid,
#: paid silently by a file that looks scoped.
_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def _rule_files() -> list[pathlib.Path]:
    assert _RULES.is_dir(), (
        f"{_RULES} is missing — CLAUDE.md links into it and keeps only one line "
        "per invariant, so an absent directory is most of this repo's working "
        "instructions gone, not a tidy-up"
    )
    return sorted(_RULES.rglob("*.md"))


RULE_FILES = _rule_files()


def _frontmatter_problem(rule: pathlib.Path) -> str | None:
    """Why ``rule`` would load unscoped, or ``None`` if it is scoped properly."""
    match = _FRONTMATTER.match(rule.read_text(encoding="utf-8"))
    if not match:
        return "no `---` frontmatter block"
    try:
        front = yaml.safe_load(match.group(1))
    except yaml.YAMLError as error:
        return f"frontmatter is not valid YAML: {error}"
    if not isinstance(front, dict):
        return f"frontmatter is {type(front).__name__}, not a map"
    declared = front.get("paths")
    if not isinstance(declared, list) or not declared:
        return f"declares `paths: {declared!r}`, not a non-empty list"
    return None


def _declared_paths(rule: pathlib.Path) -> list[str]:
    """The `paths:` list, empty when the file does not have a usable one.

    Deliberately total rather than asserting: this runs at collection time to
    build the parametrization below, and a raise here is a *collection error* —
    it takes out every case in this file and names none of them, so a single
    mistyped rule hides the state of the other fifteen. The problem is reported
    by `test_every_rule_is_scoped_by_paths`, one case per file, and the sweep
    guard catches the case where every file fails at once.
    """
    if _frontmatter_problem(rule):
        return []
    match = _FRONTMATTER.match(rule.read_text(encoding="utf-8"))
    assert match  # _frontmatter_problem returned None, so the block parsed
    return [str(entry) for entry in yaml.safe_load(match.group(1))["paths"]]


RULE_PATTERNS = [(rule.name, pattern) for rule in RULE_FILES for pattern in _declared_paths(rule)]


def _matches(pattern: str) -> list[pathlib.Path]:
    """Files under the repo matching ``pattern``, by Claude Code's reading of it.

    A trailing `**` means "everything below here" to the matcher that loads these
    rules; to `Path.glob` it means the directories below here and nothing else.
    Expanding it is what keeps a pattern over an emptied directory from passing.
    """
    expanded = f"{pattern}/*" if pattern.endswith("/**") else pattern
    return [path for path in _REPO.glob(expanded) if path.is_file()]


def test_the_sweep_found_the_rules() -> None:
    """A guard on the guard: an empty list would pass every case below."""
    assert len(RULE_FILES) > 10, f"only {len(RULE_FILES)} rule files found — is the path right?"
    assert len(RULE_PATTERNS) > 30, f"only {len(RULE_PATTERNS)} patterns read from them"


def test_the_matcher_expands_a_trailing_globstar() -> None:
    """The `pathlib` quirk this file exists to work around, pinned directly.

    Without the expansion `_matches` returns directories and the assertion below
    passes on a pattern that reaches no file — the exact silence being guarded.
    """
    assert not [path for path in _REPO.glob("src/docir/modules/agents/**") if path.is_file()]
    assert _matches("src/docir/modules/agents/**")


@pytest.mark.parametrize("rule", RULE_FILES, ids=lambda rule: rule.name)
def test_every_rule_is_scoped_by_paths(rule: pathlib.Path) -> None:
    """No `paths:`, no scoping — the rule loads at launch like CLAUDE.md itself.

    That is the cost the split exists to avoid, and it is paid silently: the file
    still governs the right code and still reads as scoped.
    """
    problem = _frontmatter_problem(rule)
    assert not problem, (
        f"{rule.name} {problem} — a rule without a `paths:` list loads into every "
        "session unconditionally, which is the bloat this directory undoes"
    )


@pytest.mark.parametrize(("rule", "pattern"), RULE_PATTERNS, ids=lambda value: value)
def test_every_declared_path_reaches_a_file(rule: str, pattern: str) -> None:
    """A glob that matches nothing is a rule nobody will ever be shown."""
    assert _matches(pattern), (
        f"{rule} declares `{pattern}`, which matches no file. The rule loads when "
        "Claude Code reads a file this pattern matches, so nothing will load it — "
        "fix the pattern, or drop it if the code it named is gone."
    )


@pytest.mark.parametrize("rule", [rule.name for rule in RULE_FILES], ids=lambda value: value)
def test_every_rule_is_linked_from_claude_md(rule: str) -> None:
    """The root file is what an agent reads *before* it opens anything.

    A rule reached only by its `paths:` arrives after the file is open, which is
    after an approach has been chosen. The one-line summary in CLAUDE.md is what
    stops the wrong one, so a rule with no line there is half-installed.
    """
    root = (_REPO / "CLAUDE.md").read_text(encoding="utf-8")
    assert f".claude/rules/{rule}" in root, (
        f"{rule} is not linked from CLAUDE.md — no summary there means the "
        "invariant only reaches a reader who already opened the code"
    )


def test_claude_md_links_no_rule_that_is_gone() -> None:
    """The other direction: a renamed rule leaves a link that reads as live."""
    root = (_REPO / "CLAUDE.md").read_text(encoding="utf-8")
    linked = set(re.findall(r"\.claude/rules/([a-z0-9-]+\.md)", root))
    assert linked, "no rule links found in CLAUDE.md — did the link format change?"
    on_disk = {rule.name for rule in RULE_FILES}
    assert linked <= on_disk, sorted(linked - on_disk)
