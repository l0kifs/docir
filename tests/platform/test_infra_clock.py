"""Tests for the system clock adapter."""

from __future__ import annotations

from datetime import UTC, date, datetime

from docir.platform.clock import Clock, SystemClock


def test_today_is_the_utc_date() -> None:
    """Dates are UTC, not local (guards issue-7e16dfe2521c).

    They are written into committed files and read by other people, so a
    local-time stamp made the same moment two different dates either side of
    midnight, and the staleness clock — whole days since `verified` — inherited
    the skew. Asserting against a UTC date computed here rather than against
    `date.today()`, which is the local value the fix moved away from.
    """
    assert SystemClock().today() == datetime.now(UTC).date()


def test_system_clock_now_is_aware_utc() -> None:
    now = SystemClock().now()
    assert now.tzinfo is UTC
    assert abs((datetime.now(UTC) - now).total_seconds()) < 5


def test_a_date_only_clock_answers_the_start_of_its_utc_day() -> None:
    class _DateClock(Clock):
        def today(self) -> date:
            return date(2026, 7, 7)

    assert _DateClock().now() == datetime(2026, 7, 7, tzinfo=UTC)
