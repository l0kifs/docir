---
code:
- src/docir/modules/documents/application/services/maintenance_service.py
- src/docir/platform/filesystem/git_history.py
code_baseline:
  src/docir/modules/documents/application/services/maintenance_service.py: c59e0525fe19
  src/docir/platform/filesystem/git_history.py: bf81fa117555
created: '2026-09-23'
description: Why check gains --against rather than a command of its own, why both
  its findings are errors, and why an unreadable ref must not be silence.
id: adr-df43aff8bb0d
owner: maintainer
related:
- adr-39210c34551a
- issue-9683b4713792
status: proposed
tags: []
title: The id collision is reported before the merge, against a base ref
type: decision
updated: '2026-09-23'
---

## Decision

`docir check --against <ref>` reports ids that are **new on this branch** and already used at
`<ref>`. Two findings, both `error`, and both existing only when a ref is named:

* `branch-id-collision` — your id, your file, and theirs.
* `unreadable-ref` — the ref could not be read at all.

## Why before the merge

The collision exists from the moment the second branch allocates: the ids are on both sides,
and each branch is correct on its own. Nothing could see it until both documents were in one
tree, and by then it is on `main`.

There is **no renumber command** — an id is a document's only address and no write re-mints
one — so the repair is the same either way: bring the base in and run `check --fix`, which
sees both files and re-issues the newer ([[adr-39210c34551a]] decides which is which, and the
base's file was committed first). What the flag buys is doing that **on this branch**, before
`main` sees the collision and before anyone else can cite the id. After the merge it is
whoever merges second repairing a conflict against an id that may already be cited.

That distinction is why the finding names the repair rather than a flag: following it has to
produce the result, and `docir update` cannot renumber anything.

`check` already held everything needed except the comparison: it scans the files for
`duplicate-id`, and this is the same scan asked against a second tree.

## Why a flag on `check`, not a command

A new command would need its own answer to everything `check` already decides — severity,
`--strict`, the JSON shape, where it runs in CI. The question is the same question (*is this
corpus safe to merge*) asked with one more input, and the CI line people already run gains one
word:

```
docir check --against origin/main --strict
```

`--fix` and `--against` are **refused together** rather than one being ignored. The repair for
a collision with another ref is to renumber here, deliberately; `--fix` re-issues ids from the
local counter and cannot see that ref, so it could mint straight into it again.

## Why both findings are errors

Neither can red-build a branch that did not opt in: they exist only when a ref is named, and
naming one *is* asking for a gate.

`branch-id-collision` is an error because the whole purpose of the flag is to fail before the
merge makes the collision real. It is unlike the warnings [[adr-e98749aa457d]] and its
neighbours argue about, which fire on correct corpora — a branch carrying this one is not
correct, it is about to break `main`.

`unreadable-ref` is an error on the argument that made `empty-index` one, arriving one merge
away. A gate that passes because it could not look is worse than no gate, and silence here is
indistinguishable from a clean branch. The most likely cause is mundane and fixable — the ref
was never fetched — so the message says to fetch it.

That is also why the port's `ids_at` returns `None` for *unknown* and an empty dict for *no
documents there*. Collapsing them would make an unfetched ref read as an empty base, which
passes every branch.

## Why it reads ids from file contents

`git grep -E "^id: " <ref>` returns the whole mapping in one subprocess — 250 documents in one
call rather than a `git show` each. The filename begins with the id and is not used for it: a
prefix carrying a `-` makes the filename ambiguous, and a hand-edited file can disagree with
its own name. The frontmatter is what every other reader here trusts.

Only files **absent from the ref** are compared. A document that exists on both sides keeps its
id there and here whether or not this branch edited it, and reporting that would fire on every
branch that touches a document — which is every branch.

## The second call to git, on the same terms

This extends the exception [[adr-39210c34551a]] opened: committed history is shared, unlike the
per-machine answers [[adr-1d1eddbb6fbd]] refused to read. Both calls now go through one `_run`
in the adapter, so the timeout and the "could not run at all" mapping are stated once.

## What the git key cannot separate

The repair reads commit history, so it separates two files only once **both** are committed —
which a merge does, and which is why the documented workflow merges before it repairs. Restore
the base's file without committing and one side is untracked: git can say nothing about it,
`created` decides instead, and on a same-day collision the alphabet does. That is the existing
fallback behaving as designed, not a second defect, and it is stated here because the
difference is invisible in the output — the action names the `created` key rather than
`first added to git`, which is the only sign.

Not closed by treating untracked as new: `added_at` returns `None` for an untracked file
and for a shallow clone, a missing repository and a machine without git alike, and reading that
one answer two ways is how a fallback becomes a guess.

## Consequences

CI gains a second, opt-in gate that is genuinely pre-merge, and a branch on a store outside a
repository is told so rather than passed. What is not built is any *automatic* renumbering
before the merge: the branch is told which id to move, and moving it is an ordinary
`docir update` the author makes — a mechanical rewrite of somebody's id is not a repair docir
performs unasked.
