---
code:
- scripts/code_citations.py
- tests/entry_points/test_code_citations.py
code_baseline:
  scripts/code_citations.py: 0d503fb3a529
  tests/entry_points/test_code_citations.py: 2a5239ba084c
created: '2026-09-22'
description: Line numbers move with every insertion above them; five documents carried
  citation columns that had shifted wholesale, and a sample of eighteen in-bounds
  ones found seven pointing at the wrong symbol.
id: issue-d4b194eca41d
owner: maintainer
related:
- adr-bea42e359960
- issue-acff9cbd2b06
status: resolved
tags:
- docs
- testing
title: A file.py:line citation rots silently, and nothing checked one
type: issue
updated: '2026-09-22'
verified: '2026-09-22'
verified_code:
  scripts/code_citations.py: 0d503fb3a529
  tests/entry_points/test_code_citations.py: 2a5239ba084c
verified_content: 0f4fda39af44
---

## What is wrong

A `file.py:line` in a document is a promise that a reader following it lands on the thing
the sentence is about. Line numbers do not keep it: every insertion above one moves it,
silently, and the string that results is indistinguishable from a correct one.

Nothing checked them. `cli_oracle` resolves every `docir ...` line against the live command
tree, and the store is one of its six surfaces — but a citation into the *source* needs a
different oracle, and there was none.

## Measured

Reading the `code-drifted` and `code-unverified` backlogs against their code turned up five
documents whose citation columns had shifted **wholesale**, not by a line or two:

- [[arch-3e305bc76ff0]], the **write path**, pointed `IndexProjected` and
  `EmbeddingMarkedDirty` at two lines inside `_ranking_trace`, a *read*-path helper, and
  `DocumentArchived` at `__init__`.
- [[arch-ccfcceeb35eb]] pointed `TagRenamed` at the `TagService` class header and
  `RegistryFileSynced` at `list_all`; `rename` is eighty lines below, `_sync_file` a hundred
  further.
- [[arch-f220a644d654]], [[issue-afd25273ff1f]] and [[arch-90c90751344f]] the same way.

Across the whole store: **266** citations in 71 documents. Sixteen named a file that no
longer resolves or a line past its end — twelve of them into a `graph_checks.py` whose
checks moved under `checks/`. Of the rest, a random sample of eighteen was read against the
prose around it and **seven pointed at the wrong symbol**.

## Why a checker alone cannot fix it

The wrongness is invisible to a machine. A citation is well-formed whether it means the
write path or a read-path helper; nothing in the text says what the author intended. A
checker can only see that the line exists — which is true for 250 of the 266.

Auto-pairing each citation with whatever symbol now spans it would make a guard pass and
bake in the roughly two-in-five that are wrong. Deriving the pair from the prose does not
work either: the surrounding text already names the right symbol in only **9** of 266 cases.

## What would fix it

A citation carries its own redundancy — the symbol it points at, named beside it. Then the
halves can disagree, and disagreement is detectable in the commit that causes it.

## Resolution

FIXED 2026-09-22. `scripts/code_citations.py` resolves a citation to a file and a line, and
names the innermost symbol spanning it; `tests/entry_points/test_code_citations.py` runs it
over every document in the store.

Two rules, because only one of them is decidable today.

**Every citation must resolve** to a real file at an existing line. The sixteen that did not
are fixed — their line numbers are dropped and the file kept, since the intent ("this file is
the evidence") survives while the precision does not.

**Every new citation must name its symbol**, so the pair can disagree. The 250 that predate
the rule are grandfathered per document by **count**, not by a list of 250 entries: a
grandfathered document may not grow a new unpaired citation, and fixing one must shrink its
number — the assertion is equality, so a fix that is not recorded fails too. Editing such a
citation changes its line, which is exactly the moment to adopt the paired form.

Four injections, each proven to fail its guard: an unpaired citation in a document with none,
a pairing that names the wrong symbol, a line past end of file, and a grandfathered count
lowered without updating the table. Plus two unit guards on the oracle itself, because a
checker that judges nothing passes everything.

A bare filename resolves only when it is unique. `dto.py` exists under both `tags` and
`documents`, and guessing between them reports a healthy citation as broken — worse than
declining to judge it. A repo-relative path always wins.

## What it does not do

It cannot tell a right line from a wrong one among the grandfathered 250, and does not
pretend to. That is a read, and the two backlogs this came out of are where it happens.
