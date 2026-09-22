---
code:
- scripts/code_citations.py
- tests/entry_points/test_code_citations.py
code_baseline:
  scripts/code_citations.py: 0d503fb3a529
  tests/entry_points/test_code_citations.py: 6a642cd40926
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
  tests/entry_points/test_code_citations.py: 6a642cd40926
verified_content: 067e17dfff45
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

The grandfathered set is gone. It was written with 250 entries and deleted in the same pass:
a baseline is for a rule that cannot yet hold everywhere, and this one can.

The sweep that made it holdable applied one rule per citation. Where the surrounding prose
already named the symbol the file holds at that line, the citation was **paired** — a
confirmation rather than a derivation. Everywhere else the line was **dropped and the file
kept**, because a line that is wrong two times in five is worse than no line.

Of 266: nine were self-confirming, fifty-five in the rule register and sixty-six more across
two other references were evidence lists whose files are the useful part, and the rest went
the same way. **Seventeen survive, every one checked.** `arch-0a3c2d6d54a6` is the document
that kept the most — nine of nine matched their prose, because nothing this release touched
`maintenance_service.py`.

Three stragglers needed hands. Two were in a `description`, which is the field every search
result shows and which the guard scans because it reads the whole file rather than the body.
The third paired a range with a parenthetical *note* rather than a symbol and continued with
a bare second range — a compound the sweep read as already paired.

`require_pair` is now unconditional, and the only way to satisfy the guard by deleting
citations is itself guarded: a floor asserts the store still cites code at all, since a
checker over an empty set passes for the wrong reason.

## What it does not do

It cannot tell a right line from a wrong one among the grandfathered 250, and does not
pretend to. That is a read, and the two backlogs this came out of are where it happens.
