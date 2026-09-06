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

import hashlib
import threading
from collections.abc import Callable
from typing import Protocol

from docir.modules.indexing.application.ports.scheduler import DrainResult, EmbeddingScheduler
from docir.platform.embedding import Embedder
from docir.platform.persistence.ports import StoredChunk
from docir.platform.persistence.unit_of_work import UnitOfWork

UnitOfWorkFactory = Callable[[], UnitOfWork]


def drain_dirty(uow_factory: UnitOfWorkFactory, embedder: Embedder) -> DrainResult:
    """Recompute every dirty document's vectors in one transaction.

    Two vectors per document, not one: the document vector over title +
    description + body, and one vector per section (adr-927aa43d9635). The document
    vector is what the model can see of the whole — which for a body over
    ~1,900 characters is only its head, because the model truncates and says
    nothing about it. The chunk vectors are what put the rest of the body into
    the index at all.

    Both are written under the same dirty flag and in the same transaction, so
    a document can never be indexed with vectors describing two different
    bodies. Returns both counts (see :class:`DrainResult`) — the documents
    drained and the vectors that cost, which is ``1 + sections`` each. A dirty
    row whose document has vanished is dropped so it cannot wedge the queue
    forever, and counts as neither.

    **A document whose inputs are unchanged is skipped, not re-embedded**
    (issue-77dd42e3a03a). Being on the queue means something asked for a
    recompute; :func:`_input_digest` is what answers whether one is owed. The
    caller with no other way to ask is ``reindex``: a full rebuild re-saves
    every document and so marks every one dirty, and before this it recomputed
    1,547 vectors byte-identical to the stored ones on every release — 146s of
    ``docir self upgrade`` against this repository's 205 documents.

    The digest covers the model id, the document's embedding text *and* every
    chunk triple, so it is not merely a content hash: a release that changes how
    a body is split changes the triples and so the digest, and the recompute
    adr-6a4718fa7a7d requires happens with no version constant for anybody to
    remember to bump.
    """
    documents = 0
    vectors = 0
    model_id = embedder.model_id
    with uow_factory() as uow:
        for doc_id in uow.embeddings.dirty_ids(model_id):
            document = uow.documents.get(doc_id)
            if document is None:
                uow.embeddings.remove(doc_id)
                uow.chunks.remove(doc_id)
                continue
            expected = document.embedding_chunks()
            digest = _input_digest(document, model_id)
            if digest == uow.embeddings.get_input_digest(doc_id) and uow.chunks.count(
                doc_id
            ) == len(expected):
                # Everything the model reads is what it read last time, and it
                # is deterministic, so the vectors it would write are the ones
                # already there. Clearing the flag is the whole of the work.
                #
                # The chunk count is not redundant with the digest: chunks live
                # in their own table and are dropped by their own calls, so a
                # document whose set was removed carries a digest that still
                # matches and would otherwise never be rebuilt — which is what
                # `reindex` after a chunk wipe exists to repair.
                uow.embeddings.clear_dirty(doc_id)
                continue
            uow.embeddings.set_vector(
                doc_id,
                embedder.embed(document.embedding_text()),
                model_id,
                input_digest=digest,
            )
            chunks = _chunks_for(document, embedder)
            uow.chunks.replace(doc_id, chunks, model_id)
            documents += 1
            # The document's own vector plus one per section — counted from what
            # was written rather than from `embedding_chunks()`, so a splitter
            # change cannot make the report and the index disagree.
            vectors += 1 + len(chunks)
        uow.commit()
    return DrainResult(documents=documents, vectors=vectors)


class _Chunkable(Protocol):
    """The slice of a document this module is allowed to know about.

    ``indexing`` may not import ``documents`` (tach enforces it), so the entity
    is the seam: it hands over already-rendered ``(ordinal, heading, text)``
    triples and nothing here needs to know what a Document is. A structural type
    rather than ``object`` so the call still type-checks — the same shape the
    fastembed adapter uses for its model handle (adr-ab9c454b760c).
    """

    def embedding_text(self) -> str: ...

    def embedding_chunks(self) -> tuple[tuple[int, str, str], ...]: ...


def _input_digest(document: _Chunkable, model_id: str) -> str:
    """Everything that decides what the vectors for a document will be.

    The model id, the document vector's text, and each chunk triple — the same
    inputs :func:`drain_dirty` is about to hand the embedder, in the order it
    hands them over. Anything the model reads is in here, and nothing else is,
    so equality means the stored vectors are the ones a recompute would write.

    Framed rather than concatenated: the separators keep a heading that ends
    where the next section's text begins from hashing the same as the pair the
    other way round.
    """
    hasher = hashlib.sha256()
    hasher.update(model_id.encode("utf-8"))
    hasher.update(b"\0text\0")
    hasher.update(document.embedding_text().encode("utf-8"))
    for ordinal, heading, text in document.embedding_chunks():
        hasher.update(f"\0chunk\0{ordinal}\0{heading}\0".encode())
        hasher.update(text.encode("utf-8"))
    return hasher.hexdigest()


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

    def wake(self) -> None:
        # Nothing to wake: there is no worker, and draining here would put the
        # whole embedding pass back on the path the bootstrap took it off.
        return None

    def flush(self) -> DrainResult:
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

    def wake(self) -> None:
        self._wake.set()

    def flush(self) -> DrainResult:
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
