# Ports — the abstract interfaces the application depends on and the
# infrastructure implements (Dependency Inversion). No concrete I/O lives here.
#
#   * repositories  — persistence contracts for documents, tags, the FTS
#                     search index, and the embedding store.
#   * unit_of_work  — a transactional boundary aggregating the repositories.
#   * embedder      — turns text into a semantic vector.
#   * scheduler     — schedules and flushes deferred embedding recomputes.
#   * clock         — supplies the current date (injected for testability).
