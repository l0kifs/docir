# FLOW-003 — Keep the corpus trustworthy (maintenance, CI, staleness)

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
  → `GAP-003`. This is the single most damaging finding in the run: it fires on the
  documented happy path (`git clone` + `docir reindex`), needs no concurrency, no `--force`,
  and no unusual input.

- **H2 — `check --strict` cannot serve as the CI gate it is sold as.** It exits 1 if *any*
  finding exists, and `orphan` fires for every document with no relations — the default state
  of a newly created document. CONFIRMED: a store with two brand-new unrelated documents
  exits 1. There is no severity, no `--only <kind>`, no ignore file. A team adopting the
  documented CI gate gets a red build on day one and must either link every document or drop
  the gate — which also drops the duplicate-id detection that is the gate's actual purpose.
  → `GAP-006`.

- **H3 — the default profile makes the canonical modelling a permanent warning.** In the
  `software` profile `decision` is level 3 and `issue` is level 1, and the layering check
  flags any non-`supersedes`/`contradicts` edge from a higher to a lower level. So
  `docir add --type decision … --related issue-0001` — the exact pairing in the README's own
  quickstart output (README:78-81) — produces a permanent `layering` finding. CONFIRMED.
  → `GAP-008`.

- **H4 — `check` detects, nothing repairs.** duplicate-id, dangling, malformed and unknown-type
  are all reported and none can be fixed by any command. There is no `docir repair`, no
  `--fix`, no runbook. Every confirmed failure mode in this analysis terminates in a state the
  product cannot exit. → `GAP-012`.

- **H5 — staleness has no route to a human.** `owner` is captured, interpolated into a `check`
  message, and never used again: no notification, no `--owner` query filter, no "documents I
  own" view, no scheduled reminder. The feature detects staleness and then relies entirely on
  someone choosing to run `docir check` and read the output. → `GAP-011`.

- **H6 — an administrative rename resets the trust clock.** `tag rename` and `tag rm --force`
  rewrite every referencing document with `updated = today` (tag_service.py:77, 99). For any
  document without an explicit `verified` date, `stale_reference_date()` falls back to
  `updated` — so renaming a tag makes stale documents look freshly reviewed. A classification
  edit silently launders the staleness signal. → `GAP-020`.

- **H7 — `reindex --changed` never removes deleted documents** (maintenance_service.py:166-174:
  the removal sweep is skipped when `changed_only`). A document deleted from the filesystem
  stays in the index and keeps being returned by every read path until a full reindex.
  Documented nowhere. → `GAP-021`.

- **H8 — malformed files are skipped silently by `reindex`.** `scan()` swallows `ValidationError`
  and continues (markdown_store.py:58-62). `reindex` reports `documents_indexed` with no count
  of files skipped, so a broken file looks like a successful rebuild. Only a separate `check`
  reveals it. → `GAP-022`.

## Off-system steps

- **Resolving every finding `check` can produce.** All manual, all undocumented. This is the
  work of ACT-008 (support / operator), the actor the product never serves.
- **Deciding whether a stale document is still true.** By design (ADR-0006 — human
  re-verification is the honest baseline). Correctly out of system; recorded for completeness.

## Rules

BR-041, BR-042, BR-043, BR-044, BR-045, BR-046, BR-047

## Gaps

GAP-003, GAP-006, GAP-008, GAP-011, GAP-012, GAP-020, GAP-021, GAP-022
