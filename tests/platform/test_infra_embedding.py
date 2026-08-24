"""Tests for the deterministic embedder and the embedding schedulers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import pytest

from docir.entry_points.composition import _build_embedder
from docir.modules.documents.domain.entities.document import Document
from docir.modules.indexing.infra.scheduler import (
    InlineEmbeddingScheduler,
    ThreadedEmbeddingScheduler,
    drain_dirty,
)
from docir.platform.embedding.deterministic import DeterministicEmbedder
from docir.platform.embedding.fastembed import FastEmbedEmbedder
from docir.platform.persistence.unit_of_work import UnitOfWork

Factory = Callable[[], UnitOfWork]


class TestDeterministicEmbedder:
    def test_is_deterministic(self) -> None:
        embedder = DeterministicEmbedder()
        assert embedder.embed("hello world").values == embedder.embed("hello world").values

    def test_the_configured_width_reaches_the_vector_and_the_model_id(self) -> None:
        # Through the vector and the id, not an accessor: the embedder no longer
        # advertises a width, because nothing outside it ever asked
        # (issue-6618d3a9e868). What the width still has to do is shape the
        # output and distinguish two configurations' vectors.
        embedder = DeterministicEmbedder(dimension=128)
        assert embedder.embed("x").dimension == 128
        assert "128" in embedder.model_id
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
        drained = drain_dirty(uow_factory, DeterministicEmbedder())
        # One document, two vectors: its own plus the body's single chunk. The
        # two counts are separate because the queue is keyed by document while
        # the cost is vectors (adr-927aa43d9635).
        assert (drained.documents, drained.vectors) == (1, 2)
        with uow_factory() as uow:
            assert uow.embeddings.get_vector("adr-0001") is not None
            assert uow.embeddings.dirty_ids(DeterministicEmbedder().model_id) == []

    def test_inline_scheduler_flush(self, uow_factory: Factory) -> None:
        _seed_dirty_doc(uow_factory)
        scheduler = InlineEmbeddingScheduler(uow_factory, DeterministicEmbedder())
        assert scheduler.flush().documents == 1
        scheduler.start()  # no-op
        scheduler.stop()  # no-op

    def test_inline_scheduler_schedule_drains(self, uow_factory: Factory) -> None:
        _seed_dirty_doc(uow_factory)
        scheduler = InlineEmbeddingScheduler(uow_factory, DeterministicEmbedder())
        scheduler.schedule("adr-0001")
        with uow_factory() as uow:
            assert uow.embeddings.dirty_ids(DeterministicEmbedder().model_id) == []

    def test_threaded_scheduler_flush_and_lifecycle(self, uow_factory: Factory) -> None:
        _seed_dirty_doc(uow_factory)
        scheduler = ThreadedEmbeddingScheduler(
            uow_factory, DeterministicEmbedder(), debounce_seconds=0.01
        )
        scheduler.start()
        scheduler.start()  # idempotent
        scheduler.schedule("adr-0001")
        assert scheduler.flush().documents == 1
        scheduler.stop()
        scheduler.stop()  # idempotent


class TestFastEmbedEmbedder:
    """The real model — what every default install actually runs.

    These are ``slow``: the first one downloads ~64 MB and loads an ONNX model
    (~4s cold, ~2ms warm afterwards). They exist because this adapter used to be
    excluded from the type checker and omitted from coverage, which was
    defensible while it was opt-in and stopped being so when it became the
    default. Skip them locally with ``-m "not slow"``.
    """

    @pytest.mark.slow
    def test_embeds_text_at_the_model_dimension(self) -> None:
        embedder = FastEmbedEmbedder()
        vector = embedder.embed("payment capture idempotency")
        assert vector.dimension == 384
        # A real model returns a dense unit-ish vector, not zeros.
        assert any(component != 0.0 for component in vector.values)

    @pytest.mark.slow
    def test_related_text_scores_higher_than_unrelated(self) -> None:
        # The whole reason this is the default: it must rank by meaning, not by
        # shared words. The hashing embedder scores this pair 0.0 (benchmarks/).
        embedder = FastEmbedEmbedder()
        query = embedder.embed("stop shoppers getting billed twice")
        related = embedder.embed("idempotency keys prevent duplicate payment capture")
        unrelated = embedder.embed("round currency amounts half to even")
        assert query.cosine_similarity(related) > query.cosine_similarity(unrelated)

    @pytest.mark.slow
    def test_is_deterministic_for_the_same_text(self) -> None:
        embedder = FastEmbedEmbedder()
        assert embedder.embed("same input").values == embedder.embed("same input").values

    def test_model_id_identifies_the_model_without_loading_it(self) -> None:
        # Not slow: model_id must be available before the model loads, because
        # it is what decides whether stored vectors are reusable.
        assert FastEmbedEmbedder().model_id == "fastembed:BAAI/bge-small-en-v1.5"
        assert FastEmbedEmbedder("some/other-model").model_id == "fastembed:some/other-model"


class TestEmbedderSelection:
    """Which embedder a default install gets — the decision, not the model."""

    def test_default_is_the_real_model(self, monkeypatch) -> None:
        monkeypatch.delenv("DOCIR_EMBEDDER", raising=False)
        assert _build_embedder().model_id.startswith("fastembed:")

    @pytest.mark.parametrize("value", ["deterministic", "hash", "DETERMINISTIC"])
    def test_opt_out_selects_the_model_free_embedder(self, monkeypatch, value: str) -> None:
        monkeypatch.setenv("DOCIR_EMBEDDER", value)
        assert _build_embedder().model_id.startswith("deterministic-hash")

    def test_falls_back_with_a_warning_when_fastembed_is_missing(self, monkeypatch) -> None:
        # A missing dependency must degrade, not break the CLI outright.
        monkeypatch.delenv("DOCIR_EMBEDDER", raising=False)
        monkeypatch.setattr(
            "docir.entry_points.composition.importlib.util.find_spec", lambda _name: None
        )
        with pytest.warns(RuntimeWarning, match="shared words rather than meaning"):
            embedder = _build_embedder()
        assert embedder.model_id.startswith("deterministic-hash")
