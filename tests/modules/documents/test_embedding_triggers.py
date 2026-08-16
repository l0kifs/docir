"""Regression tests for the embedding-recompute decision (F3).

A content change (title / description / body) must schedule a re-embed; a
metadata-only change (status / tags / related) must not. Observed through a
recording scheduler that never drains, so the service's decision is visible.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from docir.config.settings import Settings
from docir.modules.documents.application.dto import AddDocumentRequest, UpdateDocumentRequest
from docir.modules.documents.application.services.document_service import DocumentService
from docir.modules.documents.infra.schema_loader import load_schema
from docir.modules.indexing.api import EmbeddingScheduler
from docir.platform.clock import Clock
from docir.platform.embedding.deterministic import DeterministicEmbedder
from docir.platform.filesystem.markdown_store import MarkdownDocumentFileStore
from docir.platform.persistence.unit_of_work import UnitOfWork


class _FixedClock(Clock):
    def today(self) -> date:
        return date(2026, 7, 7)


class _RecordingScheduler(EmbeddingScheduler):
    """Records every schedule() and never drains, so the decision is observable."""

    def __init__(self) -> None:
        self.scheduled: list[str] = []

    def schedule(self, doc_id: str) -> None:
        self.scheduled.append(doc_id)

    def flush(self) -> int:
        return 0

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


def test_recompute_only_on_content_change(
    settings: Settings, uow_factory: Callable[[], UnitOfWork]
) -> None:
    scheduler = _RecordingScheduler()
    service = DocumentService(
        uow_factory,
        MarkdownDocumentFileStore(settings.docs_root),
        scheduler,
        DeterministicEmbedder(),
        _FixedClock(),
        load_schema(settings.schema_path),
    )

    doc_id = service.add(
        AddDocumentRequest(type="decision", title="A", description="d", body="b")
    ).id
    assert scheduler.scheduled == [doc_id]  # a new document is embedded

    scheduler.scheduled.clear()
    service.update(UpdateDocumentRequest(doc_id=doc_id, status="accepted"))
    assert scheduler.scheduled == []  # metadata-only (status): no re-embed

    scheduler.scheduled.clear()
    service.update(UpdateDocumentRequest(doc_id=doc_id, set_title="A renamed"))
    assert scheduler.scheduled == [doc_id]  # title change: re-embed

    scheduler.scheduled.clear()
    service.update(UpdateDocumentRequest(doc_id=doc_id, append_section=("Notes", "more")))
    assert scheduler.scheduled == [doc_id]  # body change: re-embed


def test_a_retype_is_not_a_content_change(
    settings: Settings, uow_factory: Callable[[], UnitOfWork]
) -> None:
    """Renaming a corpus's types must not re-embed it (adr-f8cce745d0d5).

    `type` is in `content_hash` — a write must not silently lose one — but not
    in `embedding_text`, so the vectors a retype would recompute are identical
    to the ones already stored. Under the daemon's debounced scheduler, getting
    this wrong queues every document a corpus-wide rename touches.
    """
    scheduler = _RecordingScheduler()
    service = DocumentService(
        uow_factory,
        MarkdownDocumentFileStore(settings.docs_root),
        scheduler,
        DeterministicEmbedder(),
        _FixedClock(),
        load_schema(settings.schema_path),
    )

    doc_id = service.add(
        AddDocumentRequest(type="decision", title="A", description="d", body="b")
    ).id

    scheduler.scheduled.clear()
    retyped = service.update(
        UpdateDocumentRequest(doc_id=doc_id, set_type="architecture", status="draft")
    )
    assert retyped.type == "architecture"  # the write did happen
    assert scheduler.scheduled == []
