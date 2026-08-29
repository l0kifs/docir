"""The :class:`EmbeddingScheduler` port — deferred, eventually-consistent embeds.

A content change flags the row dirty and returns immediately; the actual
vector recompute happens off the write's critical path. This port abstracts
that scheduling: the production adapter debounces and drains dirty rows on a
background thread, while ``flush()`` forces a synchronous drain (the
``--wait-embeddings`` / ``docir embed --flush`` escape hatch, and the path all
tests drive). Everything here is exposed synchronously so it is fully testable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DrainResult:
    """What one drain of the dirty queue actually did.

    Two numbers because the queue is keyed by *document* while the work is
    measured in *vectors*, and they are far apart: each document writes one
    vector of its own plus one per ``##`` section (adr-927aa43d9635), so 315
    documents is 1,326 vectors on docir's own corpus. Reporting only the
    document count understated a rebuild's work by 4x, and it is the vector
    count that explains why a rebuild takes a minute — the scan and the SQLite
    writes are ~4% of it.

    Returned rather than derived by the caller, because only the drain knows
    which documents it touched. Counting rows in the index afterwards would
    give the store's total, which equals this only after a full rebuild — the
    same class of near-enough number this type exists to remove.
    """

    documents: int
    vectors: int


class EmbeddingScheduler(ABC):
    """Schedules and flushes deferred embedding recomputes."""

    @abstractmethod
    def schedule(self, doc_id: str) -> None:
        """Request that ``doc_id``'s vector be (re)computed, eventually."""

    @abstractmethod
    def flush(self) -> DrainResult:
        """Synchronously recompute every currently-dirty vector.

        Returns what the drain did (see :class:`DrainResult`). Safe to call at
        any time; this is the escape hatch that makes the async path
        deterministic.
        """

    @abstractmethod
    def start(self) -> None:
        """Begin background draining (no-op for synchronous implementations)."""

    @abstractmethod
    def stop(self) -> None:
        """Stop background draining and release resources."""

    @abstractmethod
    def wake(self) -> None:
        """Tell a background drainer that dirty vectors are already queued.

        For the one caller that marks documents dirty without going through
        :meth:`schedule`: the store bootstrap rebuilds an index from files and
        leaves every vector to the queue, so the work exists in the database
        with nothing having announced it.

        Abstract rather than a default no-op, so an implementation has to say
        which it is: a synchronous scheduler must *not* wake, because waking it
        means draining inline and the bootstrap defers precisely because that
        drain costs a minute; one with a worker must, or the queue stands until
        something else happens to write.
        """
