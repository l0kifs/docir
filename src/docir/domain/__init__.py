# Domain layer — the innermost Clean Architecture ring.
#
# Contains the enterprise-wide rules of the doc-index system, expressed with
# zero dependencies on frameworks, I/O, or the outer layers:
#
#   * entities      — the core objects with identity (Document, Tag, Relation).
#   * value_objects — immutable, self-validating values (DocId, DocType,
#                     Status, Embedding, and the query/scoring records).
#   * schema        — the per-type grammar (required fields, status enums,
#                     allowed transitions, layering levels) loaded from
#                     docs-schema.yaml but modelled here as domain objects.
#   * ports         — abstract interfaces the application depends on and the
#                     infrastructure implements (repositories, embedder,
#                     scheduler, clock, executor).
#   * services      — pure domain logic that spans entities (validation tiers,
#                     id generation, hybrid scoring, graph checks).
#   * errors        — the domain exception hierarchy.
