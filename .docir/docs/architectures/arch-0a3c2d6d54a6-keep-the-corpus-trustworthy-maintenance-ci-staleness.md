---
created: '2026-07-30'
description: 'How the corpus stays consistent: reindex, check, repair, and the merge
  guard.'
id: arch-0a3c2d6d54a6
owner: maintainer
related:
- arch-1cfb1b212237
- adr-bd7c4f3c5764
- issue-9ed4905e0db8
status: active
tags:
- integrity
- persistence
title: Keep the corpus trustworthy (maintenance, CI, staleness)
type: architecture
updated: '2026-08-05'
---

## Backbone

merge branches → rebuild index → check structure → review stale docs → re-verify → (repair?)

## Event timeline

| # | Event | Actor | Trigger | Evidence |
|---|-------|-------|---------|----------|
| 1 | BranchesMerged | ACT-006 | `git merge` | tests/modules/documents/test_merge_safety.py |
| 2 | IndexRebuilt | ACT-002 | `docir reindex [--changed]` | maintenance_service.py:58-69 |
| 3 | StructureChecked | ACT-003 | `docir check [--strict]` | maintenance_service.py:84-100 |
| 4 | DuplicateIdDetected | system | file scan, not index | maintenance_service.py:109-124 |
| 5 | StaleFlagged | system | past `review_days` since `verified`/`updated` | graph_checks.py:84-111 |
| 6 | DocumentReVerified | ACT-007 | `docir update <id> --verified` | document_service.py:341-342 |
| 7 | AdvisoryLinted | ACT-002 | `docir lint --deep` | maintenance_service.py:126-134 |
| 8 | EmbeddingsRebuilt | ACT-002 | `docir reindex --embeddings` / `docir embed --flush` | maintenance_service.py:71-82 |

## Hotspots

- **H1 — `reindex` does not restore the id counter.** The index is documented as fully
  rebuildable from files (README:34, thesis #1), and `id_sequences` is part of the index.
  Rebuilding it loses the counter, so the next `add` re-mints a live id. CONFIRMED end to end:
  after clone→reindex→add, two files claimed `adr-0001` and the *older* document became
  invisible to `get`, `query`, `search` and `context` while its file remained on disk.
  → `issue-b7ddde3ce860`. This is the single most damaging finding in the run: it fires on the
  documented happy path (`git clone` + `docir reindex`), needs no concurrency, no `--force`,
  and no unusual input.

- **H2 — `check --strict` cannot serve as the CI gate it is sold as.** It exits 1 if *any*
  finding exists, and `orphan` fires for every document with no relations — the default state
  of a newly created document. CONFIRMED: a store with two brand-new unrelated documents
  exits 1. There is no severity, no `--only <kind>`, no ignore file. A team adopting the
  documented CI gate gets a red build on day one and must either link every document or drop
  the gate — which also drops the duplicate-id detection that is the gate's actual purpose.
  → `issue-9cb85759076d`.

- **H3 — the default profile makes the canonical modelling a permanent warning.** In the
  `software` profile `decision` is level 3 and `issue` is level 1, and the layering check
  flags any non-`supersedes`/`contradicts` edge from a higher to a lower level. So
  `docir add --type decision … --related issue-0001` — the exact pairing in the README's own
  quickstart output (README:78-81) — produces a permanent `layering` finding. CONFIRMED.
  → `issue-40d1792bc9f9`.

- **H4 — `check` detects, nothing repairs.** duplicate-id, dangling, malformed and unknown-type
  are all reported and none can be fixed by any command. There is no `docir repair`, no
  `--fix`, no runbook. Every confirmed failure mode in this analysis terminates in a state the
  product cannot exit. → `issue-476b4e188fab`.

- **H5 — staleness has no route to a human.** `owner` is captured, interpolated into a `check`
  message, and never used again: no notification, no `--owner` query filter, no "documents I
  own" view, no scheduled reminder. The feature detects staleness and then relies entirely on
  someone choosing to run `docir check` and read the output. → `issue-b4f441c7210f`.

- **H6 — an administrative rename resets the trust clock.** `tag rename` and `tag rm --force`
  rewrite every referencing document with `updated = today` (tag_service.py:77, 99). For any
  document without an explicit `verified` date, `stale_reference_date()` falls back to
  `updated` — so renaming a tag makes stale documents look freshly reviewed. A classification
  edit silently launders the staleness signal. → `issue-9ed4905e0db8`.

- **H7 — `reindex --changed` never removes deleted documents** (maintenance_service.py:166-174:
  the removal sweep is skipped when `changed_only`). A document deleted from the filesystem
  stays in the index and keeps being returned by every read path until a full reindex.
  Documented nowhere. → `issue-c33edcf431fa`.

- **H8 — malformed files are skipped silently by `reindex`.** `scan()` swallows `ValidationError`
  and continues (markdown_store.py:58-62). `reindex` reports `documents_indexed` with no count
  of files skipped, so a broken file looks like a successful rebuild. Only a separate `check`
  reveals it. → `issue-5f979576ef7d`.

## Off-system steps

- **Resolving every finding `check` can produce.** All manual, all undocumented. This is the
  work of ACT-008 (support / operator), the actor the product never serves.
- **Deciding whether a stale document is still true.** By design (adr-bd7c4f3c5764 — human
  re-verification is the honest baseline). Correctly out of system; recorded for completeness.

## Rules

BR-041, BR-042, BR-043, BR-044, BR-045, BR-046, BR-047

## Gaps

issue-b7ddde3ce860, issue-9cb85759076d, issue-40d1792bc9f9, issue-b4f441c7210f, issue-476b4e188fab, issue-9ed4905e0db8, issue-c33edcf431fa, issue-5f979576ef7d
