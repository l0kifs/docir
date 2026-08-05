---
created: '2026-07-23'
description: Why relation edges carry a kind, and how the on-disk form stays backward
  compatible.
id: adr-599055502f0e
owner: maintainer
related:
- kind: refines
  to: arch-1cfb1b212237
status: accepted
tags:
- schema
- persistence
title: Typed relation edges + per-type allowed relations
type: decision
updated: '2026-08-05'
---

## Context
`related` was a flat list of ids: every edge meant the same undifferentiated
"is related to". Agents got graph traversal but not graph *semantics* — there
was no way to say `supersedes`, `depends_on`, `implements`, or `contradicts`,
and the schema (which already constrains fields and status transitions) could
not constrain relations. "supersedes" was only expressible as a *status*
(`superseded`) on the source, losing the pointer to the successor.

## Decision
Give every edge a **kind**. A document's `related` entries become typed edges
(`RelatedRef{target, kind}`); the CLI/compact form is `<id>` (default
`relates_to`) or `<id>:<kind>`; the frontmatter form is a bare id (default) or a
`{to, kind}` mapping. The valid kinds are a schema-level registry
(`relation_types`), mirroring the tag registry — an unknown kind is a Tier 0
error. A type may further constrain its edges with
`allowed_relations: {kind: [target types]}` (a whitelist; empty target list = any
type). Tier 1 layering treats `supersedes`/`contradicts` as lateral, not
dependencies.

Storage: `relations.kind` is a **non-key** column — at most one edge kind per
ordered `(source, target)` pair. Migration `0002` adds it with a
`relates_to` default, so edges indexed before typed relations keep their meaning
and no reindex is forced.

Backward compatibility: `relation_types` is *permissive when empty*. Schemas that
predate typed edges (no `relation_types`) accept any kind; the bundled schema
ships the registry via the core, so new installs get enforcement.

## Consequences
- Easier: exact, cheap, *typed* traversal; the schema can express real relation
  semantics; embeddings stay the fallback, not the primary path.
- Harder: the `related` on-disk shape now has two forms (bare / mapping); the
  parser and renderer handle both, and default-kind edges still render bare so
  old files round-trip byte-for-byte.
- Constraint: one kind per ordered pair (kind is not in the primary key). Two
  differently-typed edges between the same two docs in the same direction are
  not representable; this keeps migration `0002` a plain additive `add_column`.
