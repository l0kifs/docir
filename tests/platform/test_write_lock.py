"""Two processes opening one fresh index: the write lock is taken before the look.

Two first commands in a new `git worktree` both open an index nobody has built
(GitHub #42). pysqlite starts a transaction at the first *write*, so each read
"no tables" or "no rows", and the slower one then created or inserted what the
faster had just committed: ``table alembic_version already exists`` from the
migration, ``UNIQUE constraint failed: tags.key`` from the rebuild.

These pin the lock on both paths and that the ordinary open does not take it.
The rebuild side, with two real openers racing, is in
`tests/modules/documents/test_integration_maintenance.py`.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

from docir.config.settings import Settings
from docir.platform.persistence import engine
from docir.platform.persistence.engine import head_revision, index_revision, run_migrations
from docir.platform.persistence.unit_of_work import UnitOfWork


def _another_process_can_write(db_path: Path) -> bool:
    """Whether a second connection could take the write lock right now.

    ``timeout=0`` so a held lock answers at once instead of waiting it out.
    """
    with closing(sqlite3.connect(db_path, timeout=0, isolation_level=None)) as other:
        try:
            other.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as exc:
            assert "locked" in str(exc)
            return False
        other.execute("ROLLBACK")
        return True


class TestTheMigration:
    def test_it_runs_holding_the_write_lock(
        self, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A second opener blocks until the tables exist rather than creating them too."""
        settings.ensure_directories()
        seen: list[bool] = []
        real_upgrade = engine.command.upgrade

        def probing_upgrade(config: Any, revision: str) -> None:
            seen.append(_another_process_can_write(settings.db_path))
            real_upgrade(config, revision)

        monkeypatch.setattr(engine.command, "upgrade", probing_upgrade)
        run_migrations(settings.database_url)

        assert seen == [False], "the migration ran while another process could write"
        assert index_revision(settings.db_path) == head_revision()

    def test_an_index_at_head_opens_without_taking_it(
        self, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Every open but the first. Locking here would queue every command behind
        whatever is writing — a rebuild, a drain — just to learn nothing changed."""
        settings.ensure_directories()
        run_migrations(settings.database_url)
        # Taking the lock behind the writer below would then raise "database is
        # locked" in a fifth of a second, rather than after five minutes.
        monkeypatch.setattr(engine, "_LOCK_WAIT_MS", 200)

        with closing(sqlite3.connect(settings.db_path, isolation_level=None)) as writer:
            writer.execute("BEGIN IMMEDIATE")
            run_migrations(settings.database_url)
            writer.execute("ROLLBACK")

        assert index_revision(settings.db_path) == head_revision()


class TestTheUnitOfWorkLock:
    def test_it_holds_the_write_lock_until_the_unit_of_work_ends(
        self, settings: Settings, uow_factory: Callable[[], UnitOfWork]
    ) -> None:
        with uow_factory() as uow:
            uow.lock()
            held = not _another_process_can_write(settings.db_path)
        assert held
        assert _another_process_can_write(settings.db_path)

    def test_it_waits_out_a_writer_and_then_reads_what_it_committed(
        self,
        settings: Settings,
        uow_factory: Callable[[], UnitOfWork],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The property the rebuild needs: a read after `lock()` is never older
        than the commit the lock waited for. Without the lock this read answers
        at once, from before the commit — the tag table #42's loser saw empty.

        It also outwaits the ordinary busy timeout, shortened here below the
        writer's hold: what it waits for is usually a whole rebuild."""
        monkeypatch.setattr(engine, "_BUSY_TIMEOUT_MS", 100)
        writer = sqlite3.connect(settings.db_path, isolation_level=None, check_same_thread=False)
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("INSERT INTO tags (key, description) VALUES ('alpha', 'A.')")
        committing = threading.Timer(0.3, writer.execute, ("COMMIT",))
        committing.start()
        try:
            with uow_factory() as uow:
                uow.lock()
                assert uow.tags.get("alpha") is not None
        finally:
            committing.join()
            writer.close()
