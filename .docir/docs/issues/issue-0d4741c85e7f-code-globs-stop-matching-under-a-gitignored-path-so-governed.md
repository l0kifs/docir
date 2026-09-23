---
code:
- src/docir/platform/filesystem/code_matcher.py
code_baseline:
  src/docir/platform/filesystem/code_matcher.py: 3abbf169dc36
created: '2026-09-22'
description: The fix for issue-ec3819b1f13c excluded ignored files from matching as
  well as fingerprinting, silencing every document governed by a vendored or mirrored
  source.
id: issue-0d4741c85e7f
owner: maintainer
related:
- adr-c87e444975e8
- issue-ec3819b1f13c
- issue-53ca53c4c047
status: resolved
tags:
- cli
- integrity
title: Code globs stop matching under a gitignored path, so governed clones lose invalidation
type: issue
updated: '2026-09-22'
---

## What is wrong

Since 0.28.0 a `code:` glob naming a file under a gitignored directory matches nothing. The
fix for [[issue-ec3819b1f13c]] excluded ignored files from *matching* as well as from
fingerprinting, so a repository that governs vendored or mirrored sources — checked out into
an ignored directory because they are read-only working copies, not sources — loses every
`code-changed` signal it had and gains one `unmatched-code` finding per document.

## Measured

Reported against 0.28.0 from an adopting store: 288 of 288 code-governing documents at once,
and the invalidation queue went from 102 live findings to none.

```
0.27.0                    0.28.0, same store, same commit
102 code-changed          288 unmatched-code
 35 code-drifted           11 code-changed
 40 stale                  15 code-drifted
  3 orphan                 40 stale
                            3 orphan
```

The direction is what makes this worse than what it replaced. 0.27.0 over-reported; 0.28.0
under-reports silently, and an empty queue is indistinguishable from a clean one. The 288
`unmatched-code` findings say "update the pattern" about 288 patterns that are correct.

## Why it slipped through

[[adr-1d1eddbb6fbd]] extended one rule to two questions in one sentence — a path git ignores
"is not hashed into a `code:` glob's digest **and** does not count as a match". The argument
behind it is only about the first: it is about files a broad glob sweeps up *beside* the ones
it was aimed at. Nobody sweeps a vendored clone up by accident.

Every test of the matcher builds its own tree in `tmp_path` with one ignore rule over a
subdirectory of a tracked tree, which is exactly the mixed case the rule is right about. The
all-ignored case had one test, and it asserted the defect.

## The workaround, and why it is not a fix

The adopter moved the exclusion to `.git/info/exclude`, which docir deliberately does not
read. It works — 102 `code-changed`, 0 `unmatched-code`, measured on 0.28.0 — and it costs the
exclusion the property it had: `.gitignore` is committed, `.git/info/exclude` is per-machine
and invisible to everyone who clones.

## Resolution

FIXED — [[adr-c87e444975e8]]. `.gitignore` drops files from a glob that reaches something
else, and is not consulted for a glob that reaches nothing else. Two passes, the second
running only for a pattern that used to resolve to nothing, so the common case pays what it
paid before and still prunes ignored subtrees. The hardcoded floor stays absolute on both.

Four guards in `tests/platform/test_infra_filesystem.py`, verified against the old matcher:
the two that pin the new half fail on it, and the two that pin the unchanged half pass on
both, which is what says the mixed case did not move.

Un-silenced globs arrive carrying no baseline, so they surface as `code-unwatched`
([[issue-53ca53c4c047]]) and `docir check --fix` arms them.

Reported as GitHub #24.
