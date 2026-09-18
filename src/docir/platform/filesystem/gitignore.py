"""What the repository's own ``.gitignore`` files exclude.

Used by :class:`~docir.platform.filesystem.code_matcher.RepositoryCodeMatcher`
so a ``code:`` glob fingerprints the code somebody wrote rather than whatever a
build left beside it. The repository has already stated which files those are,
in the one place every teammate shares.

**Only the ``.gitignore`` files in the tree.** Not ``.git/info/exclude`` and not
the user's global ``core.excludesFile``, both of which are per-machine — and a
digest that depends on the machine is the defect the skip set in
``code_matcher`` was written to avoid, arriving through a wider door
(issue-ec3819b1f13c). It is also why this reads the files itself rather than
asking ``git check-ignore``, which would answer with all three and needs a
``.git`` directory besides.

The grammar is ``gitignore(5)``: ``!`` negates, a trailing ``/`` means
directories only, a ``/`` anywhere else anchors the pattern to the file's own
directory, ``*`` and ``?`` stop at a separator, ``**`` spans them, and within
one file the *last* matching rule decides. Between files the *deepest* one
does.

**A path is judged by its ancestors first**, which is the rule that is easy to
miss and the one git is most often quoted on: a file under an excluded directory
stays excluded, and a later ``!`` naming it cannot bring it back, because git
never descends into the directory to read the rule. ``bin/`` plus
``!src/bin/out.o`` leaves ``src/bin/out.o`` ignored — verified against
``git check-ignore`` rather than reasoned about, and pinned by a test that
carries the same table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_IGNORE_FILE = ".gitignore"

#: A line ending in an odd number of backslashes escapes the whitespace after
#: it. Git strips unescaped trailing whitespace, which is what makes
#: ``build/ `` and ``build/`` the same rule and ``build/\ `` a different one.
_TRAILING_SPACE = re.compile(r"(?<!\\)\s+$")


@dataclass(frozen=True, slots=True)
class _Rule:
    """One pattern line, compiled."""

    matcher: re.Pattern[str]
    negated: bool
    dir_only: bool


class GitignoreIndex:
    """Answers "would git ignore this path", for one working tree.

    Built per matcher and thrown away with it. Ignore files are parsed on first
    use and every verdict about a *directory* is cached, because `check`
    fingerprints many files under the same few directories and the ancestor walk
    would otherwise re-answer the same question once per file.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        #: Directory -> the rules its own ``.gitignore`` declares. An empty
        #: tuple is a cached answer ("no file, or nothing in it"), not a miss.
        self._rules: dict[Path, tuple[_Rule, ...]] = {}
        #: Directory -> the (base, rules) chain that applies inside it, deepest
        #: first. Derived from ``_rules``; cached because the per-path question
        #: needs the chain, not one file.
        self._chains: dict[Path, tuple[tuple[Path, tuple[_Rule, ...]], ...]] = {}
        #: Directory -> is it excluded, ancestors included. The cache that makes
        #: the ancestor walk cost one lookup per file instead of one per level.
        self._directories: dict[Path, bool] = {}

    def ignores(self, path: Path) -> bool:
        """Whether the repository's ignore files exclude ``path``.

        A path outside the tree is not ignored: the caller resolved it against
        this root, so one that escapes is a question about somebody else's
        repository and the honest answer is "no opinion".
        """
        if path != self._root and self._root not in path.parents:
            return False
        if path == self._root:
            return False
        if self._directory_excluded(path.parent):
            return True
        return self._verdict(path, path.is_dir()) is True

    def _directory_excluded(self, directory: Path) -> bool:
        """Whether ``directory`` or any directory above it is excluded."""
        if directory == self._root or self._root not in directory.parents:
            return False
        cached = self._directories.get(directory)
        if cached is not None:
            return cached
        excluded = self._directory_excluded(directory.parent) or (
            self._verdict(directory, True) is True
        )
        self._directories[directory] = excluded
        return excluded

    def _verdict(self, path: Path, is_dir: bool) -> bool | None:
        """``True`` excluded, ``False`` re-included, ``None`` no rule applies.

        The deepest ignore file with an opinion wins; inside one file the last
        matching rule does. Both are git's, and both matter: the first is what
        makes a nested file able to override, the second is what makes ``!``
        mean anything at all.
        """
        for base, rules in self._chain_for(path.parent):
            relative = path.relative_to(base).as_posix()
            verdict: bool | None = None
            for rule in rules:
                if rule.dir_only and not is_dir:
                    continue
                if rule.matcher.fullmatch(relative):
                    verdict = not rule.negated
            if verdict is not None:
                return verdict
        return None

    def _chain_for(self, directory: Path) -> tuple[tuple[Path, tuple[_Rule, ...]], ...]:
        """The ignore files that apply inside ``directory``, deepest first."""
        cached = self._chains.get(directory)
        if cached is not None:
            return cached
        chain: list[tuple[Path, tuple[_Rule, ...]]] = []
        current = directory
        while True:
            rules = self._rules_at(current)
            if rules:
                chain.append((current, rules))
            if current == self._root or self._root not in current.parents:
                break
            current = current.parent
        resolved = tuple(chain)
        self._chains[directory] = resolved
        return resolved

    def _rules_at(self, directory: Path) -> tuple[_Rule, ...]:
        """The rules ``directory``'s own ``.gitignore`` declares, if it has one."""
        cached = self._rules.get(directory)
        if cached is not None:
            return cached
        try:
            text = (directory / _IGNORE_FILE).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # Absent is the ordinary case. Unreadable or not text is treated the
            # same on purpose: this decides what to *exclude*, so failing to
            # read a rule can only widen what is hashed, never narrow it.
            text = ""
        rules = tuple(rule for rule in map(_parse, text.splitlines()) if rule is not None)
        self._rules[directory] = rules
        return rules


