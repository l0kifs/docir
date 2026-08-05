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
from typing import Protocol

from docir.modules.indexing.application.ports.scheduler import EmbeddingScheduler
from docir.platform.embedding import Embedder
from docir.platform.persistence.ports import StoredChunk
from docir.platform.persistence.unit_of_work import UnitOfWork

UnitOfWorkFactory = Callable[[], UnitOfWork]


def drain_dirty(uow_factory: UnitOfWorkFactory, embedder: Embedder) -> int:
    """Recompute every dirty document's vectors in one transaction.

    Two vectors per document, not one: the document vector over title +
    description + body, and one vector per section (adr-927aa43d9635). The document
    vector is what the model can see of the whole — which for a body over
    ~1,900 characters is only its head, because the model truncates and says
    nothing about it. The chunk vectors are what put the rest of the body into
    the index at all.

    Both are written under the same dirty flag and in the same transaction, so
    a document can never be indexed with vectors describing two different
    bodies. Returns the number of documents (re)embedded; a dirty row whose
    document has vanished is dropped so it cannot wedge the queue forever.
    """
    count = 0
    model_id = embedder.model_id
    with uow_factory() as uow:
        for doc_id in uow.embeddings.dirty_ids(model_id):
            document = uow.documents.get(doc_id)
            if document is None:
                uow.embeddings.remove(doc_id)
                uow.chunks.remove(doc_id)
                continue
            uow.embeddings.set_vector(doc_id, embedder.embed(document.embedding_text()), model_id)
            uow.chunks.replace(doc_id, _chunks_for(document, embedder), model_id)
            count += 1
        uow.commit()
    return count


class _Chunkable(Protocol):
    """The slice of a document this module is allowed to know about.

    ``indexing`` may not import ``documents`` (tach enforces it), so the entity
    is the seam: it hands over already-rendered ``(ordinal, heading, text)``
    triples and nothing here needs to know what a Document is. A structural type
    rather than ``object`` so the call still type-checks — the same shape the
    fastembed adapter uses for its model handle (adr-ab9c454b760c).
    """

    def embedding_chunks(self) -> tuple[tuple[int, str, str], ...]: ...


def _chunks_for(document: _Chunkable, embedder: Embedder) -> list[StoredChunk]:
    """Embed each section the document offers, in body order."""
    return [
        StoredChunk(ordinal=ordinal, heading=heading, vector=embedder.embed(text))
        for ordinal, heading, text in document.embedding_chunks()
    ]


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
