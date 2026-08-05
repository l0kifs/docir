---
created: '2026-07-30'
description: A harness that cannot move is read as "no regression" when it means "not
  measured".
id: issue-f1727f4cf63b
owner: maintainer
related:
- adr-ab9c454b760c
- arch-f220a644d654
- ref-1509d5dbb4c3
- issue-8c37bf22ba3c
- issue-e183d47cdee1
- issue-5bfbc6f2699d
status: resolved
tags:
- embeddings
- material
title: The benchmark corpus has no `supersedes` edge and no inactive document, so
  both go unmeasured
type: issue
updated: '2026-08-05'
---

**Class:** missing · **Severity:** material
**Flow:** arch-f220a644d654 · **Step:** measuring a retrieval change
**Question:** None · **Frequency:** every retrieval change touching the graph

## Finding

The benchmark corpus contains no `supersedes` edge and no document in an inactive status, so the two graph behaviours `docir context` most depends on are structurally invisible to the only measurement the project has.

## What happens today

OBSERVED 2026-07-27. The issue-8c37bf22ba3c + issue-5bfbc6f2699d fixes changed retrieval semantics on both the visibility and the traversal path, and every benchmark number was byte-identical either side of them (recall@5 0.96 fastembed / 0.88 deterministic). All 20 documents use bare `related:` ids, which resolve to `relates_to`, and all statuses are type defaults.

## Impact

A harness that cannot move is read as "no regression" when it means "not measured". The same blindness applies to any future change to expansion, visibility or relation kinds — the parts of `context` that distinguish it from `search`, and therefore the parts most worth a regression signal. issue-e183d47cdee1 was closed by building this harness; this is the boundary of what it closed.

## Proposed default

Add a superseded/superseding decision pair and one closed issue to `corpus.yaml`, with tasks that discriminate them (e.g. "is the Redis session decision still current?"). Note that this re-bases every recorded number, so publish the new baseline in the same commit and mark the old figures as pre-rebase rather than editing them away.

## Resolution

FIXED 2026-07-27, as proposed, at the maintainer's direction. `corpus.yaml` gains `adr-sessions-redis` / `adr-sessions-postgres` (linked by a `supersedes` edge) and the resolved `issue-session-loss`; `tasks.yaml` gains T13/T14, which judge the successor relevant alongside the document it replaces. The loader learned two things it needed for that: typed `related` entries (`key:kind`) and `status_path`, a list of legal transitions walked in order — a path rather than a value because `decision` starts at `proposed`, and walked rather than forced with `--override` so the corpus stays one the CLI would accept. `adr-sessions-redis` is deliberately left `accepted`: a correctly-superseded document is filtered from `context` by status, so it can demonstrate nothing about traversal, and the document nobody went back to close is the realistic case anyway. The harness now moves. Measured by reverting each fix against the new corpus: `context` recall@5 0.93 -> 0.96 (prec 0.37 -> 0.39) under fastembed and 0.89 -> 0.93 (0.36 -> 0.37) under the fallback. Recall and precision move together, as expected: the successor arrives and the resolved issue stops taking a slot. Baseline re-based: 23 documents / 14 tasks, published in benchmarks/README.md with the old 20/12 figures marked pre-rebase rather than deleted. SIDE EFFECT, recorded because it cuts against a previous conclusion: the re-based corpus weakens the *headline* argument for adr-ab9c454b760c (full `context` 0.96 vs 0.93, where it was 0.96 vs 0.88) because graph expansion lifts both embedders. The argument is stronger at `--expand 0`, which isolates the ranking: the fallback scores 0.80, *below* the 0.83 plain `search` manages alone, while the model scores 0.87. README and CLAUDE.md now quote that pair instead. The conclusion did not change; the evidence for it did.

## Actors affected

- repository maintainer

## Evidence

- `benchmarks/corpus.yaml`
- `ref-1509d5dbb4c3 (discovery probe log)`

---

Migrated from the discovery gap register (GAP-046); the register itself now lives in this store.
