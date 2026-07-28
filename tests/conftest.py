"""Shared pytest fixtures.

Every fixture keeps the system hermetic by pointing ``DOCIR_HOME`` at a temp
directory and forcing in-process execution. All tests are fully synchronous;
the only async surface (the embedding scheduler) is exercised through its
synchronous ``flush`` interface.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import date

import pytest

from docir.config.settings import Settings
from docir.entry_points.composition import Container, build_container
from docir.entry_points.dispatch import Dispatcher
from docir.platform.clock import Clock
from docir.platform.persistence.engine import (
    create_index_engine,
    create_session_factory,
    run_migrations,
)
from docir.platform.persistence.sqlalchemy_uow import SqlAlchemyUnitOfWork
from docir.platform.persistence.unit_of_work import UnitOfWork

FIXED_DATE = date(2026, 7, 7)


class FixedClock(Clock):
    """A clock frozen to a fixed date for deterministic timestamps."""

    def __init__(self, day: date = FIXED_DATE) -> None:
        self._day = day

    def today(self) -> date:
        return self._day


@pytest.fixture
def settings(tmp_path, monkeypatch) -> Settings:
    home = tmp_path / "docir"
    monkeypatch.setenv("DOCIR_HOME", str(home))
    monkeypatch.setenv("DOCIR_NO_DAEMON", "1")
    # Pin the hashing embedder: the real default downloads a model, which would
    # make the suite slow and network-dependent.
    monkeypatch.setenv("DOCIR_EMBEDDER", "deterministic")
    return Settings.resolve()


@pytest.fixture
def container(settings: Settings) -> Iterator[Container]:
    built = build_container(settings, background_embeddings=False, clock=FixedClock())
    try:
        yield built
    finally:
        built.close()


@pytest.fixture
def dispatcher(container: Container) -> Dispatcher:
    return container.dispatcher


@pytest.fixture
def uow_factory(settings: Settings) -> Iterator[Callable[[], UnitOfWork]]:
    """A migrated, isolated unit-of-work factory for persistence-level tests."""
    settings.ensure_directories()
    run_migrations(settings.database_url)
    engine = create_index_engine(settings.database_url)
    session_factory = create_session_factory(engine)

    def factory() -> UnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture
def seeded(dispatcher: Dispatcher) -> Dispatcher:
    """A dispatcher pre-loaded with two tags and two related documents."""
    dispatcher.dispatch("tag_add", {"key": "auth", "description": "Auth and tokens."})
    dispatcher.dispatch("tag_add", {"key": "api", "description": "HTTP API surface."})
    dispatcher.dispatch(
        "add",
        {
            "type": "decision",
            "title": "Auth strategy",
            "description": "How the service authenticates API clients and refreshes tokens.",
            "tags": ["auth", "api"],
            "body": "We use JWT access tokens with refresh rotation.",
        },
    )
    dispatcher.dispatch(
        "add",
        {
            "type": "issue",
            "title": "Token refresh bug",
            "description": "Refresh token handling fails on renewal.",
            "tags": ["auth"],
            "related": ["adr-0001"],
            "body": "The refresh endpoint returns 500 on token rotation.",
        },
    )
    return dispatcher


@pytest.fixture
def drop_file_of(settings: Settings) -> Callable[[str], None]:
    """Delete a document's markdown file behind docir's back, leaving its edges.

    This is how a dangling reference actually arises: one branch deletes a
    document, another adds a link to it, and the merge produces a file
    referencing an id no file provides. Tests used to reach the same state with
    `delete --force`, which was a shortcut — that command now strips the edges
    it would break (GAP-007), so a dangling edge is only reachable from outside
    the CLI, which is where it always came from in practice.

    Callers must `reindex` afterwards, exactly as the agent guide instructs
    after a merge.
    """

    def drop(doc_id: str) -> None:
        for path in settings.docs_root.rglob(f"{doc_id}-*.md"):
            path.unlink()

    return drop
