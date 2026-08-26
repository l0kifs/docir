"""What one install/update touched — the value returned per target.

Pure data: the application service produces an :class:`InstalledFile` per target
it acted on, and the CLI renders them (a table, or JSON with ``--json``). The
``previous_version`` / ``new_version`` pair is what lets ``update`` report a
``v0.1.0 -> v0.2.0`` transition after a docir upgrade.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class InstallAction(enum.Enum):
    """What happened to a target's file."""

    #: The file (or docir's block within it) did not exist and was written.
    CREATED = "created"
    #: The file (or docir's block) existed and was refreshed.
    UPDATED = "updated"
    #: The file existed and was rewritten, but only its version stamp moved —
    #: this release shipped no change to what it says.
    UNCHANGED = "unchanged"
    #: The file existed but was left untouched (e.g. a foreign ``AGENTS.md``).
    SKIPPED = "skipped"


@dataclass(frozen=True)
class InstalledFile:
    """The outcome of acting on one target.

    One row per *target*, not per file: a skill is a directory now, and seven
    rows all reporting the same version transition would bury the answer the
    caller wants ("did it install, and at what version"). ``path`` is therefore
    the entry point, and the bundled files it carries are named in ``extras``.
    """

    target: str
    path: str
    action: InstallAction
    previous_version: str | None
    new_version: str | None
    note: str | None = None
    #: Files written *beside* ``path``, relative to its directory and
    #: ``/``-separated (e.g. ``reference/schema.md``). Empty for a pointer.
    extras: tuple[str, ...] = ()
    #: Files deleted from the skill's directory because this build no longer
    #: ships them. Reported rather than merely done: it is the one part of an
    #: install that destroys something, and a reference file left behind from an
    #: older docir would be read as current.
    removed: tuple[str, ...] = ()
