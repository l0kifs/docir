"""Embedding schedulers — the deferred, eventually-consistent recompute.

Two implementations of the :class:`EmbeddingScheduler` port:

* :class:`InlineEmbeddingScheduler` drains synchronously — used for in-process
  execution and everywhere in the test suite, so behavior is deterministic.
* :class:`ThreadedEmbeddingScheduler` drains on a background thread with a
  debounce window, coalescing a burst of edits to one document into a single
  recompute — used inside the long-lived daemon. Its ``flush`` still drains
  synchronously, which is the escape hatch tests drive.

Both share :func:`drain_dirty`, which does the actual work.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from docir.domain.ports.embedder import Embedder
from docir.domain.ports.scheduler import EmbeddingScheduler
from docir.domain.ports.unit_of_work import UnitOfWork

UnitOfWorkFactory = Callable[[], UnitOfWork]


def drain_dirty(uow_factory: UnitOfWorkFactory, embedder: Embedder) -> int:
    """Recompute every dirty document's vector in one transaction.

    Returns the number of documents (re)embedded. A dirty row whose document
    has vanished is dropped so it cannot wedge the queue forever.
    """
    count = 0
    with uow_factory() as uow:
        for doc_id in uow.embeddings.dirty_ids():
            document = uow.documents.get(doc_id)
            if document is None:
                uow.embeddings.remove(doc_id)
                continue
            vector = embedder.embed(document.embedding_text())
            uow.embeddings.set_vector(doc_id, vector)
            count += 1
        uow.commit()
    return count


class InlineEmbeddingScheduler(EmbeddingScheduler):
    """Synchronous scheduler: every schedule/flush drains immediately."""

    def __init__(self, uow_factory: UnitOfWorkFactory, embedder: Embedder) -> None:
        self._uow_factory = uow_factory
        self._embedder = embedder

    def schedule(self, doc_id: str) -> None:
        drain_dirty(self._uow_factory, self._embedder)

    def flush(self) -> int:
        return drain_dirty(self._uow_factory, self._embedder)

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None


class ThreadedEmbeddingScheduler(EmbeddingScheduler):
    """Background-thread scheduler with a debounce window (daemon path)."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        embedder: Embedder,
        debounce_seconds: float = 2.0,
    ) -> None:
        self._uow_factory = uow_factory
        self._embedder = embedder
        self._debounce = debounce_seconds
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def schedule(self, doc_id: str) -> None:
        self._wake.set()

    def flush(self) -> int:
        with self._lock:
            return drain_dirty(self._uow_factory, self._embedder)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="docir-embed-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    def _run(self) -> None:  # pragma: no cover - timing-dependent background loop
        while not self._stop.is_set():
            self._wake.wait()
            self._wake.clear()
            if self._stop.is_set():
                break
            # Debounce: let a burst of rapid edits settle into one recompute.
            self._stop.wait(self._debounce)
            if self._stop.is_set():
                break
            self.flush()
