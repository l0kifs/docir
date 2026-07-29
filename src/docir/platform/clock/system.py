"""The system clock adapter (implements the :class:`Clock` port)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from docir.platform.clock.port import Clock


class SystemClock(Clock):
    """Returns the current date in UTC.

    UTC, not local time. These dates are written into files that are committed
    and read by other people: with `date.today()` two teammates either side of
    midnight stamped different dates for the same moment, and the staleness
    clock — which counts whole days since `verified` — inherited the skew. A
    document is not more or less reviewed depending on who ran the command.
    """

    def today(self) -> date:
        return datetime.now(UTC).date()
