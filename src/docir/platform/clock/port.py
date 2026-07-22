"""The :class:`Clock` port — the current date, injected for testability.

``created`` and ``updated`` frontmatter fields are stamped from here rather
than calling ``date.today()`` directly, so tests can freeze time and assert on
exact dates deterministically.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date


class Clock(ABC):
    """Supplies the current calendar date."""

    @abstractmethod
    def today(self) -> date:
        """Return today's date."""
