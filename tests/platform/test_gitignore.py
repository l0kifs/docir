"""The gitignore engine behind `code:` globs, measured against git itself.

docir parses `.gitignore` rather than shelling out to `git check-ignore`, and
for a reason (adr-1d1eddbb6fbd): check-ignore also answers with
`.git/info/exclude` and the user's global excludes, both per-machine, and a
digest that moves between colleagues is the defect this whole feature exists to
detect. The cost of that choice is that correctness is now docir's problem —
so these tests take their expected answers from git and not from a reading of
`gitignore(5)`.

`TestAgainstGitsOwnAnswers` runs git where it is installed. `TestTheRecordedTable`
carries the same verdicts as data, so the grammar stays pinned in an environment
that has no git — and the two disagreeing means one of them is wrong, which is
the point of keeping both.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from docir.platform.filesystem.gitignore import GitignoreIndex

#: ``(label, root .gitignore, {directory: its .gitignore}, {path: ignored?})``.
#: The verdicts were produced by ``git check-ignore -q <path>`` in a scratch
#: repository, one case per row — see the class docstring.
CASES: list[tuple[str, str, dict[str, str], dict[str, bool]]] = [
    (
        "the gitignore(5) worked examples",
        "*.log\n!important.log\nbuild/\n/root-only\n**/temp\ndoc/frotz/\n",
        {},
        {
            "a.log": True,
            "important.log": False,
            "a/b/important.log": False,
            "root-only": True,
            "a/root-only": False,
            "build/x": True,
            "a/build/z": True,
            "a/temp/y": True,
            "doc/frotz/z": True,
            "a/doc/frotz/w": False,
        },
    ),
    (
        "a negation cannot reach into an excluded directory",
        "bin/\n!src/bin/out.o\n",
        {},
        {"src/bin/out.o": True, "bin/x": True, "src/keep.py": False},
    ),
    (
        "a nested file overrides the one above it",
        "*.o\n",
        {"src": "!keep.o\n"},
        {"src/keep.o": False, "src/other.o": True, "a/keep.o": True},
    ),
    (
        "the build output of other languages",
        "obj/\ntarget/\ndist/\n",
        {},
        {"p/obj/a.dll": True, "target/x": True, "src/dist/y": True, "src/main.cs": False},
    ),
    (
        "** spans zero or more directories",
        "foo/**/bar\n",
        {},
        {"foo/bar": True, "foo/x/bar": True, "foo/x/y/bar": True, "a/foo/bar": False},
    ),
    (
        "a leading slash anchors",
        "/a/b\n",
        {},
        {"a/b": True, "x/a/b": False},
    ),
    (
        "character classes",
        "*.py[co]\n",
        {},
        {"m.pyc": True, "m.pyo": True, "m.pyx": False},
    ),
    (
        "comments and blank lines are not rules",
        "# a comment\n\n  \nsrc/*.tmp\n",
        {},
        {"src/a.tmp": True, "src/d/b.tmp": False},
    ),
    (
        "a bare name matches at any depth, file or directory",
        "node_modules\n",
        {},
        {"node_modules/x/y.js": True, "a/node_modules/z.js": True},
    ),
    (
        "the last matching rule in a file wins, not the first",
        "!*.keep\n*.bak\n",
        {},
        {"a.bak": True, "a.keep": False},
    ),
]


def _build(root: Path, ignore: str, nested: dict[str, str], paths: dict[str, bool]) -> None:
    (root / ".gitignore").write_text(ignore, encoding="utf-8")
    for directory, text in nested.items():
        (root / directory).mkdir(parents=True, exist_ok=True)
        (root / directory / ".gitignore").write_text(text, encoding="utf-8")
    for relative in paths:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x", encoding="utf-8")


@pytest.mark.parametrize(("label", "ignore", "nested", "paths"), CASES, ids=lambda c: None)
class TestTheRecordedTable:
    def test_every_path_gets_gits_answer(
        self, tmp_path: Path, label: str, ignore: str, nested: dict, paths: dict
    ) -> None:
        _build(tmp_path, ignore, nested, paths)
        index = GitignoreIndex(tmp_path)

        actual = {relative: index.ignores(tmp_path / relative) for relative in paths}

        # The whole mapping, not a count and not one path at a time: an engine
        # that ignores everything and one that ignores nothing each satisfy half
        # of any row taken alone.
        assert actual == paths, label


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git to compare against")
class TestAgainstGitsOwnAnswers:
    """The table above, re-derived rather than trusted.

    If `gitignore(5)` is read wrongly here, this fails and the table does not —
    the table would have been written from the same wrong reading.
    """

    @pytest.mark.parametrize(("label", "ignore", "nested", "paths"), CASES, ids=lambda c: None)
    def test_the_engine_agrees_with_check_ignore(
        self, tmp_path: Path, label: str, ignore: str, nested: dict, paths: dict
    ) -> None:
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
        _build(tmp_path, ignore, nested, paths)
        index = GitignoreIndex(tmp_path)

        theirs = {
            relative: subprocess.run(
                ["git", "-C", str(tmp_path), "check-ignore", "-q", relative], check=False
            ).returncode
            == 0
            for relative in paths
        }
        ours = {relative: index.ignores(tmp_path / relative) for relative in paths}

        assert ours == theirs, label
        # And the recorded table is what git actually said, so a future reader
        # can trust it in an environment with no git.
        assert theirs == paths, label


class TestTheEdgesGitIsNotAskedAbout:
    def test_a_path_outside_the_tree_has_no_opinion(self, tmp_path: Path) -> None:
        (tmp_path / "repo").mkdir()
        (tmp_path / "repo" / ".gitignore").write_text("*\n", encoding="utf-8")
        (tmp_path / "elsewhere.txt").write_text("x", encoding="utf-8")

        assert GitignoreIndex(tmp_path / "repo").ignores(tmp_path / "elsewhere.txt") is False

    def test_a_tree_with_no_ignore_file_excludes_nothing(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("x", encoding="utf-8")
        assert GitignoreIndex(tmp_path).ignores(tmp_path / "a.py") is False

    def test_an_unreadable_ignore_file_excludes_nothing(self, tmp_path: Path) -> None:
        # Failing to read a rule may only widen what gets hashed. The opposite —
        # treating the failure as "ignore it" — would silently stop watching
        # code, which is the one outcome this must never produce.
        (tmp_path / ".gitignore").mkdir()
        (tmp_path / "a.py").write_text("x", encoding="utf-8")

        assert GitignoreIndex(tmp_path).ignores(tmp_path / "a.py") is False

    def test_the_root_itself_is_never_ignored(self, tmp_path: Path) -> None:
        (tmp_path / ".gitignore").write_text("*\n", encoding="utf-8")
        assert GitignoreIndex(tmp_path).ignores(tmp_path) is False
