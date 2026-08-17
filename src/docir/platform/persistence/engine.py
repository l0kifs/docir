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
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

_ALEMBIC_DIR = Path(__file__).resolve().parent / "alembic"


#: How long a connection waits for a write lock before giving up. Concurrent
#: ``--no-daemon`` writers serialize on this lock (the daemon serializes them a
#: level up); without a generous timeout the loser raises "database is locked"
#: instead of simply waiting its turn. Matches pysqlite's own default, set
#: explicitly so it is a decision rather than an inherited accident.
_BUSY_TIMEOUT_MS = 5000


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


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory bound to the index engine."""
    return sessionmaker(bind=engine, future=True, expire_on_commit=False)


def run_migrations(database_url: str) -> None:
    """Upgrade the index database to the latest Alembic revision."""
    command.upgrade(_alembic_config(database_url), "head")


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
