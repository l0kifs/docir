---
code:
- src/docir/modules/documents/application/services/maintenance_service.py
- src/docir/modules/documents/domain/services/graph_checks.py
- .github/workflows/ci.yml
created: '2026-07-30'
description: 'How the corpus stays consistent: reindex, check, repair, and the merge
  guard.'
id: arch-0a3c2d6d54a6
owner: maintainer
related:
- adr-bd7c4f3c5764
- arch-1cfb1b212237
- issue-40d1792bc9f9
- issue-476b4e188fab
- issue-5f979576ef7d
- issue-9cb85759076d
- issue-9ed4905e0db8
- issue-b4f441c7210f
- issue-b7ddde3ce860
- issue-c33edcf431fa
- adr-b2cfed9d5888
status: active
tags:
- integrity
- persistence
title: Keep the corpus trustworthy (maintenance, CI, staleness)
type: architecture
updated: '2026-08-17'
---

## Backbone

list the decisions a branch touches → merge branches → rebuild index → check structure →
review stale docs → re-verify → (repair?)

## Event timeline

| # | Event | Actor | Trigger | Evidence |
|---|-------|-------|---------|----------|
| 0 | GoverningDecisionsListed | ACT-003 | `docir query --code <changed files>` on a pull request | .github/workflows/ci.yml:83-97 |
| 1 | BranchesMerged | ACT-006 | `git merge` | tests/modules/documents/test_merge_safety.py |
| 2 | IndexRebuilt | ACT-002 | `docir reindex [--changed]` | maintenance_service.py:58-69 |
| 3 | StructureChecked | ACT-003 | `docir check [--strict]` | maintenance_service.py:84-100 |
| 4 | DuplicateIdDetected | system | file scan, not index | maintenance_service.py:109-124 |
| 5 | StaleFlagged | system | past `review_days` since `verified`/`updated` | graph_checks.py:84-111 |
| 6 | DocumentReVerified | ACT-007 | `docir update <id> --verified` | document_service.py:341-342 |
| 7 | AdvisoryLinted | ACT-002 | `docir lint --deep` | maintenance_service.py:126-134 |
| 8 | EmbeddingsRebuilt | ACT-002 | `docir embed --flush`, or any full `docir reindex` | maintenance_service.py:71-82 |
| 9 | UnmatchedCodeFlagged | system | a governed `code:` glob matches nothing on disk | graph_checks.py:124-166, maintenance_service.py:159-169 |

### Why event 0 is numbered from zero

Event 0 is numbered from zero because it happens *before* the flow this document was written
around: it is the only step that runs while the change is still a proposal, and it is a
**notice, not a gate** (adr-b2cfed9d5888). Everything below it runs on a corpus that has already
been changed; event 0 runs on the change itself, and the only thing it can do is tell a reviewer
what to read.

### Event 9 — the code half of the same linkage

Event 9 is the code half of the same linkage. It reports a document whose governed code moved or
was deleted — including a decision bound to the test that enforced it, which is how "the rule is
a test" notices that the rule is gone. A `warning`, like staleness: the corpus is intact and a
pattern is out of date.

## Hotspots

Eight hotspots were confirmed by the 2026-07-26 discovery pass against v0.2.1
(`ref-9e4cce368b80`). **All eight are closed.** They are kept here as the record of what
the corpus looked like before the maintenance surface existed — read each one's *Closed*
line for the behaviour that ships today, and the linked issue for the argument.

### H1 — reindex did not restore the id counter

