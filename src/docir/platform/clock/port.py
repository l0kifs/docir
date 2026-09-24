"""The :class:`Clock` port — the current date, injected for testability.

``created`` and ``updated`` frontmatter fields are stamped from here rather
than calling ``date.today()`` directly, so tests can freeze time and assert on
exact dates deterministically.

Dates are **UTC calendar dates**. They are written into committed files and read
by other people, so a local-time stamp made the same moment two different dates
either side of midnight, and staleness (whole days since `verified`) inherited
the skew.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, date, datetime, time


class Clock(ABC):
    """Supplies the current calendar date, and the current instant."""

    @abstractmethod
    def today(self) -> date:
        """Return today's date."""

    def now(self) -> datetime:
        """Return the current instant, timezone-aware in UTC.

        A clock that only knows the date answers the start of that UTC day, so a
        date-frozen test clock still yields a deterministic instant.
        """
        return datetime.combine(self.today(), time.min, tzinfo=UTC)
