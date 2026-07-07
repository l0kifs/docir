"""The composition root — wires infrastructure adapters into the use cases.

This is the one module that imports across every layer. It builds the object
graph (engine, migrations, embedder, scheduler, repositories, services,
dispatcher) and hands back a :class:`Container`. Nothing else in the codebase
constructs infrastructure adapters directly.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import Engine

from docir.application.dispatcher import Dispatcher
from docir.application.executor import InProcessExecutor, RequestExecutor
from docir.application.services.document_service import DocumentService
from docir.application.services.maintenance_service import MaintenanceService
from docir.application.services.tag_service import TagService
from docir.domain.ports.clock import Clock
from docir.domain.ports.embedder import Embedder
from docir.domain.ports.scheduler import EmbeddingScheduler
from docir.domain.ports.unit_of_work import UnitOfWork
from docir.infrastructure.clock import SystemClock
from docir.infrastructure.config.settings import Settings
from docir.infrastructure.embedding.deterministic_embedder import DeterministicEmbedder
from docir.infrastructure.embedding.scheduler import (
    InlineEmbeddingScheduler,
    ThreadedEmbeddingScheduler,
)
from docir.infrastructure.filesystem.markdown_store import MarkdownDocumentFileStore
from docir.infrastructure.filesystem.tag_file_store import YamlTagFileStore
from docir.infrastructure.persistence.database import (
    create_index_engine,
    create_session_factory,
    run_migrations,
)
from docir.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from docir.infrastructure.schema.loader import load_schema

#: Environment variable selecting the embedder implementation.
EMBEDDER_ENV = "DOCIR_EMBEDDER"


@dataclass
class Container:
    """The wired application object graph plus the resources it owns."""

    settings: Settings
    dispatcher: Dispatcher
    scheduler: EmbeddingScheduler
    engine: Engine

    def close(self) -> None:
        """Stop the scheduler and dispose of the database engine."""
        self.scheduler.stop()
        self.engine.dispose()


def _build_embedder() -> Embedder:
    if os.environ.get(EMBEDDER_ENV, "").lower() == "fastembed":
        from docir.infrastructure.embedding.fastembed_embedder import (
            FastEmbedEmbedder,
        )

        return FastEmbedEmbedder()
    return DeterministicEmbedder()


def build_container(
    settings: Settings,
    *,
    background_embeddings: bool,
    clock: Clock | None = None,
) -> Container:
    """Construct the full object graph for one process.

    ``clock`` is injectable so tests can freeze the date; production passes the
    default :class:`SystemClock`.
    """
    settings.ensure_directories()
    run_migrations(settings.database_url)

    schema = load_schema(settings.schema_path)
    engine = create_index_engine(settings.database_url)
    session_factory = create_session_factory(engine)

    def uow_factory() -> UnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    embedder = _build_embedder()
    scheduler: EmbeddingScheduler
    if background_embeddings:
        scheduler = ThreadedEmbeddingScheduler(uow_factory, embedder)
        scheduler.start()
    else:
        scheduler = InlineEmbeddingScheduler(uow_factory, embedder)

    file_store = MarkdownDocumentFileStore(settings.docs_root)
    tag_file_store = YamlTagFileStore(settings.tags_path)
    clock = clock or SystemClock()

    document_service = DocumentService(uow_factory, file_store, scheduler, embedder, clock, schema)
    tag_service = TagService(uow_factory, tag_file_store, file_store, clock)
    maintenance_service = MaintenanceService(
        uow_factory, file_store, tag_file_store, scheduler, embedder, schema
    )
    dispatcher = Dispatcher(document_service, tag_service, maintenance_service)
    return Container(settings=settings, dispatcher=dispatcher, scheduler=scheduler, engine=engine)


def build_in_process_executor(
    settings: Settings,
) -> tuple[RequestExecutor, Container]:
    """Build an in-process executor and the container it owns (caller closes)."""
    container = build_container(settings, background_embeddings=False)
    return InProcessExecutor(container.dispatcher), container


UnitOfWorkFactory = Callable[[], UnitOfWork]
