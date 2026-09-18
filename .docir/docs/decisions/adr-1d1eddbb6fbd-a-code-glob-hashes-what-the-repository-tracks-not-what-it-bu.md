---
code:
- src/docir/platform/filesystem/code_matcher.py
- src/docir/platform/filesystem/gitignore.py
code_baseline:
  src/docir/platform/filesystem/code_matcher.py: 49e035db439d
  src/docir/platform/filesystem/gitignore.py: 5fbc2dfd7629
created: '2026-09-18'
description: Why the fingerprint behind code-drifted consults the repository's own
  .gitignore files, and only those — not git check-ignore, not the user's global excludes.
id: adr-1d1eddbb6fbd
owner: maintainer
related:
- kind: refines
  to: adr-49bb8cc48938
- adr-d9e6d5ccd0b4
- adr-bd7c4f3c5764
status: proposed
tags:
- cli
- integrity
- persistence
title: A code glob hashes what the repository tracks, not what it builds
type: decision
updated: '2026-09-18'
verified: '2026-09-18'
verified_code:
  src/docir/platform/filesystem/code_matcher.py: 49e035db439d
  src/docir/platform/filesystem/gitignore.py: 5fbc2dfd7629
verified_content: 247683afb907
---

## Decision

`RepositoryCodeMatcher` consults the repository's own `.gitignore` files beside the
hardcoded skip set. A path git would ignore is not hashed into a `code:` glob's digest
and does not count as a match.

Only the `.gitignore` files **in the tree**. Not `.git/info/exclude`, not the user's
global `core.excludesFile`, and not `git check-ignore` — which answers with all three and
needs a `.git` directory besides.

## Why the tracked files and nothing else

The digest's whole value is that two people hashing the same tree get the same answer.
`.gitignore` is committed, so it is the same for everyone; the other two ignore sources are
per-machine, and a digest that read them would move between colleagues exactly the way a
digest full of `.pyc` files did. That is the defect the skip set was written to avoid,
reached through a wider door.

It is also why this reads the files rather than shelling out. `git check-ignore` is git's
own answer and therefore the *most* faithful one, which here is the wrong property.

**Measured on this repository, and the numbers say it twice.** Across all 12,307 paths in
the tree, docir's verdict and `git check-ignore`'s differ on exactly three:

```
.claude/skills/discovering-business-scenarios
.claude/skills/execution-playbooks
.claude/skills/writing-and-refactoring-clean-code
```

All three are excluded by `.git/info/exclude` and by nothing else — `git check-ignore -v`
names the file — and all three are symlinks into one developer's other checkout. They are
precisely the paths a teammate's clone would not have, so agreeing with git about them is
the thing to avoid, not the thing to aim for. The engine is otherwise identical to git over
12,304 paths.

## Why the skip set survives

Five directories stay skipped whatever the repository says. `.git` is never listed in a
`.gitignore` because git excludes it without being asked, and a tree with no ignore file
at all still needs the rest. A repository is also free to un-ignore its caches, and
`__pycache__` would then be hashed again.

The skip set is a floor. The ignore files are what generalise its argument from Python to
every language's build output — `bin/` and `obj/` for .NET, `target/`, `dist/`, `build/` —
which a list of directory names could only ever chase.

## Measured, and the bug was live here

Across the 116 distinct `code:` patterns in docir's own corpus, one digest moves:
`benchmarks/**`, and what moves it is `benchmarks/.coverage`, rewritten by every test run
under coverage. `__pycache__` beneath it was already skipped; `.coverage` is a *file*, and
a skip set made of directory names cannot reach it.

So the defect [[issue-ec3819b1f13c]] reports from a .NET repository was already firing in
this one, on the corpus its maintainer reads daily, and the shape of the skip set is why
nobody saw it.

## What upgrading costs

A pattern whose match set shrinks gets a digest that no longer equals its stored baseline,
so `check` reports `code-drifted` once and the remedy is the one the finding already names:
read the document against the code and stamp `--verified`.

One document here. In a repository where the defect is live it is every governed document —
and there the re-baseline **is** the fix arriving, because the drift being reported today is
false.

No migration machinery, deliberately. Re-minting baselines mechanically on `reindex` would
clear a standing drift by upgrading, which is the laundering [[adr-49bb8cc48938]] refused to
allow through `--set-code`, arriving through a cheaper door; and re-minting `verified_code`
would forge a review outright.

## `!` is refused on write

A `!`-prefixed entry was accepted and matched nothing, because `code:` globs are `pathlib`
patterns and a `!` is a literal there. `check` did say so — `unmatched-code` fires on it —
but a warning that reports "matches nothing" a reindex later is a poor answer to somebody
who wrote an exclusion and expected one.

Tier 0 now refuses it, naming the mechanism that replaces it. This is the fourth of the
"ways an entry silently matches nothing forever" that `validate_code` already rejects.

Exclusions the repository does not ignore — a committed `src/generated/` — remain
unexpressible. That is deliberate for now: `code:` globs would need a second grammar, and
the case has not been reported.

## Cost

The grammar is parsed here, in `platform/filesystem/gitignore.py`, and not by a library.
`pathspec` was the obvious alternative and was tried first; taking the dependency out cost
about 120 lines.

That trade is only defensible because correctness is checked against git rather than
argued from `gitignore(5)`. `tests/platform/test_gitignore.py` carries ten rule sets and
forty paths twice over: once as a recorded table, and once re-derived by running
`git check-ignore` in a scratch repository and comparing every verdict. The table is what
pins the grammar where git is not installed; the differential is what stops the table from
being written out of the same misreading it is supposed to catch.

**It earned its keep immediately.** The library version was wrong about the rule git is
most often quoted on: a file under an excluded directory cannot be re-included, because
git never descends into the directory to read the `!` that would bring it back. Matching
each path against a pattern set — which is what a per-file matcher does — gets this
backwards and hashes a build artifact. The engine here walks the ancestors first, so
`bin/` plus `!src/bin/out.o` leaves the file ignored, exactly as `git check-ignore` says.

Runtime cost is a parse of each `.gitignore` the first time its directory is asked about,
and one cached verdict per directory, so the ancestor walk is paid once per directory
rather than once per file.

## What a teammate on an older build sees

A store is a committed artifact, so two teammates on different docir versions read the
same `code_baseline` and compute different digests from the same tree. Measured, on one
store, at one moment, after a write to an ignored file only:

| build reading the store | verdict |
|---|---|
| this one | no code finding |
| the 0.27.0 release | `code-drifted` |

Neither refuses anything — the older build reads the store, and `doctor --strict` exits 0
— so it clears the bar [[adr-ab4598c6f707]] sets. What it costs is that `code-drifted` is
a per-build opinion until everyone upgrades, in the direction where the older build
over-reports. That is the state it was already in; upgrading is what ends it.

A `!` entry an older build wrote also survives here. Tier 0 validates the patterns a write
*sets*, not the ones a document already carries, so an unrelated `docir update --set-owner`
on such a document still succeeds — verified against a document the 0.27.0 wheel wrote.
Only `--set-code` re-states the patterns, and re-stating that one is what the refusal is
for.
