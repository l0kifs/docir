"""Resolving ``code`` globs against the repository (implements ``CodeMatcher``).

The patterns a document declares are repo-relative, so they are matched against
the tree the store lives in — for a project-local store, the directory holding
``.docir``. There is nothing to match against in a global store, which is why
the matcher is optional at the seam rather than defaulting to "matches nothing".
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from docir.platform.filesystem.ports import CodeMatcher

#: Hex characters kept from the digest. It rides in committed frontmatter and is
#: read by humans in diffs, so the full 64 would be noise; 48 bits is far more
#: than a per-pattern change detector needs, and a collision costs one unreported
#: edit rather than any damage.
DIGEST_LENGTH = 12

#: Directories never walked when fingerprinting. ``.git`` rewrites itself on
#: every operation, so a pattern broad enough to reach it would report the code
#: as changed after a checkout that touched nothing.
_SKIPPED_DIRS = frozenset({".git"})


class RepositoryCodeMatcher(CodeMatcher):
    """Globs a repository working tree, short-circuiting on the first hit."""

    def __init__(self, root: Path) -> None:
        self._root = root

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
        """
        try:
            return next(iter(self._root.glob(pattern)), None) is not None
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
        """
        found: dict[str, Path] = {}
        for path in self._root.glob(pattern):
            if self._skipped(path):
                continue
            candidates = (path,) if path.is_file() else path.rglob("*")
            for candidate in candidates:
                if candidate.is_file() and not self._skipped(candidate):
                    found[candidate.relative_to(self._root).as_posix()] = candidate
        return found

    def _skipped(self, path: Path) -> bool:
        return any(part in _SKIPPED_DIRS for part in path.relative_to(self._root).parts)
