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
from typing import TYPE_CHECKING

from docir import __version__
from docir.config.settings import Settings, enclosing_project_home
from docir.entry_points.dispatch import Dispatcher
from docir.entry_points.federation import FederatedDispatcher, Reader
from docir.modules.agents.api import InstalledFile, UpdateRequest, build_agent_service
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
from docir.platform.filesystem.code_matcher import RepositoryCodeMatcher
from docir.platform.filesystem.markdown_store import MarkdownDocumentFileStore
from docir.platform.filesystem.tag_store import YamlTagFileStore
from docir.platform.persistence.unit_of_work import UnitOfWork
from docir.platform.transport.messages import Request, RequestExecutor, Response

# SQLAlchemy and Alembic are ~360ms of import, and a command that never builds a
# container never needs them — which is *every* command in daemon mode, where the
# CLI is a socket client (issue-9509f9fa3631). They are therefore imported inside
# the functions that construct an engine, and the annotation-only name here is
# resolved by the type checker rather than at runtime.
if TYPE_CHECKING:
    from sqlalchemy import Engine

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
    #: The federated wrapper, not the bare dispatcher: reads fan out to declared
    #: peers and everything else delegates unchanged (adr-fb938175f72a). With no
    #: peers declared it is a pass-through.
    dispatcher: FederatedDispatcher
    scheduler: EmbeddingScheduler
    engine: Engine
    #: The embedder actually built, not the one requested. `_build_embedder`
    #: falls back when fastembed is missing, so anything reporting the
    #: configuration (benchmarks) must read the resolved object, not the env var.
    embedder: Embedder

    def close(self) -> None:
        """Stop the scheduler and dispose of the database engine."""
        self.scheduler.stop()
        self.engine.dispose()


class InProcessExecutor(RequestExecutor):
    """Dispatches requests directly against the local use-case services.

    Typed to :class:`Reader` rather than :class:`Dispatcher` because the
    federated wrapper is what the container hands over; the executor only ever
    calls ``dispatch``.
    """

    def __init__(self, dispatcher: Reader) -> None:
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
    from docir.platform.persistence.engine import (
        create_index_engine,
        create_session_factory,
        run_migrations,
    )
    from docir.platform.persistence.sqlalchemy_uow import SqlAlchemyUnitOfWork

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
    # No repository above the store means no tree to resolve a `code` glob
    # against; the check that reads this is skipped rather than reporting every
    # pattern in a global store as missing.
    code_root = settings.code_root
    code_matcher = None if code_root is None else RepositoryCodeMatcher(code_root)

    document_service = DocumentService(uow_factory, file_store, scheduler, embedder, clock, schema)
    tag_service = TagService(uow_factory, tag_file_store, file_store)
    maintenance_service = MaintenanceService(
        uow_factory,
        file_store,
        tag_file_store,
        scheduler,
        embedder,
        schema,
        clock,
        __version__,
        code_matcher,
    )
    dispatcher = Dispatcher(document_service, tag_service, maintenance_service)

    def open_peer(home: Path) -> tuple[Reader | None, str]:
        return build_peer_reader(home, embedder=embedder, clock=clock)

    return Container(
        settings=settings,
        dispatcher=FederatedDispatcher(dispatcher, settings.home, open_peer),
        scheduler=scheduler,
        engine=engine,
        embedder=embedder,
    )


def peer_status(home: Path) -> str:
    """Why a peer store cannot be read, or ``""`` when it can.

    One implementation, two callers: the reader factory refuses to open an
    unreadable peer, and the CLI warns about it before dispatching (the daemon's
    own stderr is a log nobody reads — the same reason the schema notice is
    emitted client-side). Two copies of "is this peer usable?" would answer
    differently the first time one of them learned about a new failure.
    """
    if not home.is_dir():
        return "no such store"
    settings = Settings.resolve(home)
    if not settings.db_path.is_file():
        return "no index — run `docir reindex` in that store"
    if not settings.schema_path.is_file():
        return f"no {settings.schema_path.name}"
    return ""


