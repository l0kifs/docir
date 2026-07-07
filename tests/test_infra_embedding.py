"""Tests for the deterministic embedder and the embedding schedulers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import pytest

from docir.domain.entities.document import Document
from docir.domain.ports.unit_of_work import UnitOfWork
from docir.infrastructure.embedding.deterministic_embedder import DeterministicEmbedder
from docir.infrastructure.embedding.scheduler import (
    InlineEmbeddingScheduler,
    ThreadedEmbeddingScheduler,
    drain_dirty,
)

Factory = Callable[[], UnitOfWork]


class TestDeterministicEmbedder:
    def test_is_deterministic(self) -> None:
        embedder = DeterministicEmbedder()
        assert embedder.embed("hello world").values == embedder.embed("hello world").values

    def test_dimension_and_model_id(self) -> None:
        embedder = DeterministicEmbedder(dimension=128)
        assert embedder.dimension == 128
        assert embedder.embed("x").dimension == 128
        assert "128" in embedder.model_id

    def test_lexical_overlap_scores_higher(self) -> None:
        embedder = DeterministicEmbedder()
        base = embedder.embed("authentication tokens and refresh sessions")
        similar = embedder.embed("authentication tokens refresh")
        different = embedder.embed("database migration schema tables")
        assert base.cosine_similarity(similar) > base.cosine_similarity(different)

    def test_bad_dimension_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            DeterministicEmbedder(dimension=0)


def _seed_dirty_doc(factory: Factory, doc_id: str = "adr-0001") -> None:
    document = Document(
        id=doc_id,
        title="Auth",
        description="Auth tokens",
        type="decision",
        status="proposed",
        created=date(2026, 1, 1),
        updated=date(2026, 1, 1),
        body="body about tokens",
    )
    with factory() as uow:
        uow.documents.save(document)
        uow.embeddings.mark_dirty(document.id)
        uow.commit()


class TestSchedulers:
    def test_drain_dirty_computes_vector(self, uow_factory: Factory) -> None:
        _seed_dirty_doc(uow_factory)
        count = drain_dirty(uow_factory, DeterministicEmbedder())
        assert count == 1
        with uow_factory() as uow:
            assert uow.embeddings.get_vector("adr-0001") is not None
            assert uow.embeddings.dirty_ids() == []

    def test_inline_scheduler_flush(self, uow_factory: Factory) -> None:
        _seed_dirty_doc(uow_factory)
        scheduler = InlineEmbeddingScheduler(uow_factory, DeterministicEmbedder())
        assert scheduler.flush() == 1
        scheduler.start()  # no-op
        scheduler.stop()  # no-op

    def test_inline_scheduler_schedule_drains(self, uow_factory: Factory) -> None:
        _seed_dirty_doc(uow_factory)
        scheduler = InlineEmbeddingScheduler(uow_factory, DeterministicEmbedder())
        scheduler.schedule("adr-0001")
        with uow_factory() as uow:
            assert uow.embeddings.dirty_ids() == []

    def test_threaded_scheduler_flush_and_lifecycle(self, uow_factory: Factory) -> None:
        _seed_dirty_doc(uow_factory)
        scheduler = ThreadedEmbeddingScheduler(
            uow_factory, DeterministicEmbedder(), debounce_seconds=0.01
        )
        scheduler.start()
        scheduler.start()  # idempotent
        scheduler.schedule("adr-0001")
        assert scheduler.flush() == 1
        scheduler.stop()
        scheduler.stop()  # idempotent
