---
code:
- src/docir/modules/documents/domain/services/checks/verification_rules.py
code_baseline:
  src/docir/modules/documents/domain/services/checks/verification_rules.py: 91bee7b137da
created: '2026-09-22'
description: Why check reports code-unwatched for a glob that resolves and carries
  no digest, why check --fix may repair it when its three siblings need a judgement,
  and why it is a warning.
id: adr-29a43d127e92
owner: maintainer
related:
- kind: refines
  to: adr-49bb8cc48938
- adr-c87e444975e8
status: proposed
tags: []
title: A code glob nothing is watching is a finding, not a silence
type: decision
updated: '2026-09-22'
---

## Decision

`docir check` reports `code-unwatched`: a `code:` glob that resolves against the working tree
and carries neither a `code_baseline` nor a `verified_code` digest. A Tier 1 warning, repaired
by `docir check --fix`.

## The gap it closes

Four findings read a document's globs, and until this one they left a hole between them:

| the glob | finding |
|---|---|
| names nothing | `unmatched-code` |
| moved since a verification | `code-changed` |
| moved since it was declared | `code-drifted` |
| names something, nothing watching it | *nothing* |

The last row is not an edge case. A decision written before the code it decides is the
ordinary case the write path deliberately accepts, and it has nothing to fingerprint, so it
records no baseline. `unmatched-code` does fire while the path is absent — and it is a
different finding, saying "update the pattern" rather than "the baseline is about to be taken
empty". It then **stops** the moment the file arrives, taking the last signal with it. The file
appearing reports nothing. Every later edit reports nothing.

`mint_baseline` would fill the missing entry, but only on a *write*, and `check` never writes.

## Why a finding rather than a refusal at stamp time

Refusing `--verified` on a glob that matches nothing was the alternative, and it punishes the
correct workflow: writing the decision before the code is the shape the `code:` field was built
to support ([[adr-1d1eddbb6fbd]] keeps Tier 0 accepting a pattern that matches nothing for the
same reason). It also cannot help the other route in — a document written by a build that minted
no baseline at all — because no stamp happens there.

A finding covers both, and it is the only one that reports the *transition*: the state becomes
wrong when the file arrives, which is after every write anyone made.

## Why it is repairable when its three siblings are not

`code-changed`, `code-drifted` and `unmatched-code` all clear on a judgement — read the
document against the code, or decide the pattern is wrong — so `check --fix` has nothing to
read with. This one clears on a *fact*: a baseline records what the tree held when watching
started, and claims nothing about who looked at it. That is the line `verified_code` is fenced
by ([[adr-d9e6d5ccd0b4]]), and minting a baseline does not cross it.

`check --fix` already carried the repair. What it lacked was a finding to answer — so the
repair existed for anyone who ran `--fix` speculatively, and for nobody else.

Watching starts at the next change, not at the one already missed. The repair therefore reports
one action per document rather than running silently: the frontmatter of every governed
document moves, and the reader has to see that in the diff.

## Why a warning

The document is intact, the glob resolves, and the only fault is its own history. An error kind
would red-build the first commit of every document written before its baseline could be
minted — a correct corpus failing for a reason no commit in front of the reader caused, which
is the failure mode every Tier 1 warning here is written to avoid.

## Reported per pattern

A document carrying two globs, one armed and one not, was already in the queue for the armed
one while staying silent on the other. Being in the queue is not evidence that every glob on a
document is watched, so the finding names the pattern.

Measured on the reporting corpus: nine documents carried a verified glob with no fingerprint,
and **eight** produced no finding of any kind. The ninth was visible only by accident.

## Consequences

Every glob in a store is now in exactly one of four states, and each names its own exit.
[[adr-c87e444975e8]] depends on this: the globs it un-silences arrive carrying no baseline, and
`code-unwatched` plus `check --fix` is the recovery path they take.
