"""The three things the release use cases need from the outside world.

All three are trivial to fake, which is the point: the service decides *whether*
to run an installer and *whether* to reach the network, and a test must be able
to assert those decisions without doing either.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence


class ProcessRunner(ABC):
    """Runs an installer command."""

    @abstractmethod
    def run(self, command: Sequence[str]) -> tuple[int, str]:
        """Execute ``command``; return its exit status and combined output."""


class ReleaseIndex(ABC):
    """Looks up the newest published release."""

    @abstractmethod
    def latest_version(self, package: str) -> str | None:
        """The newest version on the index, or ``None`` if it cannot be reached.

        ``None`` rather than an exception: a release check is a courtesy, and a
        machine that is offline is not a machine with a broken docir.
        """


class ReleaseCache(ABC):
    """Stores the last answer, so the network is touched at most once a day."""

    @abstractmethod
    def read(self) -> tuple[str, str] | None:
        """``(version, iso_date)`` last recorded, or ``None``."""

    @abstractmethod
    def write(self, version: str, checked_on: str) -> None:
        """Record ``version`` as of ``checked_on``."""
