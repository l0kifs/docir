# Persistence adapters — the derived SQLite index.
#
#   * models        — SQLAlchemy 2.0 declarative rows (documents, relations,
#                     tags, document_tags, embeddings, id sequences).
#   * database      — engine/session factory, FTS5 setup, Alembic migration
#                     runner.
#   * repositories  — concrete implementations of the domain repository ports.
#   * unit_of_work  — the SQLAlchemy-backed transactional UnitOfWork.
#   * alembic       — migration environment and versioned revisions.
