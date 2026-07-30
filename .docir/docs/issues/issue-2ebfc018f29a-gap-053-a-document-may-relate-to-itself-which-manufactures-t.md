---
created: '2026-07-30'
description: Tier 0 accepts a self-edge; `docir check` then reports a one-node cycle
  that no edit but removing the edge can clear.
id: issue-2ebfc018f29a
owner: maintainer
related:
- ref-cb2beaa41604
- arch-0a3c2d6d54a6
status: open
tags:
- integrity
- material
title: GAP-053 — a document may relate to itself, which manufactures the cycle warning
  `check` exists to report
type: issue
updated: '2026-07-30'
---

# GAP-053 — a document may relate to itself, which manufactures the cycle warning `check` exists to report

**Class:** unusual · **Severity:** material · **Confidence:** observed
**Flow:** FLOW-001 (authoring) into FLOW-003 (integrity)
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

Same shape as GAP-048, where `tag rename X X` reported success, deleted the tag and left
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
