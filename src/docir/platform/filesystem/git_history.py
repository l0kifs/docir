"""When a file first entered the repository's history (implements ``FileHistory``).

The one place docir invokes ``git``. Everything else that needs an answer git
could give parses the files instead — ``.gitignore`` most visibly
(adr-1d1eddbb6fbd), because those answers are per-machine and a digest that
differed between colleagues was the defect being fixed. Committed history is
the opposite: it is the same for everyone who has it, and it is the only place
that records which of two colliding files arrived later.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from docir.platform.filesystem.ports import FileHistory

#: Seconds allowed for one ``git log``. Generous for the call being made — a
#: single path's add commits — and bounded because this runs inside a repair the
#: caller is waiting on, and a repository on a stalled network mount must degrade
#: to the next tiebreak rather than hang the command.
_TIMEOUT_SECONDS = 5.0


class GitFileHistory(FileHistory):
    """Reads add times from ``git log`` in the repository above the store."""

    def __init__(self, root: Path) -> None:
        #: The directory ``git`` runs in, which is also what ``added_at``'s
        #: relative paths resolve against — the docs root, so a document's own
        #: ``path`` can be passed through untouched.
        self._root = root

    def added_at(self, path: Path) -> int | None:
        """Unix time of the earliest commit that added ``path``, or ``None``.

        ``None`` means *unknown*, never *new*, and the callers treat it that way
        — the same convention every absent answer in this codebase follows. It
        is returned for an untracked file, for a shallow clone whose history does
        not reach the add, for a store with no repository above it, and for a
        machine with no ``git`` on the path. Each of those is a normal state, so
        none of them raises.

        ``--diff-filter=A`` selects the commits that added the path and git logs
        newest first, so the **last** line is the earliest add. A file deleted
        and re-added has more than one; taking the earliest keeps the answer
        stable as history grows, which is what a tiebreak needs.
        """
        try:
            completed = subprocess.run(
                [
                    "git",
                    "log",
                    "--diff-filter=A",
                    "--format=%ct",
                    "--",
                    str(path),
                ],
                cwd=self._root,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if completed.returncode != 0:
            return None
        stamps = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
        if not stamps:
            return None
        try:
            return int(stamps[-1])
        except ValueError:
            return None
