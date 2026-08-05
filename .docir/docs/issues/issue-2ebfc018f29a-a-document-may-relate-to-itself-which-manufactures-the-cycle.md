---
created: '2026-07-30'
description: Tier 0 accepts a self-edge; `docir check` then reports a one-node cycle
  that no edit but removing the edge can clear.
id: issue-2ebfc018f29a
owner: maintainer
related:
- ref-cb2beaa41604
- arch-0a3c2d6d54a6
- arch-3e305bc76ff0
- issue-9bbca6c0f434
status: resolved
tags:
- integrity
- material
title: A document may relate to itself, which manufactures the cycle warning `check`
  exists to report
type: issue
updated: '2026-08-05'
---

**Class:** unusual · **Severity:** material
**Flow:** arch-3e305bc76ff0 (authoring) into arch-0a3c2d6d54a6 (integrity)
**Frequency:** unknown; one mistyped id away on any `update --set-related`

## Finding

Nothing rejects an edge from a document to itself. Tier 0 checks that the target exists and
that the kind is registered; a document is its own valid target, so `X -> X` passes.

## What happens today

OBSERVED. `docir update adr-eb5fe750a588 --set-related adr-eb5fe750a588:relates_to` exits 0
and writes `related: [{to: adr-eb5fe750a588, kind: relates_to}]`. `docir check` then reports
`relation cycle: adr-... -> adr-...`. The write path produced the finding the check path
exists to report, and no edit clears it except removing the edge again.

## Impact

Same shape as issue-9bbca6c0f434, where `tag rename X X` reported success, deleted the tag and left
every document carrying it — a self-operation nobody had asked "what if they are the same?"
about. That one was fixed by rejecting the degenerate case:
`ValidationError: cannot rename tag 't' to itself`. The identical degenerate case one
module away is still accepted.

A self-edge also carries no meaning. `related` answers "what else should I read", and the
answer can never be the document already in hand; graph expansion cannot follow it anywhere.
So there is no usage to preserve by allowing it.

## Proposed default

Reject at Tier 0 in the relation validator, the way an unknown kind and an unknown target
already are: `cannot relate a document to itself`. Add it to the same test class that pins
the tag self-merge, and confirm the guard by injecting the bug.

## Actors affected

- AI coding agent
- repository maintainer

## Evidence

- `src/docir/modules/documents/domain/services/validation.py` (related-reference validation)
- `src/docir/modules/documents/domain/services/graph_checks.py` (`_find_cycles`)
- PROBE-R3 / PROBE-R3b in the 2026-07-30 probe log

## Resolution

FIXED 2026-07-30. Tier 0 rejects an edge whose target is the document itself, on both write paths: `update --set-related` and `add --id` (the only way `add` can name its own id, since an allocated one is not known to the caller). The error is a plain `ValidationError` — `cannot relate document 'adr-...' to itself` — matching `cannot rename tag 't' to itself`, because it is the same degenerate case that issue-9bbca6c0f434 was: a feature whose tests only ever used two different values. The self check runs *before* the existence check so the message names the real problem; on `add --id` the document is not yet indexed and "does not exist in the index" would be true but useless. Self-edges already on disk are untouched and still surface as a `cycle` finding from `docir check` — the rule guards the write path, it does not rewrite anyone's files — and a test pins that. Verified by injecting the bug: with the self check disabled, both new guards fail.
