"""What this build still does and is going to stop doing, with the date.

A warning nobody can plan around is a mood. RFC 9745 pairs a `Deprecation` date
with RFC 8594's `Sunset` — when it stops working — precisely so a consumer can
answer "is this urgent" without asking anybody, and that is the shape copied
here (adr-6d4d43d44075).

The register is declared rather than discovered. A deprecation is a promise, and
a promise that a scanner infers from the code is one nobody made: somebody has
to decide what replaces the thing and when it goes, which is the whole content
of the announcement.

Pure, and per-entry — the question "has the date passed" needs a clock, so the
caller brings one rather than this module reaching for one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class Deprecation:
    """One thing this build accepts and will stop accepting.

    ``subject`` names it the way a caller writes it, because that is the string
    somebody will grep their scripts for. ``replacement`` is what to write
    instead — a deprecation with nowhere to go is a removal, and should be
    announced as one. ``sunset`` is the date it stops working.
    """

    subject: str
    replacement: str
    sunset: date
    note: str = ""

    def overdue(self, today: date) -> bool:
        """Whether the date has passed and the thing is still here.

        True is a defect in *docir*, not in the store reading it: past the
        sunset the surface was supposed to be gone, so an entry still answering
        means a removal was promised and not made. That is the dead-man's switch
        half of the pattern — the announcement polices its own schedule instead
        of relying on somebody to remember the date it named.
        """
        return today > self.sunset


#: Everything currently announced. Empty is a valid and expected state.
#:
#: `--include-resolved` is the one deprecation docir shipped before it had
#: anywhere to announce one: it warns on stderr at the moment of use, which
#: reaches whoever ran it, once, with no date and so no reason to act. It is the
#: entry this register was built around.
DEPRECATIONS: tuple[Deprecation, ...] = (
    Deprecation(
        subject="--include-resolved",
        replacement="--include-inactive",
        sunset=date(2027, 3, 1),
        note=(
            "the flag controls the schema's `inactive_statuses`, of which "
            "`resolved` is only one; the wire field was always `include_inactive`"
        ),
    ),
)


def describe_deprecations(today: date) -> list[dict[str, object]]:
    """The register as plain data, for whoever is reporting it.

    One shape, built once. `docir doctor` renders it in a `compat` section and
    the `deprecations` command answers with it over the wire; each building its
    own dict is how the two come to disagree about a field name, which is the
    drift adr-354a4270ecd8 exists to prevent one layer down.
    """
    return [
        {
            "subject": entry.subject,
            "replacement": entry.replacement,
            "sunset": entry.sunset.isoformat(),
            "overdue": overdue,
            "note": entry.note,
        }
        for entry, overdue in announcements(today)
    ]


def announcements(today: date) -> tuple[tuple[Deprecation, bool], ...]:
    """Every deprecation with whether its date has passed, soonest first.

    Sorted by sunset rather than by name: the reader's question is what happens
    next, and a register long enough to need sorting is one where alphabetical
    order buries the urgent entry in the middle.
    """
    return tuple(
        (entry, entry.overdue(today))
        for entry in sorted(DEPRECATIONS, key=lambda entry: (entry.sunset, entry.subject))
    )
