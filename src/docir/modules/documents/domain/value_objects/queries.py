"""Filter value objects for the structured read path (``docs query``)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DocumentFilter:
    """A conjunction of structured filters over document metadata.

    ``None`` / empty means "do not filter on this dimension". Tag matching is
    "has all listed tags". By default archived documents and — for the active
    read path — resolved/closed documents are excluded; the flags widen that.
    """

    types: tuple[str, ...] = ()
    statuses: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    include_archived: bool = False
    # When set, restrict to these statuses being *excluded* as "inactive"
    # unless ``include_inactive`` overrides it (used for default visibility).
    inactive_statuses: tuple[str, ...] = ()
    include_inactive: bool = False
    #: Exact match on the steward. There is deliberately no "stale" field here:
    #: staleness is derived from the clock and the type's review cadence, which
    #: are application concerns the index does not store, so it is filtered
    #: after the query rather than in SQL.
    owner: str | None = None
