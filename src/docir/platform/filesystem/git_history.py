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

    def ids_at(self, ref: str) -> dict[str, str] | None:
        """Every document id committed at ``ref``, mapped to its file path.

        One ``git grep`` rather than a ``git show`` per file: the id is a
        frontmatter line, so grepping the ref for it returns the whole mapping
        in a single call — 250 documents in one subprocess instead of 250.

        The id is read from the **file contents**, never from the filename,
        although the filename begins with it. A prefix carrying a ``-`` would
        make the filename ambiguous, and a hand-edited file can disagree with
        its own name; the frontmatter is what every other reader here trusts.

        ``None`` is *unknown* and the caller must treat it as such — an unknown
        ref, a shallow clone that does not reach it, no repository, no git. It
        is emphatically **not** "no ids there": a pre-merge gate that passed
        because it could not read the base ref is the failure this check exists
        to prevent, one level out.

        An empty dict is a different answer and a real one: the ref resolves and
        holds no documents. Telling the two apart is why the ref is verified
        separately — ``git grep`` exits 1 both for "no matches" and, on some
        versions, for a pathspec that matches nothing, so its exit code alone
        cannot say whether the ref was there.
        """
        if not self._ref_exists(ref):
            return None
        lines = self._grep(ref)
        if lines is None:
            return None
        found: dict[str, str] = {}
        prefix = f"{ref}:"
        for line in lines:
            # `<ref>:<path>:id: <value>` — a path may itself contain a colon, so
            # split off the marker rather than on every colon.
            head, marker, value = line.partition(":id:")
            if not marker:
                continue
            doc_id = value.strip()
            path = head[len(prefix) :] if head.startswith(prefix) else head
            if doc_id:
                found.setdefault(doc_id, path)
        return found

    def _ref_exists(self, ref: str) -> bool:
        """Whether ``ref`` resolves to a commit, so empty can be read as empty."""
        completed = self._run(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"])
        return completed is not None and completed.returncode == 0

    def _grep(self, ref: str) -> list[str] | None:
        """The ``id:`` lines at ``ref``, or ``None`` when git could not answer.

        Exit 1 is "no matches", which is a real and empty answer here; anything
        above it is a failure, and so is not running at all.
        """
        completed = self._run(["grep", "--no-color", "-E", "^id: ", ref, "--", "*.md"])
        if completed is None or completed.returncode > 1:
            return None
        return completed.stdout.splitlines()

    def _run(self, args: list[str]) -> subprocess.CompletedProcess[str] | None:
        """Run one git command in the store's tree, or ``None`` if it could not.

        Every way git can fail to *run* — absent, a broken repository, a stalled
        network mount hitting the timeout — collapses here into one answer the
        callers read as unknown. A command that runs and exits nonzero is a
        different thing and is left to them: only they know whether that exit
        code is an answer.
        """
        try:
            return subprocess.run(
                ["git", *args],
                cwd=self._root,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None

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
        completed = self._run(["log", "--diff-filter=A", "--format=%ct", "--", str(path)])
        if completed is None or completed.returncode != 0:
            return None
        stamps = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
        if not stamps:
            return None
        try:
            return int(stamps[-1])
        except ValueError:
            return None
