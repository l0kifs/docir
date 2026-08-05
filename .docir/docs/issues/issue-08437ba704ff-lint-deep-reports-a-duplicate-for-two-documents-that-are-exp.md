---
created: '2026-07-30'
description: 'On docir''s own corpus all 14 duplicate findings are pairs already joined
  by an edge: the relation is the answer to the finding.'
id: issue-08437ba704ff
owner: maintainer
related:
- ref-cb2beaa41604
- arch-0a3c2d6d54a6
- issue-40d1792bc9f9
status: resolved
tags:
- retrieval
- material
title: '`lint --deep` reports a duplicate for two documents that are explicitly related'
type: issue
updated: '2026-08-05'
---

**Class:** unwanted · **Severity:** material
**Flow:** arch-0a3c2d6d54a6 (maintenance) · **Step:** `docir lint --deep`
**Frequency:** every run against a corpus whose related documents are actually linked

## Finding

The `duplicate` heuristic compares every pair of vectors and reports any pair above the
similarity threshold. It does not look at the relation graph, so a pair the author has
explicitly linked — modelled as related, which is the whole point of typed edges — is
reported as a possible DRY violation.

## What happens today

OBSERVED against docir's own 99-document store. `docir lint --deep` returns 21 findings:
14 `duplicate` and 7 `scope-creep`. **All 14 duplicate pairs are already joined by a
`relates_to` edge** — each is a `Q-0NN` question and the `GAP-0NN` it came from, a pair
that by construction restates the same problem and is linked precisely to say so.

## Impact

The finding has no action behind it. "These two documents are similar" is answered by the
edge already in the file: yes, and here is how they relate. Nothing the user can do clears
it except deleting a document or unlinking a correct relation.

This is the failure mode the layering check already had and had to be fixed for
(BR-045/issue-40d1792bc9f9): a heuristic firing on correct, modelled usage teaches people to ignore
the whole command. `lint --deep` is Tier 2 and never blocks, so it is cheaper than the
layering case was — but a check whose every finding on the product's own corpus is
unactionable is a check nobody runs twice, and the `duplicate` heuristic is the one that
would catch a genuine copy-paste.

## Proposed default

Suppress a `duplicate` finding when the two documents are joined by an edge in either
direction: the graph has already answered it. Keep reporting unlinked similar pairs, which
is the case worth surfacing — two documents nobody has noticed are about the same thing.
Verify the way the layering fix was verified: run it against this corpus and confirm the
count drops to the unlinked pairs only, and that a deliberately unlinked duplicate is still
reported.

## Actors affected

- repository maintainer
- AI coding agent

## Evidence

- `src/docir/modules/documents/application/services/maintenance_service.py` (`lint_deep`)
- PROBE-L1 in the 2026-07-30 probe log

## Resolution

FIXED 2026-07-30. `SimilarityLinter.find_duplicates` takes the set of linked pairs and skips any pair joined by a relation in either direction; `MaintenanceService.lint_deep` supplies it from `uow.documents.relations()`. Against docir's own corpus `lint --deep` goes from 21 findings to 8 — all 14 duplicates were linked pairs, which is the measurement that motivated the change. The unlinked case, which is the copy-paste this check exists to catch, is still reported and has its own test: without it, "no duplicates" and "duplicates are never reported" look identical. `linked_pairs` defaults to empty rather than being required, because this is a pure domain service and a caller with no relation graph should get the unfiltered answer rather than a signature it cannot satisfy. Verified by injecting the bug: with the argument dropped at the call site, the integration guard fails.
