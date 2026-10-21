---
paths:
  - "src/docir/platform/persistence/**"
  - "src/docir/modules/documents/application/services/index_rebuilder.py"
---

# Persistence — Alembic, SQLite, the shared index

The index is derived and rebuildable, but the schema that holds it is not: these two break silently, at a distance from the edit that caused them.

- **Alembic owns the schema and must sit beside the engine.** `run_migrations`
  (`platform/persistence/engine.py`) resolves the migration dir via `Path(__file__).parent /
  "alembic"`; moving `engine.py` without the `alembic/` folder silently breaks migrations. The FTS5
  virtual table is **raw DDL in migration `0001`, not an ORM model** — it is queried through
  SQLAlchemy Core `text()` in `SqlAlchemySearchIndex`. `alembic/` is excluded from ruff/ty/tach/
  coverage on purpose.

- **SQLite foreign keys are enabled per-connection** by a `PRAGMA foreign_keys=ON` event listener in
  `create_index_engine`. The `ON DELETE CASCADE` from `relations`/`document_tags`/`embeddings` to
  `documents` depends on it; a raw connection without that listener will orphan rows.

- **Whatever writes what it has just read takes the write lock first (GitHub #42).** pysqlite
  opens a transaction at the first *write*, so a read before it can predate another process's
  commit. Two first commands in a fresh worktree hit this twice: both migrated an index with
  no tables (`table alembic_version already exists`), and both rebuilt an empty index, the
  loser inserting rows the winner had just committed (`UNIQUE constraint failed: tags.key`).
  So `run_migrations` upgrades inside `BEGIN IMMEDIATE` on the connection it hands Alembic,
  and every rebuild calls `UnitOfWork.lock()` before its first read. Two details look
  redundant and are not. The bootstrap counts documents **twice**, once unlocked and once
  under the lock, and only the second count decides; and `run_migrations` returns early at
  head. Both exist so an open of a built index never takes the lock: locking every open
  would queue every command behind whatever is writing. `begin_immediate` waits
  `_LOCK_WAIT_MS` (five minutes), not the five-second busy timeout, because what holds the
  lock then is a rebuild (~20s at 2,000 documents) and the waiter needs what it produces.
  The migration connection keeps foreign keys **off**: a migration that rebuilds a table
  drops the old one, and with them on the drop cascades.