def build_peer_reader(home: Path, *, embedder: Embedder, clock: Clock) -> tuple[Reader | None, str]:
    """Open a peer store for reading, or say why it stayed shut.

    Deliberately **not** ``build_container``: that runs migrations and creates
    directories, and a peer is someone else's repository. The engine's URL
    carries ``mode=ro``, so SQLite refuses a write rather than docir promising
    not to attempt one — the guarantee is the database's, not this function's.

    The reader is a full :class:`Dispatcher` rather than a hand-rolled read
    surface, so a peer's ``context`` is coerced and executed by exactly the code
    the local one is; a second vocabulary here is the drift the dispatcher
    exists to prevent. The embedder is shared with the primary, so N peers still
    load one model.
    """
    from sqlalchemy.exc import SQLAlchemyError

    from docir.platform.persistence.engine import create_index_engine, create_session_factory
    from docir.platform.persistence.sqlalchemy_uow import SqlAlchemyUnitOfWork

    reason = peer_status(home)
    if reason:
        return None, reason
    settings = Settings.resolve(home)
    try:
        schema = load_schema(settings.schema_path)
        engine = create_index_engine(f"sqlite:///file:{settings.db_path}?mode=ro&uri=true")
        session_factory = create_session_factory(engine)

        def uow_factory() -> UnitOfWork:
            return SqlAlchemyUnitOfWork(session_factory)

        file_store = MarkdownDocumentFileStore(settings.docs_root)
        # An inline scheduler is never reached on a read path (only writes
        # schedule), and a write would be refused by the read-only connection
        # before it could enqueue anything.
        scheduler = build_scheduler(uow_factory, embedder, background=False)
        documents = DocumentService(uow_factory, file_store, scheduler, embedder, clock, schema)
        tags = TagService(uow_factory, YamlTagFileStore(settings.tags_path), file_store)
        maintenance = MaintenanceService(
            uow_factory,
            file_store,
            YamlTagFileStore(settings.tags_path),
            scheduler,
            embedder,
            schema,
            clock,
            __version__,
            None,
        )
    except (DocirError, SQLAlchemyError, OSError) as exc:
        return None, f"cannot be read ({type(exc).__name__})"
    return Dispatcher(documents, tags, maintenance), ""


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
    #: ``--force`` was given but the existing schema had been customised, so it
    #: was kept. Not an error: the caller asked to regenerate the store's files
    #: and got everything that is safe to regenerate.
    schema_preserved: bool = False
    #: A project store that already exists above this one, if any. The new store
    #: shadows it for every command run beneath it, which is legitimate (a
    #: monorepo subproject) and easy to do by accident, so it is reported rather
    #: than refused.
    enclosing_home: Path | None = None


def initialize_store(
    settings: Settings,
    *,
    profiles: tuple[str, ...] = (),
    force: bool = False,
    force_schema: bool = False,
    id_style: str = DEFAULT_INIT_ID_STYLE,
) -> InitResult:
    """Create/validate a docir store at ``settings.home`` (the ``docir init`` core).

    Writes a ``docs-schema.yaml`` (default, or with the requested ``profiles``)
    and a ``.gitignore`` for the derived index, ensures the directory layout, and
    runs migrations — the same startup path every command uses, so an initialized
    store is immediately valid. Existing files are preserved unless ``force``.

    The two files are **not** equally replaceable, so ``force`` no longer treats
    them the same. The ``.gitignore`` is a constant this module generates: losing
    it costs nothing. The schema is the one file in the store that cannot be
    reconstructed from the documents — every type, status and cadence a person
    decided on lives only there. So ``force`` overwrites a schema only while it
    still matches what ``init`` would generate; once it has been customised,
    replacing it takes ``force_schema`` as well. Re-running ``init --force`` to
    refresh the ``.gitignore`` used to destroy that work silently.
    """
    unknown = [name for name in profiles if name not in PROFILE_NAMES]
    if unknown:
        available = ", ".join(PROFILE_NAMES)
        raise SchemaError(f"unknown profile(s): {', '.join(unknown)}; available: {available}")
    if id_style not in ID_STYLES:
        raise SchemaError(f"unknown id_style {id_style!r}; available: {', '.join(ID_STYLES)}")

    # Before creating anything: a store above this one is about to be shadowed
    # for every command run beneath it, and nothing used to say so.
    enclosing = enclosing_project_home(settings.home)

    settings.ensure_directories()

    schema_path = settings.schema_path
    generated = render_schema_yaml(profiles, id_style)
    schema_written, schema_preserved = _schema_write_plan(
        schema_path, generated, force=force, force_schema=force_schema
    )
    if schema_written:
        schema_path.write_text(generated, encoding="utf-8")

    gitignore_path = settings.home / ".gitignore"
    gitignore_written = force or not gitignore_path.exists()
    if gitignore_written:
        gitignore_path.write_text(_STORE_GITIGNORE, encoding="utf-8")

    from docir.platform.persistence.engine import run_migrations

    run_migrations(settings.database_url)
    load_schema(schema_path)  # validate the merged core + profiles (raises SchemaError)
    return InitResult(
        home=settings.home,
        profiles=profiles or ("software",),
        schema_written=schema_written,
        gitignore_written=gitignore_written,
        id_style=id_style,
        schema_preserved=schema_preserved,
        enclosing_home=enclosing,
    )


