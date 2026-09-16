---
code:
- src/docir/modules/documents/application/services/code_evidence.py
- src/docir/modules/documents/domain/services/checks/verification_rules.py
- src/docir/modules/documents/application/services/store_repairer.py
code_baseline:
  src/docir/modules/documents/application/services/code_evidence.py: 793cdf7277e9
  src/docir/modules/documents/application/services/store_repairer.py: 81762c221b8f
  src/docir/modules/documents/domain/services/checks/verification_rules.py: df4d15de1c87
created: '2026-09-16'
description: Why drift is measured from a baseline the write mints, why that is a
  second digest beside the verified one, and why re-declaring a glob never clears
  a drift.
id: adr-49bb8cc48938
owner: maintainer
related:
- kind: refines
  to: adr-d9e6d5ccd0b4
- adr-bd7c4f3c5764
- arch-0a3c2d6d54a6
- issue-6e4ccac453ed
status: accepted
tags:
- cli
- docs
- integrity
title: A code glob is watched from the write that declares it
type: decision
updated: '2026-09-16'
---

A `code:` glob now records what it matched at the moment the document declared it, and
`docir check` reports `code-drifted` when that code moves. The digest a verification takes
stays exactly as [[adr-d9e6d5ccd0b4]] defined it; this adds a second, weaker one beside it,
because the first was reachable only through a step almost nobody takes ([[issue-6e4ccac453ed]]).

## Two claims, not one field

`verified_code` says *the code moved since somebody read this*. It cannot exist before a
review, and it must not: a write that filled it in would make the review clock a side
effect of running a command.

`code_baseline` says *the code moved since this document said it governs this*. That is a
fact about the tree, and the write that declares the glob is entitled to record it. Nothing
in it claims a reading, which is precisely what lets it be minted automatically.

Both are warnings and both name the same remedy — read the document against the code and
stamp `--verified`. They differ in what they are entitled to assert, and a single field
would have had to pick one.

## Why a second digest rather than a re-reading of the first

Storing one digest and inferring its meaning from whether `verified` is set fails on the
document that was verified, then gained a glob: the new pattern has no review behind it and
the old one does. The evidence is per-pattern, so the distinction has to be per-pattern too.

## Minted once, never refreshed mechanically

A pattern gets a baseline on the write that first names it, and keeps it through every
later write except `--verified`, which re-bases what the reviewer actually read.

Refreshing a surviving pattern on `--set-code` was the tempting simplification and is the
defect: `--set-code` reads nothing, so it would hand any write a way to clear a standing
drift — the laundering [[adr-bd7c4f3c5764]] forbids, arriving through the cheapest door
there is. It also bounds the cost: the tree is walked once per pattern per document.

## Where it is stored, and what that costs

In the frontmatter, for the reason [[adr-d9e6d5ccd0b4]] gives: the index is gitignored and
rebuilt from the files, so a baseline living only there would reset on every `reindex` and
never fire. The index carries a mirrored column, derived like everything else in it.

`check` now fingerprints every glob that carries either digest, where before it hashed only
the verified ones. That is the price: hashing subtrees to compare them against something,
in place of not hashing them and reporting nothing.

## The two findings partition the patterns

A pattern carrying a verified digest is `code-changed`'s alone; a pattern carrying only a
baseline is `code-drifted`'s. One moved file is named once, under the strongest claim its
evidence supports. A document can raise both, for different patterns.

## Backfilling is `check --fix`, and it starts from now

Every document written before this field has globs and no baseline. `docir check --fix`
mints one for each, reports which documents it started watching, and touches no review
state — it needs no guess, and a baseline asserts nothing a human has to judge, which is
the line `--fix` may not cross.

What it cannot do is recover drift that already happened: there is no record of what those
trees held. Watching starts at the run, and the action says so rather than implying the
silence that follows means nothing moved.

## What an older docir does with the key

A store is read by whatever docir each teammate installed, so the key had to be measured
against the release people already have. It was: 0.26.0 reindexes a store carrying
`code_baseline:` with 216 of 216 documents and nothing skipped, and `doctor --strict`,
`check --strict`, `context`, `query`, `search` and `get` all answer with exit 0. An
unknown frontmatter key is ignored on read, so nothing refuses.

What it does not do is keep the key. Its `render` writes the fields it knows, so a write
from an older build drops `code_baseline:` and puts that document back to watching nothing
— silently, since the document is otherwise intact. That is erosion rather than a break: no
read fails, no evidence is falsified, and `docir check --fix` mints the baseline again.

Which is why the backfill is not a migration that runs once. It is the recovery path for
every way a baseline can go missing, and the packaged skill says to run it on adoption and
after a teammate on an older docir has written. The test that strips the key from a file
and proves `--fix` restores it pins exactly this.
