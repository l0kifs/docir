---
created: '2026-07-30'
description: '"Is this decision still current?" is the question the relation graph
  most needs to answer, and it is the one direction not traversed.'
id: issue-5bfbc6f2699d
owner: maintainer
related:
- adr-599055502f0e
- arch-f220a644d654
status: resolved
tags:
- retrieval
- material
title: GAP-019 — Expansion follows outgoing edges only, so from a superseded document
  the document that…
type: issue
updated: '2026-07-30'
---

# GAP-019 — Expansion follows outgoing edges only, so from a superseded document the document that…

**Class:** missing · **Severity:** material · **Confidence:** observed
**Flow:** FLOW-002 · **Step:** graph expansion direction
**Question:** Q-017 · **Frequency:** any corpus using supersedes

## Finding

Expansion follows outgoing edges only, so from a superseded document the document that superseded it is unreachable.

## What happens today

`_augment_with_related` calls `uow.documents.outgoing(seed)` only (document_service.py:301). `incoming()` exists and is used solely by delete.

## Impact

"Is this decision still current?" is the question the relation graph most needs to answer, and it is the one direction not traversed. An agent retrieving an old ADR gets no signal that a newer one supersedes it — while the superseding edge sits one hop away, backwards.

## Proposed default

Follow incoming `supersedes`/`contradicts` edges as well, or always include the superseding document when one exists.

## Resolution

FIXED 2026-07-27, as proposed. Expansion now walks incoming `supersedes`/`contradicts` edges as well as outgoing ones, via a `kinds` filter added to `DocumentRepository.incoming` (the method existed and was used only by delete). Successors are placed *first* in each seed's edge list, so under a tight `--expand` budget "what replaces this?" outranks an ordinary link — it is the one neighbour that can invalidate the document the agent is about to act on. `_SUCCESSOR_KINDS` is deliberately a separate constant from the layering check's kind set (then `_NON_DEPENDENCY_KINDS`, since inverted to `_DEPENDENCY_KINDS` by GAP-008); they held the same two kinds that day for unrelated reasons and must be free to diverge. Pinned by test_superseding_decision_is_reached_backwards (`--limit 2 --expand 1`, so the successor can only occupy the graph slot). Attribution verified: reverting only the incoming lookup fails that test and leaves the other two passing. NOT measurable in `benchmarks/`: the corpus contains no `supersedes` edge and no inactive document, so both fixes are invisible to it (0.96/0.88 recall@5 unchanged either side of the change). Recorded as GAP-046 rather than papered over by editing the corpus, which would break comparability with every number recorded before today.

## Actors affected

- AI coding agent

## Evidence

- `src/docir/modules/documents/application/services/document_service.py:297-307`
- `src/docir/platform/persistence/repositories.py:133-135`

---

Migrated from the discovery gap register (GAP-019); the register itself now lives in this store.
