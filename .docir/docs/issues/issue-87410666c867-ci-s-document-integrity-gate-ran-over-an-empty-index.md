---
code:
- .github/workflows/ci.yml
- src/docir/entry_points/doctor.py
created: '2026-08-25'
description: check --strict ran on a gitignored index, so dangling edges — half the
  merge guard — never fired; CI now reindexes and runs doctor --strict first.
id: issue-87410666c867
owner: maintainer
related:
- adr-909734bced92
status: resolved
tags:
- cli
- integrity
- testing
title: CI's document-integrity gate ran over an empty index
type: issue
updated: '2026-08-25'
---

## What was wrong

`.docir/docs/` is committed and the derived index is gitignored, so a CI checkout
has **no index at all** — and `docir check` reads the index. The document-integrity
step ran straight after the tests, on a fresh checkout, and reported `no structural
issues` over zero documents.

The step's own comment names the failure it fell into: *"a gate that always exits 0
reads as 'the corpus is clean' when it means 'nothing ran'."*

Half of it did run. `duplicate-id` and `malformed` scan the **files** directly, so
those kept working — which is why nothing looked broken. `dangling`, the other half
of the merge-into-main guard and the one the step exists for, reads the index and
therefore never fired.

Measured on a fresh clone with one linked-to document removed, the way a merge drops
one side of a link: the old sequence exits 0 with zero findings; with a `reindex`
first, the same corpus produces **16** `dangling` findings and exits 1.

## The fix

CI now runs `reindex` -> `doctor --strict` -> `check --strict`, in that order.
`pages.yml` already reindexed before building for exactly this reason; `ci.yml` did
not.

`doctor --strict` sits between them rather than beside them: it is what proves the
rebuild populated the index before the gate below trusts it. On this repo's corpus
the rebuild costs ~70s, and the model is already cached by the workflow.

## Why `empty-index` became an error

Found while placing the step. Doctor's own dispatch creates the index, so on a fresh
clone the second run finds an empty index where the first found none — and a
0-of-180 mismatch was only a warning, so `doctor --strict` exited 1 and then 0 on
the same corpus. A gate that goes green on the second attempt is worse than one that
never fired.

`empty-index` is now its own error kind, beside `no-index` and for the same reason:
every read answers nothing. A *partial* mismatch stays `index-behind-files`, a
warning — one file that will not parse counts on disk and not in the index for as
long as it exists, and an error there would red-build a repository for a condition
`check` already reports as `malformed`.

Two kinds rather than one kind with a conditional severity, because severity
deriving from the kind is what stops a new finding forgetting to classify itself.
