# Domain services — pure logic that spans multiple entities or value objects.
#
#   * slugify        — derive a filesystem slug from a title.
#   * id_generator   — allocate the next `<prefix>-NNNN` id from the index.
#   * validation     — Tier 0 hard checks (required fields, status, transitions,
#                      tag/related referential integrity).
#   * scoring        — hybrid lexical + semantic fusion for `docs context`.
#   * graph_checks   — Tier 1 structural warnings (cycles, orphans, layering).
#   * similarity_lint— Tier 2 advisory checks (content DRY, scope creep).
