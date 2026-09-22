---
code:
- src/docir/entry_points/composition.py
code_baseline:
  src/docir/entry_points/composition.py: 88d0cea954b3
created: '2026-09-18'
description: The generated ignore list omits release-check.json, and an existing store's
  copy is written once by init and never brought up to a later release — so the feedback/
  entry never reaches the stores that predate it.
id: issue-712f5bd17908
owner: maintainer
related:
- adr-7144cf291b1a
- adr-31aa7aa60d11
status: resolved
tags:
- cli
- release
title: The store's generated .gitignore misses release-check.json and is never refreshed
type: issue
updated: '2026-09-22'
verified: '2026-09-22'
verified_code:
  src/docir/entry_points/composition.py: 88d0cea954b3
verified_content: 2656e4f3d9dd
---

## What is wrong

The store's generated `.gitignore` states a guarantee — *"Only `docs/` +
`docs-schema.yaml` are committed"* — that it does not keep, in two directions.

**The list is short one file.** `release-check.json` is the `self status` cache:
docir writes it into `home`, it differs on every machine and it is dated. It
appears in no ignore list, including one this same release generated seconds
earlier.

**The file is written once and never again.** `initialize_store` writes it under
`force or not gitignore_path.exists()`, so every entry docir has added since a
store was created lands only in stores created afterwards. `self upgrade`
refreshes the agent instruction file and not this one, though its own help
promises to "bring this store and its generated files in line with it".

## Measured

A store created by this release, in a git repository, after one `self status
--refresh`:

```
.docir/.gitignore  docs/  docs-schema.yaml  index.db  release-check.json
grep -c release-check .docir/.gitignore  ->  0
```

A store created before the `feedback/` entry existed, upgraded with
`self upgrade --no-package`: the entry is still absent afterwards.

## Why it matters

The second half lands on the feature the entry exists for. The `docir-feedback`
skill writes its draft to `<store>/feedback/` and tells the agent that directory
"is gitignored by stores created with this release". In a store created before
it, the first draft appears as untracked, one `git add -A` from being committed —
and that draft is the one thing in the store nobody has reviewed for redaction
(adr-7144cf291b1a).

The first half is smaller and constant: a machine-local cache that produces a
diff on any checkout that runs `self status`.

`docir check` reports neither; neither is a corpus finding.

## What would fix it

Add `release-check.json` to the generated list, and give `self upgrade` a step
that brings an existing store's file up to the running build.

**Append the missing entries rather than rewriting the file.** `init --force`
regenerates it because the caller asked for exactly that. `self upgrade` is
routine, and a store's ignore file is somewhere people add their own lines, so
replacing it with the constant would delete work nobody was asked about — the
defect `--force` already grew `--force-schema` to avoid. Appending converges on
the same set from any starting point and is idempotent; rewriting is neither.

Guard it by walking a store docir has actually written to and asserting every
path it left is ignored, rather than by reading the template back. A test that
reads the constant passes on the constant being whatever it is, which is how a
file docir writes came to be missing from it in the first place.

## Reported

GitHub issue #21, against 0.27.0, reproduced with and without the daemon.

## Resolution

FIXED 2026-09-18. `release-check.json` is in the generated list, and
`self upgrade` now tops up an existing store's file between `agent update` and
`check` — the two generated-file steps together, with `check` still last.

Entries are **appended under a comment naming the version that added them**,
never rewritten over. `init --force` regenerates the file because the caller
asked for exactly that; an upgrade is routine, and a store's ignore file is
somewhere people add their own lines. Appending also converges from any starting
point and is idempotent, which rewriting is not.

Exercised on docir's own store, which was itself one of the aged ones — its
committed `.gitignore` carried neither entry:

```
gitignore_added: ["release-check.json", "feedback/"]
```

The existing lines and the comment above them are untouched in the diff, and a
second `self upgrade` adds nothing and rewrites nothing.

Both directions across the release boundary, per adr-ab4598c6f707: a store
created by the 0.27.0 wheel gains only `release-check.json` (it already had
`feedback/`), and both builds read it and pass `check --strict` afterwards.

The guard walks a store docir has written to and asks **`Settings`** which paths
live in it, by introspection rather than by a list — so the next path added to
`Settings` is covered on the day it is added. It asserts *which* four it found,
because a count cannot tell "all of them are ignored" from "`Settings` stopped
exposing any". Three injections, each proven to fail it: dropping the entry from
the template, dropping the refresh step from `upgrade_store`, and rewriting the
file instead of appending — the last one fails on the line somebody added, which
is the property the append exists for.

The runbook [[run-f4a756206fe0]] said this file was one nothing refreshes for
you, and the `docir-feedback` skill told the agent to run `init --force` when a
draft showed up untracked. Both now say what the command does.
