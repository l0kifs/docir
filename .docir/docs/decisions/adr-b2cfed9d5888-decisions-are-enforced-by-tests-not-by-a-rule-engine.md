---
code:
- src/docir/modules/documents/domain/services/code_globs.py
- .github/workflows/ci.yml
created: '2026-08-06'
description: 'Gap 6 closes as a decision: a testable decision is bound to the test
  that enforces it, CI prints the decisions a branch touches as a notice, and docir
  builds no DSL, sandbox or per-language analyzer.'
id: adr-b2cfed9d5888
owner: maintainer
related:
- ref-a6db21f52427
- issue-90aea6d1b891
- adr-bd7c4f3c5764
- arch-0a3c2d6d54a6
status: accepted
tags:
- architecture
- integrity
- cli
title: Decisions are enforced by tests, not by a rule engine
type: decision
updated: '2026-08-06'
---

## Context

Gap 6 of the competitive survey (ref-a6db21f52427) is the one docir has never answered: archgate
binds an ADR to an executable rule (`.rules.ts`) that fails CI when the code violates it; trackfw
enforces ADR → requirement → roadmap traceability. docir validates the *document graph* — ids,
edges, statuses, tags, staleness — and says nothing about the code the documents are about. That
is the "why is this document worth writing" argument, and it was the last strategic gap left.

Until 2026-08-06 the gap was also **blocked**: no field named the code a decision governed, so a
rule had nothing to bind to. `code:` closed that (issue-90aea6d1b891), and with it came
`docir query --code <path>` — "which decisions does this branch have to be read against". So the
question is now live and narrow: given the binding site, does docir build the engine?

## Decision

**No engine. A decision that can be mechanically enforced is enforced by a test, and docir's job
is to record which test that is.**

Three parts, in order of how much they cost:

1. **The rule is a test.** `docir update <id> --set-code "tests/test_auth_rotation.py"` binds a
   decision to the thing that already fails CI when the code contradicts it — written in the
   project's language, run by the project's runner, with the project's fixtures. `check`'s
   `unmatched-code` warning then covers the failure mode a rule file has too: the test was
   deleted or moved and the decision is no longer enforced by anything. Nothing new is built.

2. **The routing is a pull, at review time.** `docir query --code $(git diff --name-only
   origin/main...HEAD)` lists the decisions a branch touches, and CI prints it as a **notice**.
   Never a gate: a check that fails because you touched governed code punishes the ordinary case,
   and one that passes when you click "acknowledged" is a nag a bot can clear rather than a human
   reading a decision — the argument adr-bd7c4f3c5764 already made for staleness, where delivery
   is pull and `--verified` is the only thing that clears it.

3. **What docir does not own**: a rule DSL or plugin API, a sandbox for executing user-supplied
   rules, and language-specific static analysis. Each is a product on its own. archgate is
   TypeScript-only, and not by accident — a rule engine is bound to one language's AST, while
   docir's corpus is language-agnostic and its thesis is markdown compiled into an index.

## Consequences

- **Gap 6's cell stays ❌ against archgate's ✅, honestly.** docir does not fail CI when code
  contradicts a decision; it names the decisions that apply and relies on the project's own tests
  for the ones that are testable. The gap closes as a *decision*, like gaps 3 and 8 — reasoned
  against rather than deferred.
- A decision that is not testable ("we do not use lazy loading anywhere") gets no mechanical
  enforcement, only the review-time notice. That is the honest limit: the alternative is a
  heuristic promoted to a hard error, which is the documented overengineering trap of the
  validation tiers.
- The `code:` field now carries two meanings that stay deliberately undistinguished — "this
  document is about that code" and "that test enforces this decision". A `kind` on the entry was
  considered and rejected: nothing reads the distinction, and a schema that records unused
  structure is the thing typed relation kinds had to be rescued from (adr-234b956a48d8).
- **The trigger for revisiting is evidence, not a competitor's feature list**: repeated cases
  where a governed decision was violated in a branch whose notice listed it. The `code:` links and
  the query make that measurable; "archgate has it" never was.

## Alternatives considered

- **An executable-rule engine (archgate's shape).** Rejected on cost and fit: a DSL, a sandbox, a
  per-language analyzer, and a second thing for a reader to keep true beside the document itself.
- **A blocking review-acknowledgement gate.** Rejected: clearable without reading, which makes it
  a ritual. Same failure mode as an automated staleness nag.
- **Deriving enforcement from lint configuration.** Rejected as renaming: a lint rule is already
  the enforcement; docir binding to its config file adds a layer without adding a check.
