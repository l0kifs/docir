# Application services — the use-case classes.
#
# Each public method is one use case, orchestrating domain services and ports
# inside a unit-of-work transaction. Grouped by aggregate/concern:
#
#   * document_service    — add, get, update, query, search, context,
#                           archive/unarchive, delete.
#   * tag_service         — add, list, rename, remove tags (registry + rewrite).
#   * maintenance_service — reindex, check (Tier 1), lint (Tier 2), embed flush.