The index is documented as fully
rebuildable from files (thesis #1), and `id_sequences` is part of the index. Rebuilding it
lost the counter, so the next `add` re-minted a live id. CONFIRMED end to end: after
clone→reindex→add, two files claimed `adr-0001` and the *older* document became invisible to
`get`, `query`, `search` and `context` while its file remained on disk. This was the single
most damaging finding in the run: it fired on the documented happy path (`git clone` +
`docir reindex`), needed no concurrency, no `--force`, and no unusual input.

*Closed* — `reindex` now raises each prefix to `max(numeric suffix on disk) + 1`
(`_restore_id_sequences`, monotonic), backed by two further guards: `IdGenerator` skips a
candidate already indexed, and a create refuses to write when a file already claims the id
(`DuplicateDocumentIdError`). → `issue-b7ddde3ce860`.

### H2 — check --strict could not serve as the CI gate it was sold as

It exited 1 if
*any* finding existed, and `orphan` fires for every document with no relations — the default
state of a newly created document. CONFIRMED: a store with two brand-new unrelated documents
exited 1. A team adopting the documented CI gate got a red build on day one and had to
either link every document or drop the gate — which also dropped the duplicate-id detection
that is the gate's actual purpose.

*Closed* — findings carry a `severity` derived from their kind. `ERROR_KINDS` is
`duplicate-id`/`dangling`/`malformed` (the corpus is broken); everything else is a
`warning` about shape or age. `--strict` gates on errors only; `--strict-all` restores
fail-on-anything for anyone who wants it. → `issue-9cb85759076d`.

### H3 — the default profile made the canonical modelling a permanent warning

In the
`software` profile `decision` is level 3 and `issue` is level 1, and the layering check
flagged any non-`supersedes`/`contradicts` edge from a higher to a lower level. So
`docir add --type decision … --related issue-0001` — the exact pairing in the README's own
quickstart — produced a permanent `layering` finding. CONFIRMED.

*Closed* — layering now reads only edges the schema marks `dependency`
(`_find_layering_violations` consults `is_dependency_relation`), so an ordinary
`relates_to` link from a decision to the issue that motivated it is silent.
→ `issue-40d1792bc9f9`.

### H4 — check detected, nothing repaired

duplicate-id, dangling, malformed and
unknown-type were all reported and none could be fixed by any command. Every confirmed
failure mode in this analysis terminated in a state the product could not exit.

*Closed* — `docir check --fix` (`MaintenanceService.repair`) is the sanctioned recovery
path. It repairs exactly what needs no guess: duplicate ids are re-issued (the *oldest*
file keeps the id, so existing edges stay valid) and dangling edges are dropped. It
reindexes first and does not advance `updated`. `malformed` and `unknown-type` are still
left unrepaired deliberately and come back in `RepairResult.remaining` — each needs
somebody to read something and decide what the file or the schema should say, and a
repair has nothing to read with. `run-22e0a6ce6ae1` and
`run-f4a756206fe0` are the runbooks. → `issue-476b4e188fab`.

### H5 — staleness had no route to a human

`owner` was captured, interpolated into a
`check` message, and never used again: no `--owner` query filter, no "documents I own"
view.

*Closed* — `query --owner X --stale` is the review queue and `update <id> --verified`
clears an entry. `--stale` is applied before `--limit`, so `--stale --limit 10` means ten
overdue documents. Delivery stays **pull, not push**: there is deliberately no notifier or
scheduler, because an automated nag a bot can clear is not somebody vouching for content.
→ `issue-b4f441c7210f`.

### H6 — an administrative rename reset the trust clock

`tag rename` and `tag rm --force`
rewrote every referencing document with `updated = today`. For any document without an
explicit `verified` date, staleness falls back to `updated` — so renaming a tag made stale
documents look freshly reviewed.

*Closed* — `TagService` has **no `Clock`**: it was injected only to stamp the date it must
not stamp (`tag_service.py`). The tag paths rewrite the classification and leave `updated`
alone, alongside `check --fix` and `delete --force`. Only a content edit moves
`updated`. → `issue-9ed4905e0db8`.

### H7 — reindex --changed never removed deleted documents

The removal sweep was skipped
when `changed_only`, so a document deleted from the filesystem stayed in the index and kept
being returned by every read path until a full reindex.

*Closed* — the sweep runs in **both** modes (`_reindex_documents`); `--changed` now only
skips re-saving files whose content is unchanged. Both modes leave the index agreeing with
the filesystem. → `issue-c33edcf431fa`.

### H8 — malformed files were skipped silently by reindex

`scan()` swallowed
`ValidationError` and continued, and `reindex` reported `documents_indexed` with no count of
files skipped, so a broken file looked like a successful rebuild.

*Closed* — `ReindexResult.documents_skipped` counts source files that will not parse and is
printed by the CLI; a non-zero value means run `check`, which names each file.
→ `issue-5f979576ef7d`.

## Off-system steps

- **Resolving every finding `check` can produce.** All manual, all undocumented. This is the
  work of ACT-008 (support / operator), the actor the product never serves.
- **Deciding whether a stale document is still true.** By design (adr-bd7c4f3c5764 — human
  re-verification is the honest baseline). Correctly out of system; recorded for completeness.

## Rules

BR-041, BR-042, BR-043, BR-044, BR-045, BR-046, BR-047

## Gaps

issue-b7ddde3ce860, issue-9cb85759076d, issue-40d1792bc9f9, issue-b4f441c7210f, issue-476b4e188fab, issue-9ed4905e0db8, issue-c33edcf431fa, issue-5f979576ef7d
