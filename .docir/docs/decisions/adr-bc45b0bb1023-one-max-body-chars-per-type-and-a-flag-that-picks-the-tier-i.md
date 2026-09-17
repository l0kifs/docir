---
code:
- src/docir/modules/documents/infra/schema_loader.py
- src/docir/modules/documents/domain/services/validation.py
- src/docir/modules/documents/domain/schema.py
code_baseline:
  src/docir/modules/documents/domain/schema.py: c0ea053f1c39
  src/docir/modules/documents/domain/services/validation.py: 18b842a51fe9
  src/docir/modules/documents/infra/schema_loader.py: 4cbd9ed6460b
created: '2026-09-15'
description: One max_body_chars per type, read by both tiers; max_body_chars_enforce
  decides whether it refuses the write or only reports it, so the Tier 2 smell is
  never a second number.
id: adr-bc45b0bb1023
related:
- issue-5d6a5e854d11
- arch-ad342aae8293
status: accepted
tags:
- schema
- integrity
title: One max_body_chars per type, and a flag that picks the tier it acts at
type: decision
updated: '2026-09-17'
---

## Context

`max_body_chars` shipped as a Tier 2 number: `lint --deep` read it, printed
`scope-creep`, and nothing stopped a document from growing. That is the right
shape for a *smell* — a register split in half is two half-registers, which is
the argument issue-5d6a5e854d11 settled — but it leaves a store with no way to
say "documents of this type do not get longer than this", enforced.

The tier rule (arch-ad342aae8293) says a heuristic is never promoted to a hard
error, and a naive reading of "make `max_body_chars` blocking" does exactly
that.

## Decision

**One number, read by both tiers. `max_body_chars_enforce` picks the tier it
acts at.**

`max_body_chars: N` means Tier 0 refuses a write that would leave the body over
N **and longer than it already was**, with `BodyTooLargeError` — its own exit
code, 9, because the caller's move is to split the document rather than to
rewrite a field, and a script branching on `ValidationError`'s 2 would retry the
same body forever. Tier 2's `scope-creep` reads the same N and still only
suggests.

`max_body_chars_enforce: false` is exactly the behaviour the key had before it
gained a tier: nothing is refused, `lint --deep` still names the document, and
the write carries `body_limit_notice` back to the caller — on stderr for the
CLI, in the payload for MCP. Set without a positive `max_body_chars` to relax it
is a `SchemaError`, since a key that reads as configuration and configures
nothing is worse than one refused.

This is not a promoted heuristic. The number is the type's own — absent, Tier 0
does nothing at all — and so is the tier it acts at.

### The second key that was built and dropped

The first implementation split them: `max_body_chars` as the ceiling,
`advisory_body_chars` inheriting the Tier 2 role. It buys exactly two
configurations — "suggest at 8000, refuse at 12000", and "refuse at N, never
suggest" — and costs:

- **A rename for every store that already set the key**, plus a silent change to
  what `scope-creep` reports for that type.
- **A second number that can only disagree with the first.** A type that refuses
  a write at N has already said what "too long" means for it.

The early-nudge case is the only real argument for the split, and it is weaker
than it looks: `lint --deep` is opt-in and off the write path, so the nudge
arrives when somebody runs the linter, not when the document grows.

### What holds the Tier 0 half up

**No default, ever.** Absent means no ceiling, and no shipped type declares one.
The schema merges core → profiles → inline on *every* command, so a default
would begin refusing writes to documents that were legal when they were written,
on a release with nothing in `git diff` to point at — the argument the
`schema-drift` warnings already make, one tier louder.

**`0` still turns off both halves**, which is what it already meant: no ceiling,
and never "too long". This store's `reference` line is untouched by this change.

**Growth is the trigger, not size.** A document already over the limit still
takes `--set-title`, `--status`, `--set-tags`, `--type` and a *shorter*
`--replace-body`. Refusing every write to an oversized document blocks the one
edit that fixes it and leaves hand-editing markdown as the only repair, which
the CLI-is-the-only-write-path thesis forbids. The ceiling stops growth; the
lint is what reports the backlog that is already there.

**The mechanical rewrites are exempt.** A `tag rename`, a forced delete's
edge-strip and `check --fix` do not run through `add`/`update` and so never
reach the check. One refusing halfway through a corpus-wide rewrite leaves it
half-applied, and a repair that refuses to run is not a repair.

**The loader refuses what it can name.** A negative limit is every body's
ceiling — refused at load rather than refusing every write to the type one
command later. So is a non-boolean `max_body_chars_enforce`, and the dead
relaxation above.

## Consequences

- A store opts in per type. Nothing changes for a store that does not, and no
  store has to rename anything.
- A store that set `max_body_chars` as *advice* gets a ceiling at that number on
  upgrade. The recovery is one added line, `max_body_chars_enforce: false`, and
  it is not silent for long: growth is what is refused, so the first write that
  crosses says so by name.
- `max_body_chars_enforce` joins `schema_shape.describe`, so `check` reports it
  once as `schema-drift` per type against an older baseline — measured on a
  store built by 0.26.0 — cleared by `reindex`.
- `BodyTooLargeError` takes exit code 9. The next error class takes 10.
- The guards were verified by injection: dropping the growth carve-out, the
  `add` call site, the enforce flag, and the loader's two refusals each fail
  exactly one test.
