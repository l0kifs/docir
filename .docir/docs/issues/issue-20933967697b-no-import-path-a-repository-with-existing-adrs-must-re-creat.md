---
created: '2026-07-30'
description: The most likely adopter is precisely a project that already keeps ADRs
  in markdown — the audience the product describes.
id: issue-20933967697b
owner: maintainer
related:
- arch-90c90751344f
- issue-389dc5dac58a
- issue-b7ddde3ce860
- issue-6a0ad9a70f84
status: resolved
tags:
- integrity
- material
title: 'No import path: a repository with existing ADRs must re-create every document
  by hand'
type: issue
updated: '2026-08-05'
---

**Class:** missing · **Severity:** material
**Flow:** arch-90c90751344f · **Step:** adopting docir in a repo that already has documents
**Question:** issue-6a0ad9a70f84 · **Frequency:** once per adopting repository, at the moment of adoption

## Finding

There is no import path. A repository with existing ADRs must create each document through `docir add`, and because ids are always allocated by the system (BR-006), the existing ADR numbers cannot be preserved.

## What happens today

No `import`, `export`, `migrate` or `adopt` command exists anywhere in the CLI (verified by search). Every cross-reference in the existing corpus breaks on adoption.

## Impact

The most likely adopter is precisely a project that already keeps ADRs in markdown — the audience the product describes. For them the on-ramp is a hand-written migration script plus renumbering every historical reference. The bulk-import path is, as the coverage checklist predicts, both the most important and the least documented flow.

## Proposed default

NOT a command. `docir import` was built on 2026-07-27 and REMOVED the same day before committing; the reasoning is worth keeping so it is not rebuilt naively. It preserved the number a filename implies, inferred title/description/status, and handled a directory in one pass. It worked perfectly on docir's own ADRs. It was removed for two reasons that compound: (a) The maintainer wanted random ids by default even for numbered sources, which removes the one thing import could do that `docir add` cannot. What remained was inference — and every inference is a guess the agent must verify. Verifying a guess is not cheaper than making the judgement; it is often dearer, because the guess must first be noticed as wrong. The agent reads every source file either way, so import saved the *writing*, and writing was never the bottleneck. (b) It reported success on input it had silently mangled. DEMONSTRATED: a `decisions.md` holding three decisions — one superseded, one rejected — became ONE document titled "Architecture decisions" with status `proposed`; a file whose body read "DRAFT — do not rely on this" imported as `proposed`, indistinguishable from a real decision. The report said `imported 2, failed 0`. An agent reading that concludes the migration is done. The honest replacement is a documented workflow, now in the packaged agent guide: read each file, decide whether it is one document or several, judge whether it is still true, write a real description, pick the type, then `docir add`. Adoption stays awkward — that is the true state of affairs, and a command that hid it made things worse. If it is ever revisited, the design that would address (b) is importing *archived*, so documents are invisible to every read path until an agent reviews and unarchives each one — review becomes structural rather than advisory.

## Resolution

FIXED 2026-07-29 with `docir add --id <id>` — one flag, not the command that was rejected. The rejection above is sound and stands; it killed *inference* — one file guessed into one document, with `imported 2, failed 0` reported over input it had mangled. But it took id preservation down with it, and the two are separable. Preserving `adr-0007` is not an inference. The caller reads it off the file and states it, one document at a time, after reviewing the file exactly as the documented workflow says. The argument that settles the bulk case — "every inference is a guess the agent must verify, and verifying a guess is not cheaper than making the judgement" — does not reach a fact the human supplies. What was left after the rejection was the guide telling adopters to "keep a mapping as you go and fix the references in step 4": pure mechanical bookkeeping across a corpus that cross-references itself. Every safety it needs already existed, built for issue-b7ddde3ce860/issue-389dc5dac58a: the file store refuses a create when any file claims the id (keyed on id, not path), and `IdGenerator` skips indexed ids. Added: a prefix check, since the prefix encodes the type, and an index-side collision check. The apparent bypass is of "ids come from the counter"; the invariant that matters is collision-freedom, and it survives — the id is validated on both sides. FOUND WHILE VERIFYING MY OWN CLAIM: adopting `adr-0007` left the counter at 1, so the next `add` minted `adr-0001`. Safe (the generator skips indexed ids) but not what adopting a corpus implies, and corrected only by the next `reindex`. `_allocate_id` now calls `raise_next_number`, with the same two guards `_restore_id_sequences` uses: counter-backed types only, and never from a random-looking token. The CLI docstring had already asserted the behaviour before it was true. SCOPE, stated honestly: this only helps a store using `--id-style sequential`. With `random` as the `init` default there is no numbering to preserve — but a repository adopting docir with ADR-007..ADR-042 is exactly the one that chooses `sequential`, so the flag and that choice go together. NOT REVISITED: the archived-import design sketched above remains the right shape *if* a bulk path is ever wanted. It addresses the report-success-over-mangled-input problem, not id continuity, and is far more machinery than this.

## Actors affected

- repository maintainer

## Evidence

- `src/docir/entry_points/cli/app.py`
- `src/docir/modules/documents/application/services/id_generator.py:26-40`

---

Migrated from the discovery gap register (GAP-036); the register itself now lives in this store.
