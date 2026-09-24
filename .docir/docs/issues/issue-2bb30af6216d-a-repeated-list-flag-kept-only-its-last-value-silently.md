---
code:
- src/docir/entry_points/cli/emit.py
- src/docir/entry_points/cli/write_cmds.py
- src/docir/entry_points/cli/app.py
code_baseline:
  src/docir/entry_points/cli/app.py: 455f3454fc4f
  src/docir/entry_points/cli/emit.py: 2fdfefe88a62
  src/docir/entry_points/cli/write_cmds.py: c88c302b7e48
created: '2026-09-24'
description: Why add --code a --code b wrote only b, and why every list flag now takes
  both the repeated and the comma-separated form.
id: issue-2bb30af6216d
owner: maintainer
related:
- arch-7fd54a82f7d6
- issue-413546da5db7
status: resolved
tags:
- cli
- agents
- integrity
title: A repeated list flag kept only its last value, silently
type: issue
updated: '2026-09-24'
---

## Symptom

`docir add --code "a/**" --code "b/**"` wrote `code: [b/**]`. `--tags x --tags y`
was read as `y` — the error named `unknown tag 'y'` and never `x`. No error, no
warning. `--code "a/**,b/**"` kept both. Reported from a scratch store on
2026-09-23 by the agents-docir package, whose id-collision procedure re-creates
documents through `docir add`.

A document written that way lost globs and edges, and `docir query --code`
stopped finding the decisions that govern those files.

## Cause

The CLI had two conventions for a list-valued flag. Every read-side one —
`query --type/--status/--tag/--code`, `context --also`, `--store`,
`agent install --agent` — is repeatable. The seven write-side ones — `add
--tags/--related/--code`, `update --set-tags/--set-related/--set-code`, `init
--profiles` — took one comma-separated string. Click keeps the last occurrence of
a single-valued option, so an agent that learned the read form lost everything
but the last value on the write, silently.

## Resolution

The seven flags are repeatable, and every occurrence is comma-split, so both
forms mean the same list: `--code a/** --code b/**,c/**` is three globs, in
order. `""` still clears a `--set-*` list and an absent flag still leaves it
alone.

A repeat is dropped, first occurrence kept. Merging turns `--tags x --tags x` —
read as `x` while the last value won — into `x, x`, and a document holds each
tag, glob and identical edge once anyway (issue-413546da5db7); `init --profiles`
has nothing behind it that would, and would commit the repeat into the schema.

`split_csv` takes `list[str]`, so a list flag declared single-valued again fails
`ty check`. The packaged skill still teaches the comma form: its committed copy
is read by teammates on 0.29.0 and older, where a repeat still loses values.
