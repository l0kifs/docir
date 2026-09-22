---
code:
- scripts/cli_oracle.py
- tests/entry_points/test_agent_guide_matches_cli.py
code_baseline:
  scripts/cli_oracle.py: 7de2a0db4c96
  tests/entry_points/test_agent_guide_matches_cli.py: 314183633af5
created: '2026-09-22'
description: The oracle checks that each line the prose carries resolves; nothing
  checked that every command is carried, so doctor and two daemon subcommands went
  unlisted.
id: issue-193c443791c5
owner: maintainer
related:
- adr-bea42e359960
- issue-d4b194eca41d
- arch-7fd54a82f7d6
status: resolved
tags:
- docs
- testing
title: A command the CLI-surface document never names is invisible to every prose
  guard
type: issue
updated: '2026-09-22'
---

## What is wrong

Every guard over docir's own prose asks the same question: does a line the text *carries*
resolve? `cli_oracle` introspects the live command tree and checks each `docir ...` span
against it, across six surfaces.

A command the prose never mentions carries no line. It is invisible to all of them.

## Measured

[[arch-7fd54a82f7d6]] states its job in its first sentence — "Every command below exists in
`docir --help`" — and its table had 34 rows, every one of which resolved. Compared against
the tree in the other direction it was missing **`doctor`**, `daemon status` and `daemon
stop`. `doctor` has an ADR of its own and is the command an adopter runs when something is
wrong.

Found by reading the document against its code, not by a guard, during the `code-changed`
pass. Nothing would have found it otherwise: a table cannot be checked for what is not in it
by looking at what is.

## What would fix it

Assert the reverse — every command in the tree appears in the document whose stated job is
the CLI surface — and make the document claim both directions rather than one.

Hidden commands are exempt. `daemon serve` is how the client respawns the daemon, not
something a reader should ever type, so demanding it be documented would be demanding the
wrong thing. That needs the oracle to know which commands are hidden, which it did not.
