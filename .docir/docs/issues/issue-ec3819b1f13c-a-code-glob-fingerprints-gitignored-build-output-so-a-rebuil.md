---
code:
- src/docir/platform/filesystem/code_matcher.py
code_baseline:
  src/docir/platform/filesystem/code_matcher.py: 49e035db439d
created: '2026-09-18'
description: 'Every file under a code: glob is hashed, ignored ones included, so one
  compile drifts every document governing a source tree that holds build output.'
id: issue-ec3819b1f13c
owner: maintainer
related:
- adr-1d1eddbb6fbd
- adr-49bb8cc48938
status: resolved
tags:
- cli
- integrity
title: A code glob fingerprints gitignored build output, so a rebuild reports drift
type: issue
updated: '2026-09-18'
verified: '2026-09-18'
verified_code:
  src/docir/platform/filesystem/code_matcher.py: 49e035db439d
verified_content: aa1c65118684
---

## What is wrong

`RepositoryCodeMatcher` fingerprints every file under a `code:` glob, including the
ones `.gitignore` excludes. Touching only an ignored file moves the digest, so
`docir check` reports `code-drifted` on a document whose governed source has not
changed.

In a repository whose build writes output beside its sources — `bin/` and `obj/`
for .NET, and the same shape for `target/`, `dist/`, `build/` — one compile drifts
every `src/**`-style glob at once.

`_SKIPPED_DIRS` already states the principle this misses: a directory that "moves
differently on a teammate's machine" would "report drift against a baseline they
never diverged from". Every entry in it is Python or git, and `.gitignore` is the
repository's own statement of which the rest are.

## Measured

Reported against 0.27.0 from a .NET repository where five documents reported
`code-drifted` after a build in which no tracked file under any of their globs had
changed. Reproduced on a scratch store: `src/**` with `bin/` ignored, one write to
`src/bin/out.txt`, `git status` clean, `code-drifted` on the document.

**It was also live in docir's own corpus.** Of the 116 distinct `code:` patterns
here, one digest moves when ignored files are excluded: `benchmarks/**`, and what
moves it is `benchmarks/.coverage`, rewritten by every test run under coverage.
`__pycache__` below it was already skipped; `.coverage` is a file, and a skip set
made of directory names cannot reach it.

## Why it matters

The finding is indistinguishable from a real one, so the queue stops being
readable: the correct response to a false `code-drifted` is to re-read a document
that nothing changed, and `--verified` clears it only until the next build.

## The `!` half, and a correction to the report

The report says a `!`-prefixed glob is "accepted and silently ignored", and that no
`unmatched-code` is reported for it. The first half is right — `code:` globs are
`pathlib` patterns, where `!` is a literal — and the second is not: `check` does
report `unmatched-code` on `'!src/bin/**'`, verified on 0.27.0.

It is still a poor answer. The write is accepted, and the signal arrives later, as
"matches nothing" rather than "exclusions are not written this way".

## What would fix it

Consult the repository's own `.gitignore` files in the matcher, and refuse a `!`
entry at Tier 0 naming that mechanism. The reasoning, the alternatives refused and
what upgrading costs are recorded as [[adr-1d1eddbb6fbd]].

## Reported

GitHub issue #20, against 0.27.0, reproduced with and without the daemon.

## Resolution

FIXED 2026-09-18. `RepositoryCodeMatcher` consults the repository's own `.gitignore`
files beside the hardcoded skip set: an ignored path is neither hashed into a glob's
digest nor counted as a match. The reasoning, the alternatives refused and what upgrading
costs are [[adr-1d1eddbb6fbd]].

The reported reproduction, re-run against the fix — `src/**` with `bin/` ignored:

```
write src/bin/out.txt (ignored)   no code finding
write src/keep.txt    (tracked)   code-drifted
```

The second line is what makes the first mean something: a matcher that ignored everything
would pass the first and detect nothing.

**On this repository, live.** `benchmarks/**` was the one pattern of 116 whose digest
moved, and `benchmarks/.coverage` was moving it on every test run under coverage. It is
stable across a coverage run now, measured before and after. The document that governs it
(issue-c6d184704682) stays `code-drifted` until somebody reads it, because its baseline
was taken by the old algorithm — one document, which is what the upgrade costs here.

**The `!` half** is refused at Tier 0, and the message names what replaces it rather than
saying "unusable" — the author wrote an exclusion, and "matches nothing" is an answer to a
question they did not ask. Patterns an older build already wrote are untouched: Tier 0
validates what a write *sets*, so an unrelated `--set-owner` on such a document still
succeeds, verified against one the 0.27.0 wheel wrote.

Ten injections, each proven to fail its guard. Three against the matcher — dropping the
ignore consultation, ignoring everything, dropping the always-skipped floor — and seven
against the engine: no ancestor walk, first-match-wins inside a file, nothing anchored,
`**` as a literal segment, negation dropped, the shallowest ignore file winning, and an
unreadable ignore file read as "exclude everything". The second matcher injection matters
as much as the first: the cheap wrong fix here excludes too much, and a test suite that
only checks "the build no longer drifts" passes on an engine that has stopped watching the
code.

The grammar is parsed here rather than taken from a library, and it is checked against
`git check-ignore` rather than against a reading of `gitignore(5)` — ten rule sets and
forty paths, run twice, once as a recorded table and once re-derived from git. Doing that
caught a real error in the first attempt, which used `pathspec`: a file under an excluded
directory cannot be re-included, and a per-file matcher says it can.

Cross-build, measured on one store at one moment: this build reports nothing where 0.27.0
reports `code-drifted`. Neither refuses anything and `doctor --strict` exits 0 on both, so
it clears [[adr-ab4598c6f707]]; the ADR records it as the cost of the older build
over-reporting until everyone upgrades.
