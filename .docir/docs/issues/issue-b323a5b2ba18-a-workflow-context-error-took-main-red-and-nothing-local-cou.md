---
code:
- .github/workflows/**
- pyproject.toml
created: '2026-08-25'
description: A job-level env used the runner context, so GitHub rejected ci.yml and
  zero jobs ran; actionlint now gates workflows locally and in CI.
id: issue-b323a5b2ba18
owner: maintainer
related:
- issue-82b01d7f80d0
- issue-87410666c867
status: resolved
tags:
- cli
- testing
title: A workflow context error took main red, and nothing local could have caught
  it
type: issue
updated: '2026-08-25'
---

## What happened

A commit set `FASTEMBED_CACHE_PATH: ${{ runner.temp }}/fastembed-cache` as a
job-level `env:`. The `runner` context is not available there — only `github`,
`inputs`, `matrix`, `needs`, `secrets`, `strategy` and `vars` are — so GitHub
rejected the file outright. **Zero jobs ran.** The failure said only "This run
likely failed because of a workflow file issue", and the workflow's `name`
stopped resolving, so every run of it started listing as `.github/workflows/ci.yml`
instead of `CI`.

The check that passed before the push was `yaml.safe_load`. That is a far weaker
claim than "GitHub accepts it", and the whole class of error lives in the gap
between the two.

## Why it is worth a gate

A workflow file is the one thing in this repository that **cannot be validated by
running it**. Every other gate is reproducible locally: the tests run, `tach`
walks the imports, `docir check` reads the corpus. A workflow only runs on a
push, so the first honest feedback arrives after main is already red.

## The fix

`actionlint` runs as a gate, locally and in CI. It ships as `actionlint-py`, a
wheel that vendors the Go binary, so it runs like every other gate
(`uv run actionlint`) rather than needing a Go toolchain or Docker — which
matters, because a gate that only fires after a push cannot stop the push.

Verified by injecting the exact bug back into `ci.yml`: it names the line, the
context and the rule, and exits 1. Against the three current workflows it exits
0, so nothing pre-existing had to be suppressed to adopt it.

## What it does not cover

`actionlint` checks the workflow's shape, not its effect. It had nothing to say
about the two real CI defects that preceded it — a gate reading an unbuilt index
(issue-87410666c867) and a cache naming a directory nothing writes to
(issue-82b01d7f80d0). Both were valid workflow files doing the wrong thing, and
both were found by reading a run's output rather than by any linter.
