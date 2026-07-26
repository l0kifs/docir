"""The composition root — wires infrastructure adapters into the use cases.

This is the one module that imports across every layer. It builds the object
graph (engine, migrations, embedder, scheduler, repositories, services,
dispatcher) and hands back a :class:`Container`. Nothing else in the codebase
constructs infrastructure adapters directly.
"""

from __future__ import annotations

import importlib.util
import os
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine

from docir.config.settings import Settings
from docir.entry_points.dispatch import Dispatcher
from docir.modules.documents.api import (
    ID_STYLES,
    PROFILE_NAMES,
    DocumentService,
    MaintenanceService,
    load_schema,
    render_schema_yaml,
)
from docir.modules.indexing.api import EmbeddingScheduler, build_scheduler
from docir.modules.tags.api import TagService
from docir.platform.clock import Clock, SystemClock
from docir.platform.embedding import Embedder
from docir.platform.embedding.deterministic import DeterministicEmbedder
from docir.platform.errors import DocirError, SchemaError
from docir.platform.filesystem.markdown_store import MarkdownDocumentFileStore
from docir.platform.filesystem.tag_store import YamlTagFileStore
from docir.platform.persistence.engine import (
    create_index_engine,
    create_session_factory,
    run_migrations,
)
from docir.platform.persistence.sqlalchemy_uow import SqlAlchemyUnitOfWork
from docir.platform.persistence.unit_of_work import UnitOfWork
from docir.platform.transport.messages import Request, RequestExecutor, Response

#: Environment variable selecting the embedder implementation. Unset means the
#: real model; ``deterministic`` selects the dependency-free hashing embedder.
EMBEDDER_ENV = "DOCIR_EMBEDDER"

#: The id style ``docir init`` writes when the caller does not choose one.
#: ``random`` rather than the schema-level fallback: ``init`` scopes docs to a
#: *repository*, which is exactly where two branches can each mint ``adr-0007``
#: and only collide at merge. Readable numbers stay one flag away.
DEFAULT_INIT_ID_STYLE = "random"


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


class InProcessExecutor(RequestExecutor):
    """Dispatches requests directly against the local use-case services."""

    def __init__(self, dispatcher: Dispatcher) -> None:
        self._dispatcher = dispatcher

    def execute(self, request: Request) -> Response:
        try:
            data = self._dispatcher.dispatch(request.command, request.payload)
            return Response(ok=True, data=data)
        except DocirError as exc:
            return Response(
                ok=False,
                error={
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "exit_code": exc.exit_code,
                },
            )


def _build_embedder() -> Embedder:
    """Pick the embedder: the real model unless asked for, or unable to, do otherwise.

    ``fastembed`` is a hard dependency and the default, because the hashing
    embedder scores shared vocabulary rather than meaning — with it, ``docir
    context`` is barely distinguishable from plain full-text search (see
    ``benchmarks/``). ``DOCIR_EMBEDDER=deterministic`` opts out, which is what
    the test suite does to stay hermetic and model-free.

    If the dependency is somehow absent, fall back rather than refuse to run: a
    weaker index beats no CLI at all. Vectors record which model produced them,
    so switching back and forth re-embeds instead of comparing across spaces.
    """
    choice = os.environ.get(EMBEDDER_ENV, "").lower()
    if choice in ("deterministic", "hash"):
        return DeterministicEmbedder()
    if importlib.util.find_spec("fastembed") is None:
        warnings.warn(
            "fastembed is not installed, falling back to the hashing embedder: "
            "`docir context` will match on shared words rather than meaning. "
            "Reinstall docir, or set DOCIR_EMBEDDER=deterministic to silence this.",
            RuntimeWarning,
            stacklevel=2,
        )
        return DeterministicEmbedder()
    from docir.platform.embedding.fastembed import FastEmbedEmbedder

    return FastEmbedEmbedder()


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
    scheduler = build_scheduler(uow_factory, embedder, background=background_embeddings)

    file_store = MarkdownDocumentFileStore(settings.docs_root)
    tag_file_store = YamlTagFileStore(settings.tags_path)
    clock = clock or SystemClock()

    document_service = DocumentService(uow_factory, file_store, scheduler, embedder, clock, schema)
    tag_service = TagService(uow_factory, tag_file_store, file_store, clock)
    maintenance_service = MaintenanceService(
        uow_factory, file_store, tag_file_store, scheduler, embedder, schema, clock
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


# -- store initialization (``docir init``) ----------------------------------

#: What ``docir init`` gitignores inside the store: the derived index and the
#: daemon's runtime files. Only ``docs/`` + ``docs-schema.yaml`` are committed.
_STORE_GITIGNORE = """\
# docir derived index + daemon runtime — rebuildable from docs/, do not commit.
index.db
index.db-journal
index.db-wal
index.db-shm
daemon.pid
daemon.log
"""


@dataclass(frozen=True)
class InitResult:
    """The outcome of ``docir init`` — where the store is and what was written."""

    home: Path
    profiles: tuple[str, ...]
    schema_written: bool
    gitignore_written: bool
    id_style: str = DEFAULT_INIT_ID_STYLE


def initialize_store(
    settings: Settings,
    *,
    profiles: tuple[str, ...] = (),
    force: bool = False,
    id_style: str = DEFAULT_INIT_ID_STYLE,
) -> InitResult:
    """Create/validate a docir store at ``settings.home`` (the ``docir init`` core).

    Writes a ``docs-schema.yaml`` (default, or with the requested ``profiles``)
    and a ``.gitignore`` for the derived index, ensures the directory layout, and
    runs migrations — the same startup path every command uses, so an initialized
    store is immediately valid. Existing files are preserved unless ``force``.
    """
    unknown = [name for name in profiles if name not in PROFILE_NAMES]
    if unknown:
        available = ", ".join(PROFILE_NAMES)
        raise SchemaError(f"unknown profile(s): {', '.join(unknown)}; available: {available}")
    if id_style not in ID_STYLES:
        raise SchemaError(f"unknown id_style {id_style!r}; available: {', '.join(ID_STYLES)}")

    settings.ensure_directories()

    schema_path = settings.schema_path
    schema_written = force or not schema_path.exists()
    if schema_written:
        schema_path.write_text(render_schema_yaml(profiles, id_style), encoding="utf-8")

    gitignore_path = settings.home / ".gitignore"
    gitignore_written = force or not gitignore_path.exists()
    if gitignore_written:
        gitignore_path.write_text(_STORE_GITIGNORE, encoding="utf-8")

    run_migrations(settings.database_url)
    load_schema(schema_path)  # validate the merged core + profiles (raises SchemaError)
    return InitResult(
        home=settings.home,
        profiles=profiles or ("software",),
        schema_written=schema_written,
        gitignore_written=gitignore_written,
        id_style=id_style,
    )
