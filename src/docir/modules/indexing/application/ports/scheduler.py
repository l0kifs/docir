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


class EmbeddingScheduler(ABC):
    """Schedules and flushes deferred embedding recomputes."""

    @abstractmethod
    def schedule(self, doc_id: str) -> None:
        """Request that ``doc_id``'s vector be (re)computed, eventually."""

    @abstractmethod
    def flush(self) -> int:
        """Synchronously recompute every currently-dirty vector.

        Returns the number of documents embedded. Safe to call at any time;
        this is the escape hatch that makes the async path deterministic.
        """

    @abstractmethod
    def start(self) -> None:
        """Begin background draining (no-op for synchronous implementations)."""

    @abstractmethod
    def stop(self) -> None:
        """Stop background draining and release resources."""
