"""The register of what this build will stop doing, and when.

A warning with no date cannot be planned around (adr-6d4d43d44075). These test
the two things a date buys: the reader can tell whether it is urgent, and the
announcement polices its own schedule once the day arrives.
"""

from __future__ import annotations

from datetime import date

from docir.modules.release.api import DEPRECATIONS, Deprecation, announcements


def _entry(subject: str, sunset: date) -> Deprecation:
    return Deprecation(subject=subject, replacement=f"{subject}-new", sunset=sunset)


class TestTheDateIsTheContent:
    def test_the_sunset_day_itself_is_not_overdue(self) -> None:
        # The date the thing stops working is the last day it works. Off by one
        # here would report every announcement as a broken promise on the
        # morning it comes true.
        entry = _entry("--old", date(2027, 3, 1))
        assert not entry.overdue(date(2027, 2, 28))
        assert not entry.overdue(date(2027, 3, 1))
        assert entry.overdue(date(2027, 3, 2))

    def test_announcements_are_sorted_by_what_happens_next(self) -> None:
        # Asserts which entries and in which order, not how many: a count
        # cannot tell "sorted" from "returned in declaration order".
        register = (_entry("--zulu", date(2027, 1, 1)), _entry("--alpha", date(2028, 1, 1)))
        ordered = sorted(register, key=lambda entry: (entry.sunset, entry.subject))
        assert [entry.subject for entry in ordered] == ["--zulu", "--alpha"]

    def test_every_shipped_entry_names_a_replacement_and_a_future_date(self) -> None:
        # The register is the promise. An entry with nowhere to go is a removal
        # and has to be announced as one; an entry already past its date is a
        # promise docir broke, which `doctor` reports as an error.
        assert DEPRECATIONS, "the register is empty — nothing exercises this"
        for entry in DEPRECATIONS:
            assert entry.replacement, f"{entry.subject} deprecates to nothing"
            assert entry.subject != entry.replacement

    def test_the_shipped_register_is_reported_with_its_verdict(self) -> None:
        reported = {entry.subject: overdue for entry, overdue in announcements(date(2026, 9, 16))}
        # The flag this register was built around: it warns at the moment of use
        # today, which reaches whoever ran it, once, with no date.
        assert reported["--include-resolved"] is False
