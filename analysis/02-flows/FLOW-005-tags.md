# FLOW-005 — Maintain the tag vocabulary

## Backbone

register key → apply to documents → rename across corpus → retire

## Event timeline

| # | Event | Actor | Trigger | Evidence |
|---|-------|-------|---------|----------|
| 1 | TagRegistered | ACT-001/002 | `docir tag add <key> --description` | tag_service.py:43-52 |
| 2 | TagApplied | ACT-001/002 | `docir add --tags` / `update --set-tags` | document_service.py:98, 330-332 |
| 3 | TagRenamed | ACT-002 | `docir tag rename <old> <new>` | tag_service.py:62-82 |
| 4 | TagRemovalBlocked | system | key still in use, no `--force` | tag_service.py:91-96 |
| 5 | TagStripped | system | `docir tag rm <key> --force` | tag_service.py:97-103 |
| 6 | RegistryFileSynced | system | rewrite `docs/tags.yaml` | tag_service.py:107-109 |

Steps 3/5 rewrite every referencing document's file **and** index row inside one transaction —
this is the cross-context write the shared UoW exists for (ADR-0002).

## Hotspots

- **H1 — a tag key has no grammar.** Nothing validates the key's format anywhere: no charset,
  no length, no case rule, no reserved words. `docir tag add "Auth Strategy!"` is accepted.
  Document ids are strictly validated by regex (identifiers.py:21); tag keys, the other
  user-supplied identifier, are not validated at all. The asymmetry is unexplained.
  → `GAP-027`.
- **H2 — rename resets the staleness clock** on every referencing document (`updated=today`,
  tag_service.py:77). See FLOW-003 H6 / `GAP-020`.
- **H3 — no merge operation.** Renaming `auth` → `security` when `security` already exists is
  rejected as "already exists" (tag_service.py:69-70). The obvious vocabulary-consolidation
  operation — merge two tags into one — has no path. Lifecycle checklist item
  "merge/deduplicate two records" is unmet. → `GAP-028`.
- **H4 — `tag list` shows no usage counts.** Nothing tells a maintainer which tags are dead,
  so the registry can only grow. → `GAP-029` (cosmetic).
- **H5 — `tag rm --force` is irreversible and unconfirmed.** It strips the key from every
  document in one shot. `delete --force` at least names the referencing documents in the error
  it bypasses; `tag rm --force` reports only `removed <key>` and never says how many documents
  it rewrote. → `GAP-030`.
- **H6 — tags are not searchable.** They are not in the FTS5 table (migration 0001:88-92 indexes
  title/description/body only) and not in `embedding_text()` (document.py:40-47). They filter
  in `query` and appear in output, but `docir search auth` will not find a document tagged
  `auth`. Reasonable, and nowhere stated. → `GAP-031`.

## Off-system steps

- Deciding the tag vocabulary. Genuinely human; no gap.

## Rules

BR-069, BR-070, BR-071, BR-072

## Gaps

GAP-020, GAP-027, GAP-028, GAP-029, GAP-030, GAP-031
