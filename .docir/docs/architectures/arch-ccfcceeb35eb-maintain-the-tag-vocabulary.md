---
code:
- src/docir/modules/tags/**
code_baseline:
  src/docir/modules/tags/**: 444c47d90798
created: '2026-07-30'
description: How the controlled vocabulary is registered, renamed and retired.
id: arch-ccfcceeb35eb
owner: maintainer
related:
- adr-d3e3616400bf
- arch-0a3c2d6d54a6
- arch-1cfb1b212237
- issue-498cbbaeac2f
- issue-9ed4905e0db8
- issue-a776b08ceaea
- issue-cc61d038cf8f
- issue-d69a47904478
- issue-e71e1ad9b0ef
status: active
tags:
- schema
- tags
title: Maintain the tag vocabulary
type: architecture
updated: '2026-09-22'
verified: '2026-09-22'
verified_code:
  src/docir/modules/tags/**: 444c47d90798
verified_content: 0081494c5568
---

## Backbone

register key → apply to documents → rename across corpus → retire

## Event timeline

| # | Event | Actor | Trigger | Evidence |
|---|-------|-------|---------|----------|
| 1 | TagRegistered | ACT-001/002 | `docir tag add <key> --description` | `TagService.add` |
| 2 | TagApplied | ACT-001/002 | `docir add --tags` / `update --set-tags` | `DocumentService`, tag validation |
| 3 | TagRenamed | ACT-002 | `docir tag rename <old> <new>` | `TagService.rename` |
| 4 | TagRemovalBlocked | system | key still in use, no `--force` | `TagService.remove` |
| 5 | TagStripped | system | `docir tag rm <key> --force` | `TagService.remove`, `--force` |
| 6 | RegistryFileSynced | system | rewrite `docs/tags.yaml` | `TagService._sync_file` |

Steps 3/5 rewrite every referencing document's file **and** index row inside one transaction —
this is the cross-context write the shared UoW exists for (adr-d3e3616400bf).

## Hotspots

- **H1 — a tag key has no grammar.** Nothing validates the key's format anywhere: no charset,
  no length, no case rule, no reserved words. `docir tag add "Auth Strategy!"` is accepted.
  Document ids are strictly validated by regex (`platform.naming`, `DOC_ID_RE`); tag keys, the other
  user-supplied identifier, are not validated at all. The asymmetry is unexplained.
  → `issue-e71e1ad9b0ef`.

### H2 — rename resets the staleness clock

on every referencing document (`updated=today`,
`TagService.rename`). See arch-0a3c2d6d54a6 H6 / `issue-9ed4905e0db8`.

### H3 — no merge operation.

Renaming `auth` → `security` when `security` already exists is
rejected as "already exists" (`TagService.add`). The obvious vocabulary-consolidation
operation — merge two tags into one — has no path. Lifecycle checklist item
"merge/deduplicate two records" is unmet. → `issue-cc61d038cf8f`.

### H4 — tag list shows no usage counts.

Nothing tells a maintainer which tags are dead,
so the registry can only grow. → `issue-498cbbaeac2f` (cosmetic).

### H5 — tag rm --force is irreversible and unconfirmed.

It strips the key from every
document in one shot. `delete --force` at least names the referencing documents in the error
it bypasses; `tag rm --force` reports only `removed <key>` and never says how many documents
it rewrote. → `issue-d69a47904478`.

### H6 — tags are not searchable.

They are not in the FTS5 table (migration 0001:88-92 indexes
title/description/body only) and not in `embedding_text()` (`Document.embedding_text`). They filter
in `query` and appear in output, but `docir search auth` will not find a document tagged
`auth`. Reasonable, and nowhere stated. → `issue-a776b08ceaea`.

## Off-system steps

- Deciding the tag vocabulary. Genuinely human; no gap.

## Rules

BR-069, BR-070, BR-071, BR-072

## Gaps

issue-9ed4905e0db8, issue-e71e1ad9b0ef, issue-cc61d038cf8f, issue-498cbbaeac2f, issue-d69a47904478, issue-a776b08ceaea
