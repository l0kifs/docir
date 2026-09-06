"""Tests for the deterministic embedder and the embedding schedulers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import pytest
from sqlalchemy import text

from docir.config.settings import Settings
from docir.entry_points.composition import build_embedder
from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.services import chunking
from docir.modules.indexing.infra.scheduler import (
    InlineEmbeddingScheduler,
    ThreadedEmbeddingScheduler,
    drain_dirty,
)
from docir.platform.embedding import Embedding
from docir.platform.embedding.deterministic import DeterministicEmbedder
from docir.platform.embedding.fastembed import FastEmbedEmbedder
from docir.platform.embedding.port import Embedder
from docir.platform.persistence.engine import create_index_engine
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


class _CountingEmbedder(Embedder):
    """Records every text it was asked to embed, so a test can name them.

    A count cannot tell "nothing changed" from "nothing was checked", and the
    claim under test is about *which* documents were recomputed.
    """

    def __init__(self, model_id: str = "deterministic-64") -> None:
        self._inner = DeterministicEmbedder()
        self._model_id = model_id
        self.texts: list[str] = []

    @property
    def model_id(self) -> str:
        return self._model_id

    def embed(self, text: str) -> Embedding:
        self.texts.append(text)
        return self._inner.embed(text)


def _save(factory: Factory, doc_id: str, body: str) -> None:
    with factory() as uow:
        uow.documents.save(
            Document(
                id=doc_id,
                title="Auth",
                description="Auth tokens",
                type="decision",
                status="proposed",
                created=date(2026, 1, 1),
                updated=date(2026, 1, 1),
                body=body,
            )
        )
        uow.embeddings.mark_dirty(doc_id)
        uow.commit()


def _mark_all_dirty(factory: Factory, *doc_ids: str) -> None:
    with factory() as uow:
        for doc_id in doc_ids:
            uow.embeddings.mark_dirty(doc_id)
        uow.commit()


class TestDrainSkipsUnchangedInputs:
    """`docir self upgrade` re-embedded the whole corpus on every release.

    A full rebuild re-saves every document, which marks every one dirty, and the
    drain then recomputed vectors byte-identical to the stored ones — 1,547 of
    them, 146s, against this repository's 205 documents, on a release that had
    changed neither the model nor the chunking (issue-77dd42e3a03a).

    The queue still means "somebody asked"; the input digest is what answers
    whether a recompute is owed.
    """

    def test_a_second_drain_over_unchanged_documents_embeds_nothing(
        self, uow_factory: Factory
    ) -> None:
        _save(uow_factory, "adr-0001", "body about tokens")
        _save(uow_factory, "adr-0002", "body about sessions")
        first = _CountingEmbedder()
        drain_dirty(uow_factory, first)
        assert first.texts, "the first drain must actually embed"
        with uow_factory() as uow:
            before = uow.embeddings.get_vector("adr-0001")

        _mark_all_dirty(uow_factory, "adr-0001", "adr-0002")
        second = _CountingEmbedder()
        drained = drain_dirty(uow_factory, second)

        assert second.texts == []
        assert (drained.documents, drained.vectors) == (0, 0)
        with uow_factory() as uow:
            # Skipped, not dropped: the vectors are still there and still the
            # ones the first drain wrote, and the queue is empty.
            assert uow.embeddings.get_vector("adr-0001") == before
            assert uow.embeddings.dirty_ids(second.model_id) == []

    def test_only_the_document_whose_body_moved_is_recomputed(self, uow_factory: Factory) -> None:
        # Markers that appear in the body alone: the title and description are
        # shared, and they are part of what gets embedded.
        _save(uow_factory, "adr-0001", "alphamarker stays put")
        _save(uow_factory, "adr-0002", "betamarker moves")
        drain_dirty(uow_factory, _CountingEmbedder())

        _save(uow_factory, "adr-0002", "betamarker moves and then moves again")
        _mark_all_dirty(uow_factory, "adr-0001", "adr-0002")
        embedder = _CountingEmbedder()
        drained = drain_dirty(uow_factory, embedder)

        assert drained.documents == 1
        assert embedder.texts, "the changed document must be embedded"
        assert all("betamarker" in text for text in embedder.texts)
        assert not any("alphamarker" in text for text in embedder.texts)

    def test_a_chunking_change_recomputes_documents_whose_text_never_moved(
        self, uow_factory: Factory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # adr-6a4718fa7a7d's requirement, and the reason the digest covers the
        # chunk triples rather than the body alone: nothing about the document
        # changes, only how docir splits it, and the stored vectors describe a
        # splitting that no longer exists.
        body = "## One\n\n" + ("alpha beta gamma. " * 60) + "\n\n## Two\n\ndelta epsilon."
        _save(uow_factory, "adr-0001", body)
        drain_dirty(uow_factory, _CountingEmbedder())

        monkeypatch.setattr(chunking, "MAX_CHUNK_CHARS", 200)
        _mark_all_dirty(uow_factory, "adr-0001")
        embedder = _CountingEmbedder()
        drained = drain_dirty(uow_factory, embedder)

        assert drained.documents == 1
        assert drained.vectors > 2, "the finer splitting must produce more chunk vectors"

    def test_a_model_change_recomputes_everything(self, uow_factory: Factory) -> None:
        _save(uow_factory, "adr-0001", "body about tokens")
        drain_dirty(uow_factory, _CountingEmbedder(model_id="model-a"))

        _mark_all_dirty(uow_factory, "adr-0001")
        embedder = _CountingEmbedder(model_id="model-b")
        drained = drain_dirty(uow_factory, embedder)

        assert drained.documents == 1
        assert embedder.texts != []

    def test_a_document_whose_chunk_rows_were_dropped_is_recomputed(
        self, uow_factory: Factory
    ) -> None:
        # The digest lives on the document row, and chunks are removed by their
        # own calls — so a matching digest is not on its own evidence that the
        # chunk set is there. Without the count check the drain skips this
        # document forever and `reindex` stops being the repair for it.
        _save(uow_factory, "adr-0001", "## One\n\nalpha\n\n## Two\n\nbeta")
        drain_dirty(uow_factory, _CountingEmbedder())
        with uow_factory() as uow:
            # Whatever the chunker made of it — asserted against itself, so the
            # merge rule can change without rewriting the claim.
            before = uow.chunks.count("adr-0001")
            uow.chunks.remove("adr-0001")
            uow.commit()
        assert before >= 1

        _mark_all_dirty(uow_factory, "adr-0001")
        embedder = _CountingEmbedder()
        assert drain_dirty(uow_factory, embedder).documents == 1
        with uow_factory() as uow:
            assert uow.chunks.count("adr-0001") == before

    def test_a_vector_with_no_recorded_digest_is_recomputed(
        self, uow_factory: Factory, settings: Settings
    ) -> None:
        # What an index built before migration 0012 looks like: a vector, a
        # model id, and no record of what produced them. Absent means unknown,
        # and unknown must never be read as unchanged.
        _save(uow_factory, "adr-0001", "body about tokens")
        drain_dirty(uow_factory, _CountingEmbedder())
        engine = create_index_engine(settings.database_url)
        try:
            with engine.begin() as conn:
                conn.execute(text("UPDATE embeddings SET input_digest = NULL"))
        finally:
            engine.dispose()

        _mark_all_dirty(uow_factory, "adr-0001")
        embedder = _CountingEmbedder()
        assert drain_dirty(uow_factory, embedder).documents == 1
        assert embedder.texts != []


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
        assert build_embedder().model_id.startswith("fastembed:")

    @pytest.mark.parametrize("value", ["deterministic", "hash", "DETERMINISTIC"])
    def test_opt_out_selects_the_model_free_embedder(self, monkeypatch, value: str) -> None:
        monkeypatch.setenv("DOCIR_EMBEDDER", value)
        assert build_embedder().model_id.startswith("deterministic-hash")

    def test_falls_back_with_a_warning_when_fastembed_is_missing(self, monkeypatch) -> None:
        # A missing dependency must degrade, not break the CLI outright.
        monkeypatch.delenv("DOCIR_EMBEDDER", raising=False)
        monkeypatch.setattr(
            "docir.entry_points.composition.importlib.util.find_spec", lambda _name: None
        )
        with pytest.warns(RuntimeWarning, match="shared words rather than meaning"):
            embedder = build_embedder()
        assert embedder.model_id.startswith("deterministic-hash")
