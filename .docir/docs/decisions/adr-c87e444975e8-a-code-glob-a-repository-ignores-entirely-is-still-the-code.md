---
code:
- src/docir/platform/filesystem/code_matcher.py
code_baseline:
  src/docir/platform/filesystem/code_matcher.py: 3abbf169dc36
created: '2026-09-22'
description: 'Why .gitignore drops files from a code: glob only while the glob reaches
  something else, and why a glob that reaches nothing but ignored files is honoured
  instead of erased.'
id: adr-c87e444975e8
owner: maintainer
related:
- kind: refines
  to: adr-1d1eddbb6fbd
- issue-ec3819b1f13c
status: proposed
tags: []
title: A code glob a repository ignores entirely is still the code it governs
type: decision
updated: '2026-09-24'
---

## Decision

`.gitignore` governs what a `code:` glob **fingerprints**, and narrows what it **matches**
only while the glob reaches something else.

One rule, two halves:

* A glob that reaches ignored files *and* tracked ones drops the ignored ones. `src/**`
  reaching `src/bin/` is [[adr-1d1eddbb6fbd]] unchanged, and dropping the build output
  there is what stops one compile drifting every glob at once.
* A glob that reaches **nothing but** ignored files keeps them. It matches, it
  fingerprints, and it is watched like any other.

The hardcoded floor — `.git`, `__pycache__`, `.mypy_cache`, `.ruff_cache`, `.pytest_cache` —
is absolute in both halves.

## What this reverses, and what it keeps

[[adr-1d1eddbb6fbd]] said a path git would ignore "does not count as a match". That sentence
is withdrawn; every other sentence in it stands, including the reason the engine reads the
tree's own `.gitignore` files and nothing else.

The argument it was written from is about files a glob sweeps up **beside** the ones it was
aimed at. `.gitignore` answers "is this the repository's source", and for a broad glob that
is exactly the right question. It is the wrong question for a glob that reaches nothing else:
nobody sweeps a vendored clone up by accident, so a path written into `code:` by hand is a
statement that this document is governed by it — whatever git's opinion of whether it belongs
in this repository's history.

Ignoring a path and governing it are orthogonal. A vendored dependency, a shallow submodule, a
mirrored upstream clone, a generated API client committed nowhere: all are read-only inputs a
document can legitimately be governed by, and all are routinely gitignored precisely because
they are not this repository's source.

## What it cost to find out

288 of 288 governed documents in one adopting store lost their invalidation at once, and 102
live findings went to none. What replaced them was 288 `unmatched-code` findings — a message
reading "update the pattern", on 288 patterns that were correct.

The direction matters more than the count. 0.27.0 over-reported; 0.28.0 under-reported
silently, and an empty queue is indistinguishable from a clean one. Where the two rules
disagree, the conservative one is the one that still reports.

The workaround an adopter found is the measure of the defect: move the exclusion from
`.gitignore` to `.git/info/exclude`, which docir deliberately does not read. It works, and
it costs the exclusion the one property it had — `.gitignore` is committed, and
`.git/info/exclude` is per-machine and invisible to everyone who clones.

## Two passes, not one predicate

`_files_under` walks once dropping ignored files, and walks again keeping them **only if the
first walk found nothing**. `matches` does the same with its short-circuit intact.

A single classify-as-you-go pass was the obvious shape and is worse: an ignored *directory* can
no longer be pruned, so a broad glob descends into every `node_modules` and `.venv` it reaches
to discover it did not need them. Two passes keep the common case at exactly its old cost,
including the pruning, and pay a second walk only for a pattern that used to resolve to
nothing — which is the case that was silent.

## Why the floor stays absolute

Re-admitting the floor on the second pass would hash bytecode again ([[issue-68df009b4e43]])
through the door this decision opens: `src/**/__pycache__/**` reaches nothing but `.pyc`
files, finds nothing on the first pass, and would be honoured on the second. A glob reaching
nothing but generated output governs nothing anyone wrote, which is the one case where
"somebody wrote this by hand" is not evidence of intent — the pattern is broad, not specific.

## What upgrading costs

Nothing re-reports. A mixed glob's digest is computed exactly as before, so no stored baseline
changes value and no document drifts on upgrade.

A glob that 0.28.0 silenced comes back with no baseline — 0.28.0 dropped it, because there was
nothing it would fingerprint — so it surfaces as `code-unwatched` ([[adr-29a43d127e92]]) and `docir check --fix` arms it. That is the recovery path, and it is the same
one every other unwatched glob takes.

A teammate on 0.28.0 reading the same store computes no digest for those globs and reports
`unmatched-code` on them, exactly as it does today. Neither build refuses anything, so this
clears the bar [[adr-ab4598c6f707]] sets; what it costs is that those globs are a per-build
opinion until everyone upgrades, in the direction where the older build over-reports.

## Consequences

A `code:` glob is now the author's statement about scope, and `.gitignore` is a tool for
removing noise from inside one rather than a veto over it. Exclusions the repository does not
ignore — a committed `src/generated/` — remain unexpressible, unchanged from
[[adr-1d1eddbb6fbd]] and for the same reason: `code:` globs would need a second grammar.
