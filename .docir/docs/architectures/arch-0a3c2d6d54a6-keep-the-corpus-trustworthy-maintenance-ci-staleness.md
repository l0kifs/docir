---
code:
- .github/workflows/ci.yml
- src/docir/modules/documents/application/services/maintenance_service.py
- src/docir/modules/documents/application/services/store_repairer.py
- src/docir/modules/documents/application/services/index_rebuilder.py
- src/docir/modules/documents/application/services/document_patch.py
- src/docir/modules/documents/domain/services/graph_checks.py
- src/docir/modules/documents/domain/services/checks/**
code_baseline:
  .github/workflows/ci.yml: a4b0e9a8fdd6
  src/docir/modules/documents/application/services/document_patch.py: 5b7b85ac62c7
  src/docir/modules/documents/application/services/index_rebuilder.py: 9b1fe093b10d
  src/docir/modules/documents/application/services/maintenance_service.py: d63801115bf9
  src/docir/modules/documents/application/services/store_repairer.py: 84452625a9b0
  src/docir/modules/documents/domain/services/checks/**: b28b2d4f6708
  src/docir/modules/documents/domain/services/graph_checks.py: 7a789c9edc8d
created: '2026-07-30'
description: 'How the corpus stays consistent: reindex, check, repair, and the merge
  guard.'
id: arch-0a3c2d6d54a6
owner: maintainer
related:
- adr-b2cfed9d5888
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
revoked: '2026-09-22'
status: active
tags:
- integrity
- persistence
title: Keep the corpus trustworthy (maintenance, CI, staleness)
type: architecture
updated: '2026-09-22'
verified_code:
  .github/workflows/ci.yml: a4b0e9a8fdd6
  src/docir/modules/documents/application/services/document_patch.py: 5b7b85ac62c7
  src/docir/modules/documents/application/services/index_rebuilder.py: 9b1fe093b10d
  src/docir/modules/documents/application/services/maintenance_service.py: d63801115bf9
  src/docir/modules/documents/application/services/store_repairer.py: 84452625a9b0
  src/docir/modules/documents/domain/services/checks/**: b28b2d4f6708
  src/docir/modules/documents/domain/services/graph_checks.py: 7a789c9edc8d
---

## Backbone

list the decisions a branch touches → merge branches → rebuild index → check structure →
review stale docs → re-verify → (repair?)

## Event timeline

| # | Event | Actor | Trigger | Evidence |
|---|-------|-------|---------|----------|
| 0 | GoverningDecisionsListed | ACT-003 | `docir query --code <changed files>` on a pull request | .github/workflows/ci.yml:146 |
| 1 | BranchesMerged | ACT-006 | `git merge` | tests/modules/documents/test_merge_safety.py |
| 2 | IndexRebuilt | ACT-002 | `docir reindex [--changed]` | maintenance_service.py:170 (`reindex`) → index_rebuilder.py |
| 3 | StructureChecked | ACT-003 | `docir check [--strict]` | maintenance_service.py:191 (`check`) |
| 4 | DuplicateIdDetected | system | file scan, not index | maintenance_service.py:478 (`_find_duplicate_ids`) |
| 5 | StaleFlagged | system | past `review_days` since `verified`, else `revoked`, else `created` — never `updated` | checks/verification_rules.py:52 (`_find_stale`) |
| 6 | DocumentReVerified | ACT-007 | `docir update <id> --verified` | document_patch.py:134 (`_apply_verification`) |
| 7 | AdvisoryLinted | ACT-002 | `docir lint --deep` | maintenance_service.py:514 (`lint_deep`) |
| 8 | EmbeddingsRebuilt | ACT-002 | `docir embed --flush`, or any full `docir reindex` | maintenance_service.py:182 (`flush_embeddings`) |
| 9 | UnmatchedCodeFlagged | system | a governed `code:` glob matches nothing the repository tracks | checks/verification_rules.py:89 (`_find_unmatched_code`), maintenance_service.py:424 (`_resolve_code`) |
| 9a | UnwatchedCodeFlagged | system | a governed `code:` glob resolves and no digest is watching it, so no edit to it is ever reported | checks/verification_rules.py:137 (`_find_unwatched_code`) |

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
`duplicate-id`/`dangling`/`malformed` (the corpus is broken) plus `empty-index` (the check
could not look — adr-1cccd77cb023); everything else is a `warning` about shape or age. `--strict` gates on errors only; `--strict-all` restores
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
path. It repairs what needs no guess: duplicate ids are re-issued (the *oldest*
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
`updated` — and the clock no longer reads `updated` at all: an unverified document ages from
`created` (or from `revoked`, once a stamp is withdrawn), so no write can launder it
(issue-6726eabcf871). → `issue-9ed4905e0db8`.

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

## check reports what is ready, not only what is wrong

Since 0.18.0 `check` also reports **`unblocked`**: a live document whose every `depends_on`
target has closed. The one finding here that is good news — the work is ready to start.

It exists because the edge was asserted and nothing read it. A `depends_on` claims this work
waits on that work, and until now only `context` expansion followed it, and only when a caller
happened to query nearby — so a blocker could clear and the thing it blocked would sit there
with the graph holding the answer and nobody asking.

A warning, never an error, on the same argument as `stale`: nothing is broken, this is a
scheduling fact, and it is cleared by doing something real rather than by a flag — start the
work, or drop an edge that is no longer true.

Which kinds count is the schema's `blocking` property, not the name `depends_on`. That property
is deliberately separate from `dependency`, which `layering` reads: one is temporal and the
other structural, and reading one for both announced a decision refining a *superseded* one as
ready to start (adr-716c2eeb4e51).

## What check --fix files rather than repairs

Two of `repair`'s actions repair nothing, and qualify on the same two tests: the value is
derived, so there is exactly one answer, and neither claims anything a human must judge.

A `code_baseline` for each `code:` glob that carries none, so drift is watched from that run
onward ([[adr-49bb8cc48938]]). And `store_format:` in `docs-schema.yaml` when the file's
contents need a higher floor than it declares, so a docir that predates the construct refuses
the store by name rather than on a key nobody removed ([[adr-36d6156ffab9]]).

The baseline mint reports one action per document, because the frontmatter of every governed
document moves and the reader has to see that in the diff; the `store_format:` line is one
action against the schema file.
