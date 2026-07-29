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
from datetime import date


class Clock(ABC):
    """Supplies the current calendar date."""

    @abstractmethod
    def today(self) -> date:
        """Return today's date."""