# -- post-upgrade maintenance (``docir self upgrade``) -----------------------

#: Runs one dispatcher command and returns its data (the CLI supplies the
#: error handling, so this module never decides an exit code).
CommandRunner = Callable[[str, dict[str, object]], object]


@dataclass(frozen=True)
class UpgradeResult:
    """What ``docir self upgrade`` did, in the order it did it."""

    version: str
    reindex: dict[str, object]
    agents: tuple[InstalledFile, ...]
    findings: tuple[dict[str, object], ...]
    #: The version that ran the package step, when one ran and handed off to
    #: this process. ``None`` means the package was left alone — a store-only
    #: resync, or an environment docir does not own.
    upgraded_from: str | None = None


def upgrade_store(
    run: CommandRunner,
    *,
    project_root: Path,
    version: str = __version__,
    upgraded_from: str | None = None,
) -> UpgradeResult:
    """Bring one store and its generated files in line with the running docir.

    Three commands in a fixed order, which is two more than a user should have
    to remember and exactly the sequence they had to run by hand:

    * ``reindex`` — the index is derived and gitignored, and it is the only
      writer of the schema baseline and of the version that built it, so a store
      reports no drift and no stale build until it is rebuilt.
    * ``agent update`` — the instruction files are rendered from a template
      inside the package and stamped with the version that rendered them.
      Nothing else reports that the stamp has fallen behind.
    * ``check`` — **last**, so its findings describe the state the upgrade left
      behind rather than the one it started from.

    The *package* is upgraded before any of this, by a process that then hands
    off to the one it installed: everything here has to be the new build's work,
    starting with the rebuild that records which version built the index
    (adr-31aa7aa60d11). ``upgraded_from`` is what that handoff carries, and is
    ``None`` when no install happened.
    """
    reindex = run("reindex", {})
    setup = build_agent_service(version).update(
        UpdateRequest(project_root=project_root, global_root=Path.home())
    )
    findings = run("check", {})
    return UpgradeResult(
        version=version,
        reindex=_as_mapping(reindex),
        agents=setup.files,
        findings=tuple(
            _as_mapping(item) for item in (findings if isinstance(findings, list) else [])
        ),
        upgraded_from=upgraded_from,
    )


def _as_mapping(value: object) -> dict[str, object]:
    """A response payload as a plain mapping (the wire type is ``object``)."""
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _schema_write_plan(
    schema_path: Path, generated: str, *, force: bool, force_schema: bool
) -> tuple[bool, bool]:
    """``(write_it, preserved_a_customised_one)`` for ``init``'s schema write.

    The two files ``init`` writes are not equally replaceable. The ``.gitignore``
    is a constant this module generates, so losing it costs nothing. The schema
    is the one file in the store that cannot be reconstructed from the
    documents — every type, status and cadence a person decided on lives only
    there — and ``--force`` used to replace both under one flag, so re-running
    ``init`` to refresh the gitignore destroyed that work silently.

    A customised schema is therefore **skipped rather than refused**: the caller
    asked to regenerate the store's files and gets everything safe to
    regenerate, with ``schema_preserved`` saying what was left alone. Raising
    instead would abort before the gitignore was written, which is the one thing
    they could still have had.
    """
    if not schema_path.exists():
        return True, False
    if force_schema:
        # Stands alone: it names the schema specifically, so requiring --force
        # as well meant the more precise flag silently did nothing. Someone
        # replacing the schema should not have to regenerate the gitignore too.
        return True, False
    if not force:
        return False, False
    if schema_path.read_text(encoding="utf-8") == generated:
        return True, False  # identical bytes: rewriting loses nothing
    return False, True
