"""The one line a command prints when a newer docir has been published.

Three rules, and each of them exists because the notice is read by an *agent*
rather than by a person at a prompt. A person weighs an interruption and gets on
with what they were doing; an agent follows an instruction, so a notice that
names a command is a notice that will run it.

**It says nothing where the named command cannot work.** An editable checkout
and a lockfile-managed project both classify as ``project``, and for both of them
the package step of ``docir self upgrade`` declines by design
(:mod:`..domain.installation`). docir's own repository is the clearest case:
every command run in it would otherwise carry an upgrade instruction that cannot
be followed, aimed at the people who publish the release.

**Where the command differs, so does the text.** An ephemeral ``uvx`` run and an
unrecognised layout have no installer either, but they do have an answer — pin
the version, or upgrade it the way it was installed — and the installation
already carries that sentence. Printing a single hardcoded "run `docir self
upgrade`" at all four of them is how two thirds of a decision table ends up
wrong.

**It names the moment, not just the command.** `docir self upgrade` replaces the
running process (``os.execv``), stops and respawns a daemon whose build stamp no
longer matches, and rebuilds the index. That is the right thing to do between
tasks and the wrong thing to do in the middle of one, and an agent has no other
way to know.
"""

from __future__ import annotations

from docir.modules.release.domain.results import ReleaseStatus

#: The installation kinds that get no notice at all. ``project`` is the one:
#: docir is a dependency of the tree it is being run in, so whoever wants it
#: moved does it in that tree's lockfile — and this is the build docir's own
#: maintainers run, on the day they publish the release the notice names.
SILENT_METHODS = frozenset({"project"})

#: Appended where `docir self upgrade` is the answer. The command is safe and
#: idempotent; *when* it runs is the part an agent cannot infer.
_WHEN = (
    "run `docir self upgrade` between tasks rather than during one "
    "(it replaces this process and rebuilds the index)"
)


def notice_for(status: ReleaseStatus) -> str | None:
    """One line naming the newer release, or ``None`` to stay quiet.

    ``None`` for three separate reasons, which callers do not need to tell
    apart: nothing newer is published, nothing has been checked (``latest`` is
    unknown, never "up to date"), or this installation is one that must not be
    told to upgrade itself.
    """
    if not status.update_available:
        return None
    if status.method in SILENT_METHODS:
        return None
    head = f"docir {status.latest} is available (this is {status.installed})"
    tail = _WHEN if status.upgrade_command else status.explanation
    return f"{head} — {tail}"
