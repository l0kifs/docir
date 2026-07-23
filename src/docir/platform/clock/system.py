"""The system clock adapter (implements the :class:`Clock` port)."""

from __future__ import annotations

from datetime import date

from docir.platform.clock.port import Clock


class SystemClock(Clock):
    """Returns the real current date."""

    def today(self) -> date:
        return date.today()
