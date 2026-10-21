"""Engine/session wiring and the Alembic migration runner.

The schema is owned by Alembic (per project requirement). On startup the
composition root calls :func:`run_migrations`, which brings a fresh or existing
index database up to ``head`` — creating the ORM tables and the FTS5 virtual
table in one place.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from functools import cache
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from docir.platform.errors import UnknownIndexRevisionError

_ALEMBIC_DIR = Path(__file__).resolve().parent / "alembic"


#: How long a connection waits for a write lock before giving up. Concurrent
#: ``--no-daemon`` writers serialize on this lock (the daemon serializes them a
#: level up); without a generous timeout the loser raises "database is locked"
#: instead of simply waiting its turn. Matches pysqlite's own default, set
#: explicitly so it is a decision rather than an inherited accident.
_BUSY_TIMEOUT_MS = 5000

#: How long :func:`begin_immediate` waits for the write lock. Not
#: `_BUSY_TIMEOUT_MS`: what holds the lock then is usually another process's
#: rebuild, which takes as long as the corpus is big (~20s at 2,000 documents),
#: and the waiter needs exactly what that rebuild is producing. Finite, so a
#: process stopped while holding the lock is an error rather than a hang.
_LOCK_WAIT_MS = 300_000


def create_index_engine(database_url: str) -> Engine:
    """Create an engine with SQLite foreign-key enforcement enabled."""
    engine = create_engine(database_url, future=True)

    @event.listens_for(engine, "connect")
    def _configure_connection(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        cursor.close()

    return engine


def begin_immediate(connection: Connection) -> None:
    """Open the transaction holding the write lock, before anything is read.

    pysqlite opens a transaction lazily, at the first write, so whatever was
    read before it may be older than what another process has committed since.
    Waits up to `_LOCK_WAIT_MS` for the lock, then puts the ordinary busy
    timeout back for the statements that follow.
    """
    connection.exec_driver_sql(f"PRAGMA busy_timeout={_LOCK_WAIT_MS}")
    try:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
    finally:
        connection.exec_driver_sql(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory bound to the index engine."""
    return sessionmaker(bind=engine, future=True, expire_on_commit=False)


def run_migrations(database_url: str) -> None:
    """Upgrade the index database to the latest Alembic revision.

    An index stamped with a revision this build does not ship is refused here,
    by name, before Alembic sees it (issue-38a4f13b1e61). Alembic's own answer
    is ``CommandError: Can't locate revision identified by '0009'`` — a raw
    traceback naming neither the store, nor the two builds, nor what to do — and
    it comes out of *every* command that opens the index, because the
    composition root migrates on open. ``reindex`` and ``doctor`` are the
    documented repair paths, so the one state that needs them was the one state
    they could not run in.

    The condition is already detectable: :func:`known_revisions` and
    :func:`index_revision` exist for the federation peer check, which asks this
    exact question of *someone else's* store and never asked it of this one.

    An index already at head is left alone without taking a lock, because that
    is every open but the first. Anything else is upgraded under the write lock
    (:func:`_upgrade_under_lock`).
    """
    db_path = _database_path(database_url)
    recorded = index_revision(db_path)
    if recorded is not None and recorded not in known_revisions():
        raise UnknownIndexRevisionError(
            f"the index at {db_path} is at schema {recorded}, "
            f"which this docir ({head_revision()} is its newest) does not ship — it was "
            "built by a newer docir. Use that one, or rebuild the index for this build "
            "with `docir reindex` after deleting it (the newer build will migrate it "
            "again the next time it runs)"
        )
    if recorded == head_revision():
        return
    _upgrade_under_lock(database_url)


def _upgrade_under_lock(database_url: str) -> None:
    """Run the migrations inside one transaction that holds the write lock.

    pysqlite runs DDL outside a transaction, so two processes opening the same
    fresh index — two first commands in a new `git worktree` — each read "no
    version table" and each created the tables: the slower one failed with
    ``table alembic_version already exists`` or ``table documents already
    exists`` (GitHub #42). ``BEGIN IMMEDIATE`` makes the second wait for the
    first to commit and then find the index at head, where Alembic does nothing.

    Not :func:`create_index_engine`: foreign keys stay off here, as they always
    were for migrations, because a migration that rebuilds a table drops the old
    one, and with them on the drop cascades into every row that references it.
    """
    engine = create_engine(database_url, poolclass=NullPool, future=True)
    try:
        with engine.connect() as connection, connection.begin():
            begin_immediate(connection)
            config = _alembic_config(database_url)
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    finally:
        engine.dispose()


def _database_path(database_url: str) -> Path:
    """The file behind a ``sqlite:///`` URL.

    Only the shape :attr:`Settings.database_url` produces is understood; anything
    else yields a path that does not exist, which :func:`index_revision` reports
    as "cannot say" — the same answer as a store with no index yet, and the
    answer that lets the upgrade proceed.
    """
    return Path(database_url.removeprefix("sqlite:///"))


def _alembic_config(database_url: str = "") -> Config:
    config = Config()
    config.set_main_option("script_location", str(_ALEMBIC_DIR))
    if database_url:
        config.set_main_option("sqlalchemy.url", database_url)
    return config


@cache
def known_revisions() -> frozenset[str]:
    """Every migration revision this build ships.

    Cached: the answer is a property of the installed package, and the peer
    check asks it once per peer per command.
    """
    scripts = ScriptDirectory.from_config(_alembic_config())
    return frozenset(script.revision for script in scripts.walk_revisions())


@cache
def head_revision() -> str:
    """The revision a freshly migrated index sits at."""
    return str(ScriptDirectory.from_config(_alembic_config()).get_current_head())


def index_revision(db_path: Path) -> str | None:
    """The revision an index database is stamped with, or ``None`` if unknown.

    Read with a bare read-only sqlite connection rather than through the engine:
    this is asked of *peer* stores, before deciding whether to open one at all,
    and building an engine to find out whether a store is usable inverts the
    order. ``None`` covers a database with no ``alembic_version`` row and one
    that will not open — both mean "cannot say", and the caller treats that as a
    reason to skip rather than as permission to proceed.
    """
    try:
        with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as conn:
            row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    except sqlite3.Error:
        return None
    return None if row is None else str(row[0])
