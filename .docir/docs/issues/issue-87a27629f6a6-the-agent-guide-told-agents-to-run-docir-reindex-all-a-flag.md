---
created: '2026-07-30'
description: An agent following the guide after a merge gets an error instead of a
  rebuilt index, and the merge-safety workflow the guide exists to teach silently
  does not run.
id: issue-87a27629f6a6
owner: maintainer
related:
- adr-3a2d5ee7bc84
- arch-90c90751344f
- issue-996b567e5131
status: resolved
tags:
- agents
- material
title: The agent guide told agents to run `docir reindex --all`, a flag that does
  not exist
type: issue
updated: '2026-08-05'
---

**Class:** incorrect · **Severity:** material
**Flow:** arch-90c90751344f · **Step:** the packaged agent guide (`modules/agents/infra/templates/skill.md`)
**Question:** None · **Frequency:** every agent that follows the post-merge instructions

## Finding

The canonical agent instructions told agents to run `docir reindex --all`, a flag that does not exist — at the single most important recovery step ("After any merge/pull").

## What happens today

FOUND AND FIXED 2026-07-26 while propagating the issue-996b567e5131 change. `docir reindex --all` errors with "No such option: --all". The guide is the one artifact `docir agent install` ships into other repositories, so the bad instruction was being distributed to every adopting project. Nothing validated the template against the CLI it documents.

## Impact

An agent following the guide after a merge gets an error instead of a rebuilt index, and the merge-safety workflow the guide exists to teach silently does not run.

## Proposed default

FIXED (now `docir reindex`). The durable fix is a test that extracts every `docir ...` invocation from the template and asserts each command and flag exists in the CLI's own JSON `--help` — the check that would have caught this. Not yet written.

## Resolution

Typo corrected 2026-07-26; the guard written 2026-07-28, which is what closes this. `tests/entry_points/test_agent_guide_matches_cli.py` extracts every `docir ...` the guide presents as runnable — fenced-block lines and inline code spans — and resolves each against the CLI's own command tree, introspected from the Typer app rather than shelled out, so it cannot drift from the binary. 29 invocations, one parametrized case each. Attribution tested by injecting three defects into the template and confirming each fails: an unknown flag (`reindex --all`, the original), an unknown subcommand (`schema dump`) and an unknown top-level command (`repair --fix`). One prose change was needed to make the rule enforceable: the guide said "One `docir import`-style bulk pass", a backticked command that deliberately does not exist. Reworded to "a single bulk-import pass". That is the right outcome rather than an extractor exemption — an agent will try to run a backticked command whatever the sentence around it says, which is this gap's exact failure mode. TWO DEFECTS IN THE GUARD ITSELF, both found by testing it against injected bugs rather than by reading it: (a) the inline-span regex paired backticks across the whole document, but a ``` fence *is* backticks — each fenced block was swallowed into one giant "span" and every pair after it shifted. It extracted a plausible 28 invocations while missing the exact line the test exists to catch. Prose is now separated from fenced blocks before the regex runs. (b) resolution fell back to the parent group on an unknown word, so `docir schema dump` validated against `docir schema`. A word in a *group's* subcommand position must now resolve; only a leaf command's trailing words are treated as arguments. The first version of the guard-the-guard asserted a *count* of invocations, which both defects passed. It now names specific invocations that must be found, each reachable from a different part of the document. A count cannot say which line went missing.

## Actors affected

- AI coding agent
- repository maintainer

## Evidence

- `src/docir/modules/agents/infra/templates/skill.md`
- `src/docir/entry_points/cli/app.py:409-417`

---

Migrated from the discovery gap register (GAP-040); the register itself now lives in this store.
