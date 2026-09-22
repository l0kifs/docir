---
code:
- src/docir/platform/filesystem/code_matcher.py
code_baseline:
  src/docir/platform/filesystem/code_matcher.py: 49e035db439d
created: '2026-09-17'
description: 'code: patterns ending in ** fingerprinted __pycache__ alongside the
  source, so a digest moved when no line was edited and differed across machines.'
id: issue-68df009b4e43
owner: maintainer
related:
- adr-d9e6d5ccd0b4
- adr-1d1eddbb6fbd
status: resolved
tags:
- cli
- integrity
title: A ** glob hashes the package's bytecode, so it drifts on its own
type: issue
updated: '2026-09-22'
verified: '2026-09-22'
verified_code:
  src/docir/platform/filesystem/code_matcher.py: 49e035db439d
verified_content: aae793b6d946
---

A `code:` glob ending in `**` over a Python package hashes the package's `__pycache__` as well
as its source. Of the 39 files `src/docir/modules/publishing/**` matched in this repository,
**19** were `.pyc`.

## What that costs

Bytecode moves when no line was edited — a different interpreter run, a `uv sync`, a fresh
install — so `code-drifted` fires against a baseline nothing diverged from. It is worse across
machines: `.pyc` content depends on the interpreter version and on cache invalidation, so a
teammate on a clean checkout compares their bytecode against the digest somebody else's
interpreter produced, and every broad glob in the store reports drift on arrival.

Measured here: 16 recorded baselines matched the old rule's digest exactly, meaning no source
file under them had changed and bytecode was the whole difference.

## Why it slipped through

[[adr-d9e6d5ccd0b4]] skips `.git` for precisely this reason — "it rewrites itself on every
operation, so a pattern broad enough to reach it would report the code as changed after a
checkout that touched nothing". The argument was written for one directory rather than for the
class it belongs to, and `__pycache__` satisfies it word for word.

Nothing caught it because every test of the matcher builds its own tree in `tmp_path`, where no
interpreter has ever written bytecode. It only appears against a real checkout — which is the
case [[adr-f14682e3f4d6]] exists to make somebody run.

## Resolution

FIXED — `_SKIPPED_DIRS` now names the class rather than one member: `.git`, `__pycache__`,
`.mypy_cache`, `.ruff_cache`, `.pytest_cache`. A test builds a `__pycache__`, rewrites the
`.pyc`, and asserts the digest holds while a change to the source beside it still moves it.

The 16 contaminated baselines were re-minted, each by dropping only the affected pattern and
adding it back so the mint-once rule left every sibling's evidence alone. They were safe to
re-mint because their stored value still equalled what the old rule computes today: proof that
nothing but bytecode had moved under them.

The class turned out to be wider than a list of directory names can reach.
[[adr-1d1eddbb6fbd]] made the matcher consult the repository's own `.gitignore` files and
kept these five as the floor — which is what generalises this argument from Python to every
language's build output. The case that proved it here was `benchmarks/.coverage`: a *file*,
rewritten by every test run under coverage, that no set of directory names could have
excluded.
