---
code:
- src/docir/modules/documents/domain/services/graph_checks.py
- src/docir/modules/documents/domain/schema.py
created: '2026-08-07'
description: unknown-tag and unknown-status are reported, but an edge carrying an
  unregistered kind is served by get, traversed by context and flagged by nothing;
  only rewriting it is refused.
id: issue-0e3d1d9c81d3
owner: maintainer
related:
- issue-8f6576cd7bc9
- adr-599055502f0e
status: open
tags:
- cosmetic
- schema
title: docir check has no finding for an edge whose relation kind the registry no
  longer knows
type: issue
updated: '2026-08-07'
---

**Class:** missing · **Severity:** cosmetic
**Source:** schema-evolution investigation, 2026-08-07 (sibling of issue-8f6576cd7bc9)
**Step:** narrowing `relation_types` in an inline-only schema · **Frequency:** rare — see *Exposure*

## Finding

`docir check` reports a tag the registry does not know (`unknown-tag`) and a status the type does
not declare (`unknown-status`), but says nothing about an **edge whose kind the registry no longer
knows**. The edge is served by `get`, traversed by `context`, and survives every write that does
not rewrite it.

Reproduced in a throwaway store: an `issue --related <adr>:depends_on`, then a schema declaring
`relation_types: [relates_to, supersedes]`.

```
docir schema show   -> ['relates_to', 'supersedes']
docir check         -> 0 findings;  --strict exit 0
docir get <id>      -> related: [{target: adr-…, kind: 'depends_on'}]
docir update <id> --set-title "B2"
                    -> written; the depends_on edge is still there
docir update <id> --set-related <adr>:depends_on
                    -> error: unknown relation kind 'depends_on'; known kinds: relates_to, supersedes
```

So Tier 0 refuses to *write* the kind while the corpus keeps *holding* it, and the one command
that exists to find that class of drift is silent. `GraphChecker.check` (`graph_checks.py:92`)
never consults `Schema.is_known_relation_kind` (`schema.py:211`), which has exactly one caller —
the write-path validator.

## Exposure

Narrower than it looks, which is why this is filed as cosmetic rather than material.
`_merge_profiled` merges `relation_types` as a **union** (`schema_loader.py:152`), so a schema with
a `profiles:` key can only ever *widen* the registry — the core six are always present and cannot
be removed by editing the file. Reaching the state above takes one of:

- an **inline-only** schema (no `profiles:` key), whose registry is exactly what it declares — the
  reproduction above;
- a release **dropping a kind from `CORE_SCHEMA_YAML`**, which would hit every store at once;
- an edge written by hand into frontmatter with a kind nobody registered.

The third is the same route `unknown-tag` and `unknown-status` exist to cover, and it is covered
for them.

## Impact

Low and bounded: the edge still resolves, and its behaviour is unchanged, because
`Schema.relation_kind` falls back to `CORE_RELATION_KINDS` for any kind the file does not describe
(`schema.py:215`) — so a dropped `depends_on` is still cycle-checked and still read as a
dependency by the layering check. What is lost is the report: the registry has stopped describing
the corpus, and `docir check` — which says so for tags, statuses and types — does not say so here.

## Proposed default

An `unknown-relation-kind` warning in Tier 1, listing the source, the target and the kind. Warning
severity and the same wording shape as `unknown-status`, for the same reason: nothing is broken,
the classification is simply no longer one the schema knows.

Deliberately not proposed: repairing it in `check --fix`. There is no safe substitute kind —
rewriting `depends_on` to `relates_to` would silently drop a dependency claim the layering check
reads, which is a guess about meaning, not a mechanical repair.

## Actors affected

- ACT-002 repository maintainer / developer

## Evidence

- `src/docir/modules/documents/domain/services/graph_checks.py:92` — `check`, no relation-kind pass
- `src/docir/modules/documents/domain/services/graph_checks.py:169,199` — the two sibling findings
- `src/docir/modules/documents/domain/schema.py:211,215` — `is_known_relation_kind`, and the core fallback
- `src/docir/modules/documents/infra/schema_loader.py:152` — `relation_types` merges as a union
