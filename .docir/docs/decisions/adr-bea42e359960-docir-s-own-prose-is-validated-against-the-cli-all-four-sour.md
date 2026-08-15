---
code:
- tests/entry_points/test_agent_guide_matches_cli.py
created: '2026-08-15'
description: Why the command-resolution guard covers CLAUDE.md and the project store
  as well as the shipped guide, why a retired binary name needs a separate check,
  why the unreal-command exemption list may only shrink, and why type/status values
  are checked against the shipped vocabulary.
id: adr-bea42e359960
owner: maintainer
related:
- issue-87a27629f6a6
- adr-3a2d5ee7bc84
- arch-0a3c2d6d54a6
- adr-b2cfed9d5888
status: accepted
tags:
- docs
- testing
- agents
title: docir's own prose is validated against the CLI, all four sources
type: decision
updated: '2026-08-15'
---

## Context

issue-87a27629f6a6 closed a narrow version of this: the packaged agent guide told
agents to run a `reindex` flag that has never existed, at the single most important
recovery step, and nothing checked the guide against the CLI it documents. The fix was
a test that introspects the Typer tree from `cli.app` and resolves every `docir ...`
code span in `modules/agents/infra/templates/skill.md`, later extended to `README.md`.

That covered what an **adopter** reads. It did not cover what an agent working *in this
repository* reads, which is `CLAUDE.md` and the project store — and CLAUDE.md's first
instruction is to read the store. A review of the corpus on 2026-08-15 found that half
had rotted exactly the way the guide had:

- `arch-1cfb1b212237`, the document CLAUDE.md sends readers to first, carried **96**
  invocations of the binary's previous name, plus `--set-field` (never shipped),
  `reindex --all` (the very flag issue-87a27629f6a6 is about) and a command table
  listing 11 of the 22 commands that exist.
- Two active documents asserted `docir check --fix` did not exist, years of `--fix`
  after it shipped, and one asserted there was no similarity floor after `--min-score`
  landed.

None of it was found by reading the suite. All of it was found by running the commands.

## Decision

**One oracle, five sources.** `tests/entry_points/test_agent_guide_matches_cli.py`
resolves every `docir ...` code literal in the packaged guide, `README.md`,
`CLAUDE.md`, every file under `.docir/docs/**`, and every docstring under `src/`
against the same introspected command tree. A document in the store, a docstring on
the method that implements the command, and the guide shipped to other repositories
are judged by identical rules, because they fail identically.

The source half was added last and found 37 more stale invocations, which is the
argument for the rule in general: each source was believed clean until the same
oracle was pointed at it. A docstring is not a lesser document — it is the one a
reader reaches by following the code, and it names commands constantly.

Three parts are load-bearing and are the reason this is a decision rather than a patch.

### A retired binary name needs its own check, in every source

The extractor is anchored on `docir `. A code span opening with the binary's *previous*
name therefore never reaches it — the line reads as "nothing to validate", which is
indistinguishable from "valid". That is precisely how one document accumulated 96 of
them while the guard beside it was green, and how `src/` kept 37 after the markdown
side was clean. `_RETIRED_BINARIES` matches an old name
followed by a word that is a live subcommand; requiring the second word to resolve is
what keeps the docs *directory* and `docs-schema.yaml` out, since neither is followed
by a space and a command.

Generalising: a guard anchored on the correct spelling cannot see the incorrect one.
Whenever a name changes, the retired name needs an explicit check or the rename is
unenforced in exactly the places nobody re-reads.

### Prose that names an unreal command is exempted by list, and the list may only shrink

A corpus of decisions necessarily writes commands that do not exist: `docir import` was
proposed and rejected, `docir repair` is the name of the gap `check --fix` closed, and
the probe logs quote `reindex --all` as the defect they record. Rewriting those would
destroy the argument. `_DELIBERATELY_UNREAL` maps the leading words to *why*, and
`test_every_exemption_is_still_needed` fails when an entry stops matching anything.

That inverse test is the point. An exemption that outlives its prose becomes a blind
spot pointed at the exact command most likely to be typed wrong later — if `docir
import` ever ships, a stale entry would swallow every future typo in it silently.
Dropping the entry is part of shipping the command, and this is what says so.

An exemption is never the fix for a document that tells a reader to *run* something.
issue-8f6576cd7bc9 instructed the reader to supply a missing steward with an update
call naming a bare `--owner`; the flag is `--set-owner`, and that took the correction,
not an entry. Writing the wrong invocation here as a code span would have failed this
document too — as an earlier draft of it did.

### Type and status values are checked; other values are not

Resolving a command proves the *shape* of a line and nothing about its meaning. A
filter reading `--type decision --status open` parses, runs, exits zero and matches
nothing — forever — because `decision` goes proposed -> accepted and never holds an
`open`. That is worse than a broken command, which at least announces itself.

So `--type` and `--status` values are checked against the **core merged with every
bundled profile**, not against the schema this store resolved. Which profiles a store
enables is a local choice; whether `decision` declares an `open` status is not. An
example may therefore reach for a `test_plan` from the qa profile that this repository
does not turn on, and still fail if it pairs that type with a status the type never
declares. Without a `--type` to scope it, a status only has to be one some shipped type
declares, because `update <id> --status resolved` names no type and cannot.

Other values stay unchecked, and the line is deliberate: a tag, an id, a heading or a
path is a fact about one corpus, while a type and its statuses are facts about docir.
Checking the first class would bind this test to the contents of a store, and the guard
would then fail for anyone who wrote a different document.

The corpus-level instrument remains and is not replaced by this: Tier 1's
`unknown-status` and `unknown-type` findings judge *documents*, which is where a wrong
status actually costs something. This guard judges prose, which is where the wrong
status is learned.

## Consequences

- Extraction had to get stricter before it could get broader. Global flags precede the
  command (`docir --pretty get <id>`), slash alternatives occur below the top level
  (`docir agent install/update`), and a `$(...)` substitution carries another program's
  flags. All three produced false failures on correct prose and are now handled in the
  shared helpers, so the guide and README benefit too.
- The suite grew from 1154 to 1779 tests. They are parametrized per invocation, so a
  failure names the line rather than a count.
- Writing about docir in docir is now constrained: a command named in backticks must be
  real or exempted. Prose stays prose. This document's own first draft tripped the
  retired-binary check by quoting an example, which is the rule working.
- All fourteen failure modes were verified by injection — a wrong flag, an unknown
  subcommand, an unknown command, a misplaced global, a retired binary, an unreal
  subcommand, a stale exemption, a moved store path, and six shapes of bad
  `--type`/`--status` value — because a guard that has never failed has not been shown
  to work, and because two earlier versions of this same test silently checked nothing.
  The value check was run against five legitimate lines as well, since a guard that
  rejects correct prose gets deleted rather than obeyed.
- Extending the checker turned up its own bug: the placeholder rule knew `...` and not
  the typographic `…` that prose actually uses, so an ellipsis read as a type name. A
  checker that understands only one spelling of a convention is the same failure as one
  anchored on only the current binary name.
