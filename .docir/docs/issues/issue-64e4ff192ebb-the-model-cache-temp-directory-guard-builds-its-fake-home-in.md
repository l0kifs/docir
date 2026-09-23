---
code:
- tests/config/test_model_cache_home.py
code_baseline:
  tests/config/test_model_cache_home.py: 0ec33891d2a7
created: '2026-09-23'
description: The guard uses tmp_path for a home it asserts is not under the temp directory,
  so it fails on Linux whatever the code does, and a symlinked temp dir hid that on
  macOS.
id: issue-64e4ff192ebb
owner: maintainer
related:
- adr-78090be868ec
- issue-c5c089bcc1b2
status: resolved
tags: []
title: The model-cache temp-directory guard builds its fake home inside the temp directory
type: issue
updated: '2026-09-23'
---

## What is wrong

`test_it_is_not_under_the_temp_directory` builds its fake home from `tmp_path` — which is
itself under the temp directory, because that is what `tmp_path` is for. So the path it
asserts about is inside the very directory the assertion says it stays out of, and the test
fails whatever the production code does.

```
FAILED tests/config/test_model_cache_home.py::test_it_is_not_under_the_temp_directory
AssertionError: assert PosixPath('/tmp') not in <PosixPath.parents>
  where PosixPath('/tmp/pytest-of-runner/pytest-0/test_it_is_not_under_the_temp_0/user/.docir/models')
```

## Why nobody saw it

It passed on the machine it was written on. `tempfile.gettempdir()` reports
`/var/folders/…/T` on macOS while `tmp_path` reports the symlink-resolved
`/private/var/folders/…/T`, and `in .parents` compares path components, not filesystem
identity — so the two never matched and the broken fixture stayed invisible. The test was
green there for a reason unrelated to the property it asserts.

`model_cache_home()` is correct and always was. This is a defect in the guard.

## Measured

CI on `main` has failed on this one test, and only this one, for every run since it landed in
`08e909d` (2026-09-18) — ten consecutive runs across five commits, each otherwise green
through ruff, actionlint, ty, vulture, tach, contract-sync and 4572 other tests. Because the
test step fails, the four store gates after it (`reindex`, `doctor --strict`, `check --strict`,
the decisions notice) are **skipped**, so the branch's document integrity has not been checked
by CI on any of those commits either.

A red `main` that stays red is the failure mode behind [[adr-e53c813d2f13]]'s argument one
level out: a gate nobody can distinguish from noise is a gate that stops being read.

## Resolution

FIXED — the home is built from the filesystem root (`Path(temp.anchor) / …`) instead of from
`tmp_path`, and both sides of the comparison are resolved so a symlinked temp directory cannot
hide a mismatch again. A precondition assertion states the fixture's own requirement — the
fake home sits outside the temp directory — so a later simplification back to `tmp_path` fails
loudly on both platforms rather than only on Linux.

Verified by injecting the defect the guard exists to catch: `model_cache_home()` returning
fastembed's `tempfile.gettempdir()/fastembed_cache` fails it.

This is the testing rule's own shape, arriving from the other side: a test that has never
failed has not been shown to work, and this one had never *passed* anywhere it mattered.
