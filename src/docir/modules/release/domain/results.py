"""What the release use cases return, and the one comparison they make.

``latest`` is deliberately three-valued: a version, or ``None`` meaning *not
known* — never checked, or the check failed. Absent is not "up to date"; the
rule the schema baseline and the index build stamp already follow.
"""

from __future__ import annotations

from dataclasses import dataclass

from packaging.version import InvalidVersion, Version


@dataclass(frozen=True, slots=True)
class ReleaseStatus:
    """What is installed, what is published, and how to close the gap."""

    installed: str
    #: The newest release known, or ``None`` when nothing has been checked.
    latest: str | None
    #: ISO date the cached answer was fetched, or ``None``.
    checked_on: str | None
    method: str
    upgrade_command: tuple[str, ...]
    explanation: str

    @property
    def update_available(self) -> bool:
        return is_newer(self.latest, than=self.installed)


@dataclass(frozen=True, slots=True)
class UpgradeOutcome:
    """What the package step of ``docir self upgrade`` did, if anything."""

    #: Whether an installer was actually run.
    ran: bool
    #: Whether it succeeded. ``True`` with ``ran=False`` means "nothing to do".
    ok: bool
    command: tuple[str, ...]
    message: str


def is_newer(candidate: str | None, *, than: str) -> bool:
    """Whether ``candidate`` is a strictly newer release than ``than``.

    PEP 440 ordering rather than a string or tuple compare, because ``0.9.0`` is
    newer than ``0.10.0`` under both of those and neither knows what a release
    candidate is. An unparseable version on either side answers ``False``: this
    decides whether to *tell someone to upgrade*, and the honest answer to a
    version nobody can order is "no idea", which reads the same as "no".
    """
    if candidate is None:
        return False
    try:
        return Version(candidate) > Version(than)
    except InvalidVersion:
        return False
