"""Resolving ``code`` globs against the repository (implements ``CodeMatcher``).

The patterns a document declares are repo-relative, so they are matched against
the tree the store lives in — for a project-local store, the directory holding
``.docir``. There is nothing to match against in a global store, which is why
the matcher is optional at the seam rather than defaulting to "matches nothing".
"""

from __future__ import annotations

from pathlib import Path

from docir.platform.filesystem.ports import CodeMatcher


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