def _parse(line: str) -> _Rule | None:
    """One ``.gitignore`` line as a rule, or ``None`` for a blank or comment."""
    line = _TRAILING_SPACE.sub("", line)
    if not line or line.startswith("#"):
        # `\#` is the escape for a literal one; only an unescaped `#` comments.
        return None
    negated = line.startswith("!")
    if negated or line.startswith("\\"):
        line = line[1:]
    if not line:
        return None
    dir_only = line.endswith("/")
    if dir_only:
        line = line[:-1]
    if not line:
        return None
    # "A slash at the beginning or middle makes the pattern relative to this
    # file's directory; otherwise it matches at any depth." The trailing one is
    # already gone, so any slash left is such a slash.
    anchored = "/" in line
    if line.startswith("/"):
        line = line[1:]
    body = _translate(line)
    prefix = "" if anchored else "(?:[^/]+/)*"
    return _Rule(matcher=re.compile(prefix + body), negated=negated, dir_only=dir_only)


def _translate(pattern: str) -> str:
    """A gitignore pattern as a regex over a ``/``-joined relative path."""
    segments = pattern.split("/")
    parts: list[str] = []
    separator = ""
    ends_open = False
    for index, segment in enumerate(segments):
        if segment == "**":
            if index == len(segments) - 1:
                # A trailing `**` covers everything inside what came before it.
                ends_open = True
            else:
                # Zero or more directories, so `a/**/b` still matches `a/b`.
                separator = "/(?:[^/]+/)*" if parts else "(?:[^/]+/)*"
            continue
        parts.append(separator + _translate_segment(segment))
        separator = "/"
    body = "".join(parts)
    if ends_open:
        return f"{body}/.*" if body else ".*"
    return body


def _translate_segment(segment: str) -> str:
    """One path segment of a pattern as a regex fragment; ``/`` never matches."""
    out: list[str] = []
    index = 0
    while index < len(segment):
        char = segment[index]
        if char == "\\" and index + 1 < len(segment):
            index += 1
            out.append(re.escape(segment[index]))
        elif char == "*":
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        elif char == "[":
            closing = segment.find("]", index + 1)
            if closing == -1:
                # An unclosed class is a literal '[', which is what git and
                # `fnmatch` both do. A pattern is user text; it must not raise.
                out.append(re.escape(char))
            else:
                body = segment[index + 1 : closing]
                if body.startswith(("!", "^")):
                    body = "^" + body[1:]
                out.append(f"[{body}]")
                index = closing
        else:
            out.append(re.escape(char))
        index += 1
    return "".join(out)
