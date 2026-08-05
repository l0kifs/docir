"""Tests for the system clock adapter."""

from __future__ import annotations

from datetime import UTC, datetime

from docir.platform.clock import SystemClock


def test_today_is_the_utc_date() -> None:
    """Dates are UTC, not local (guards issue-7e16dfe2521c).

    They are written into committed files and read by other people, so a
    local-time stamp made the same moment two different dates either side of
    midnight, and the staleness clock — whole days since `verified` — inherited
    the skew. Asserting against a UTC date computed here rather than against
    `date.today()`, which is the local value the fix moved away from.
    """
    assert SystemClock().today() == datetime.now(UTC).date()
