"""Resolving ``code`` globs against the repository (implements ``CodeMatcher``).

The patterns a document declares are repo-relative, so they are matched against
the tree the store lives in — for a project-local store, the directory holding
``.docir``. There is nothing to match against in a global store, which is why
the matcher is optional at the seam rather than defaulting to "matches nothing".
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

from docir.platform.filesystem.gitignore import GitignoreIndex
from docir.platform.filesystem.ports import CodeMatcher

#: Hex characters kept from the digest. It rides in committed frontmatter and is
#: read by humans in diffs, so the full 64 would be noise; 48 bits is far more
#: than a per-pattern change detector needs, and a collision costs one unreported
#: edit rather than any damage.
DIGEST_LENGTH = 12

#: Directories never walked when fingerprinting, whatever the repository says:
#: the ones whose contents are *generated* and rewrite themselves. ``.git`` does
#: it on every operation, so a pattern broad enough to reach it would report the
#: code as changed after a checkout that touched nothing — and ``.gitignore``
#: never lists it, because git excludes it without being asked.
#:
#: ``__pycache__`` does it on every interpreter run, and measurably: of the 39
#: files ``src/docir/modules/publishing/**`` matched in this repository, **19**
#: were ``.pyc``. A digest half made of bytecode moves when nothing was edited,
#: and moves differently on a teammate's machine — the same glob on a clean
#: checkout would have reported drift against a baseline they never diverged
#: from. The cache directories beside it are listed on the same rule.
#:
#: This is the **floor**, not the list. The repository's own ``.gitignore``
#: files are consulted beside it (adr-1d1eddbb6fbd), which is what generalises
#: the argument above from Python to every language's build output; these five
#: stay because a tree with no ignore file at all still needs them, and because
#: a repository is free to un-ignore its caches and would then be hashing
#: bytecode again.
_SKIPPED_DIRS = frozenset({".git", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache"})


class RepositoryCodeMatcher(CodeMatcher):
    """Globs a repository working tree, short-circuiting on the first hit."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._ignored = GitignoreIndex(root)

    def matches(self, pattern: str) -> bool:
        """Whether the pattern names at least one existing path.

        Stops at the first match: the answer is a boolean, and the common case
        (a pattern that still matches) should not pay for enumerating a whole
        subtree.

        A pattern the glob engine refuses — absolute, or carrying ``..`` — is
        reported as *unmatched* rather than raised. Tier 0 rejects both on
        write, so one can only arrive by hand-editing the file, and `check` is
        the command that exists to be run over hand-edited files: crashing on
        one would take the other findings down with it.

        Ignored paths are dropped only while the pattern reaches something
        else — the second pass below, and the rule :meth:`_files_under` states
        in full.
        """
        try:
            if any(not self._skipped(path) for path in self._root.glob(pattern)):
                return True
            return any(not self._generated(path) for path in self._root.glob(pattern))
        except (ValueError, NotImplementedError, IndexError, OSError):
            return False

    def fingerprint(self, pattern: str) -> str | None:
        """Digest the contents of every file ``pattern`` matches.

        Contents, not mtimes or a commit id: a checkout, a clone or a rebase
        moves both of those without changing a line, and a finding that fires
        after `git clone` is one nobody reads twice. Hashing the bytes means the
        answer depends only on the tree in front of it — the property that lets
        this work in a repository whose history was never fetched.

        The path is folded in beside each file's hash, so adding, removing or
        renaming a file under a directory glob registers as a change even when
        no surviving file was edited.

        Whitespace and formatting count. A normalised syntax tree would ignore
        them, at the cost of a parser per language and an answer that differs by
        language; the honest trade for a *warning* is to over-report a reformat
        rather than to under-report an edit in a language nobody wrote a parser
        for. This is where to start if the noise turns out to be real.
        """
        try:
            matched = self._files_under(pattern)
        except (ValueError, NotImplementedError, IndexError, OSError):
            return None
        if not matched:
            return None
        digest = hashlib.sha256()
        for relative, path in sorted(matched.items()):
            try:
                content = hashlib.sha256(path.read_bytes()).digest()
            except OSError:
                # Unreadable mid-walk (a permission, a race with a delete). The
                # set is no longer knowable, so the whole answer is unknown —
                # reporting a digest over the part that read would compare a
                # subset against a full one and call it a change.
                return None
            digest.update(relative.encode("utf-8"))
            digest.update(b"\x00")
            digest.update(content)
            digest.update(b"\n")
        return digest.hexdigest()[:DIGEST_LENGTH]

    def _files_under(self, pattern: str) -> dict[str, Path]:
        """Every file the pattern reaches, keyed by repo-relative posix path.

        A directory the glob names is expanded into the files inside it, because
        that is already what a pattern naming a directory *means* here — the
        read path resolves ``src/auth/**`` to the files under ``src/auth``, and
        two answers to "which code is this" would be one answer too many.

        It also matters mechanically: ``**`` yields directories, not files, so
        without the expansion the most natural way to write a pattern would
        fingerprint nothing and quietly record no evidence at all.

        A dict rather than a list because the walk reaches the same file
        through every enclosing directory a recursive glob yields, and a file
        counted twice hashes differently from the same tree counted once.

        **Ignored files are dropped only while the pattern reaches something
        else** (adr-c87e444975e8). `.gitignore` answers "is this the
        repository's source", and that is the right question for the files a
        *broad* glob sweeps up beside the ones it was aimed at: `src/**` reaching
        `src/bin/` is issue-ec3819b1f13c, and dropping the build output there is
        what stops one compile drifting every glob at once. It is the wrong
        question for a glob that reaches **nothing but** ignored files. Nobody
        sweeps a vendored clone up by accident — a path written into `code:` by
        hand is a statement that this document is governed by it, whatever git's
        opinion of whether it belongs in this repository's history, and a
        read-only mirror checked out into an ignored directory is the ordinary
        way to hold one. Taking the ignore rule literally there cost 288 of 288
        governed documents their invalidation at once (GitHub #24), and an empty
        queue is indistinguishable from a clean one.

        So: one pass that drops them, and — only if it found nothing at all — a
        second that keeps them. The common case pays exactly what it paid
        before, including not descending into an ignored subtree; the second
        walk runs only for a pattern that used to resolve to nothing, which is
        the case that was silent.

        The hardcoded floor is absolute in both passes. A glob reaching nothing
        but `__pycache__` governs nothing anyone wrote, and re-admitting it on
        the second pass would hash bytecode again — issue-68df009b4e43 through
        the door this method just opened.
        """
        tracked = self._collect(pattern, self._skipped)
        return tracked or self._collect(pattern, self._generated)

    def _collect(self, pattern: str, skip: Callable[[Path], bool]) -> dict[str, Path]:
        """The files ``pattern`` reaches, less the ones ``skip`` refuses.

        The predicate is a parameter rather than a flag because it is also the
        pruning rule for the walk: a directory ``skip`` refuses is not descended
        into, so the pass that drops ignored files never enters an ignored
        subtree.
        """
        found: dict[str, Path] = {}
        for path in self._root.glob(pattern):
            if skip(path):
                continue
            candidates = (path,) if path.is_file() else path.rglob("*")
            for candidate in candidates:
                if candidate.is_file() and not skip(candidate):
                    found[candidate.relative_to(self._root).as_posix()] = candidate
        return found

    def _generated(self, path: Path) -> bool:
        """Whether ``path`` sits under a directory that rewrites itself.

        The floor, and it holds whatever the repository says — including on the
        pass that stops consulting `.gitignore`.
        """
        return any(part in _SKIPPED_DIRS for part in path.relative_to(self._root).parts)

    def _skipped(self, path: Path) -> bool:
        """Whether ``path`` is generated rather than written.

        Two sources, and the order is an optimisation only: the always-skipped
        floor is a set lookup per path part, while the ignore files cost a parse
        the first time a directory is asked about.
        """
        return self._generated(path) or self._ignored.ignores(path)
