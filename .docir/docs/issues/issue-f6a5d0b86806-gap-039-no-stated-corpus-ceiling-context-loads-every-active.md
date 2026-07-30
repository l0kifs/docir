---
created: '2026-07-30'
description: Fine at the 'thousands of documents' scale the id-entropy comment assumes
  (identifiers.py:23-25).
id: issue-f6a5d0b86806
owner: maintainer
related:
- adr-ab9c454b760c
- arch-f220a644d654
status: resolved
tags:
- retrieval
- cosmetic
title: GAP-039 — No stated corpus ceiling. `context` loads every active embedding
  into memory per call…
type: issue
updated: '2026-07-30'
---

# GAP-039 — No stated corpus ceiling. `context` loads every active embedding into memory per call…

**Class:** unstated · **Severity:** cosmetic · **Confidence:** observed
**Flow:** FLOW-002 · **Step:** scale
**Question:** None · **Frequency:** n/a

## Finding

No stated corpus ceiling. `context` loads every active embedding into memory per call and `lint --deep` is O(n²) over them; neither is paginated, capped or benchmarked.

## What happens today

repositories.py:309-320 selects all active vectors; similarity_lint.py:36-40 compares every pair.

## Impact

Fine at the 'thousands of documents' scale the id-entropy comment assumes (identifiers.py:23-25). That assumption is stated in a comment about ids and nowhere else.

## Proposed default

State the supported corpus size in the README.

## Resolution

FIXED 2026-07-29 properly, at the maintainer's direction, who expects much larger corpora than the "thousands of documents" the original assumption allowed for. Pagination is real, not documented-away. `query` and `search` take `--limit`/`--offset`, and `tag list` — which had no window at all — now pages too. `query`'s window is a SQL LIMIT/OFFSET applied *in* the statement: it previously fetched every match and sliced in Python, so the cost of a page grew with the corpus behind it. `DocumentFilter` carries the window, and `limit=None` still means "everything" for the maintenance paths, which genuinely need every row. TWO PREDICATES CANNOT USE A SQL WINDOW, and both would have been silently wrong: `--stale` derives from the clock and the type's cadence, and `search`'s status filter runs after FTS5 (which cannot see a status). A SQL OFFSET on either would count *rows scanned* rather than rows returned — the same class of ordering bug GAP-011 fixed once for `--limit`. Both page over the filtered set instead, and the stale path is pinned by a fixture that interleaves overdue and fresh documents, which a naive window mis-pages. NO TOTAL IN THE RESPONSE: it is a bare JSON array with nowhere to put one, and a wrapper would break every caller. A page shorter than `--limit` means the end; stated in the CLI help, the guide and the README. STILL UNBOUNDED, and stated rather than hidden: `context` loads every current embedding per call, which is what sets the practical corpus ceiling — capping it would break the semantic recall that ADR-0011 exists for. `lint --deep` remains O(n²) over those vectors. Both are now named in the README's "Scope and limits" instead of living in a comment about id entropy.

## Actors affected

- AI coding agent
- repository maintainer

## Evidence

- `src/docir/platform/persistence/repositories.py:309-320`
- `src/docir/modules/documents/domain/services/similarity_lint.py:33-53`

---

Migrated from the discovery gap register (GAP-039); the register itself now lives in this store.
