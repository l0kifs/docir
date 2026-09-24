---
code:
- src/docir/modules/documents/domain/services/checks/verification_rules.py
code_baseline:
  src/docir/modules/documents/domain/services/checks/verification_rules.py: 91bee7b137da
created: '2026-09-22'
description: A glob declared before the code it governs records no digest, so no finding
  reads it and no edit to that code is ever reported.
id: issue-53ca53c4c047
owner: maintainer
related:
- adr-29a43d127e92
- issue-0d4741c85e7f
- issue-6e4ccac453ed
status: resolved
tags:
- cli
- integrity
title: A code glob verified while it matches nothing records an empty baseline that
  never re-arms
type: issue
updated: '2026-09-24'
---

## What is wrong

A `code:` glob that matches nothing at the moment its baseline would be taken records none,
and nothing re-arms it. The file arriving reports nothing. Every later edit to it reports
nothing. The document is permanently silent on that glob.

`unmatched-code` fires while the path is absent, which is correct and is the only warning
there is — but it says "update the pattern", not "the baseline is about to be taken empty",
and it **stops the moment the file arrives**, taking the last signal with it.

## Why nothing catches it

The four code findings partition the patterns and leave this one out:

| the glob | finding |
|---|---|
| names nothing | `unmatched-code` |
| moved since a verification | `code-changed` |
| moved since it was declared | `code-drifted` |
| names something, nothing watching it | *nothing* |

`code-changed` and `code-drifted` both read a recorded digest and treat its absence as
*unknown* — which is right on its own terms, because a comparison against nothing is not a
change. `mint_baseline` does fill a missing entry, but only on a *write*, and `check` never
writes. So the recovery exists (`docir update <id> --verified` re-arms it, and edits report
from then on) and nothing surfaces that it is needed.

## Measured

Nine documents in the reporting corpus carried a verified glob with no fingerprint. **Eight**
produced no finding of any kind — all eight stamped against paths that arrived upstream
afterwards.

The ninth was visible only by accident: it declared two globs, one of them fingerprinted, and
that one happened to move. So it reported `code-changed` for an unrelated reason while its
other glob stayed silently exempt. **Being in the queue is not evidence that every glob on a
document is armed**, which is why the finding has to name the pattern.

It was found by hand, and only because a document whose governed source had demonstrably
moved was absent from a queue somebody was reading for another reason.

## Resolution

FIXED — [[adr-29a43d127e92]]. `docir check` reports `code-unwatched` for a glob that resolves
and carries neither digest, naming the pattern; `docir check --fix` mints the baseline, which
is a fact about the tree and not a claim that anybody read it. Watching starts at the next
change, not at the one already missed, so the repair reports one action per document rather
than running silently.

Not a refusal at stamp time: writing the decision before the code is the workflow the `code:`
field exists to support, and a refusal cannot reach the other route in — a document written by
a build that minted no baseline at all, where no stamp happens.

Five guards in `tests/modules/documents/test_code_references.py`. Verified by removing the
check: the two that assert the finding fail, and the three that assert its silence — a glob
that matches nothing, a watched glob, an archived document, a store with no repository — pass
either way, which is what says the finding is not firing on everything.

Reported as GitHub #25.
