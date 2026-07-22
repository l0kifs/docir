"""Engine/session wiring and the Alembic migration runner.

The schema is owned by Alembic (per project requirement). On startup the
composition root calls :func:`run_migrations`, which brings a fresh or existing
index database up to ``head`` — creating the ORM tables and the FTS5 virtual
table in one place.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

_ALEMBIC_DIR = Path(__file__).resolve().parent / "alembic"


def create_index_engine(database_url: str) -> Engine:
    """Create an engine with SQLite foreign-key enforcement enabled."""
    engine = create_engine(database_url, future=True)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory bound to the index engine."""
    return sessionmaker(bind=engine, future=True, expire_on_commit=False)


def run_migrations(database_url: str) -> None:
    """Upgrade the index database to the latest Alembic revision."""
    config = Config()
    config.set_main_option("script_location", str(_ALEMBIC_DIR))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
