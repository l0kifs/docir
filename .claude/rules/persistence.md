---
paths:
  - "src/docir/platform/persistence/**"
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
