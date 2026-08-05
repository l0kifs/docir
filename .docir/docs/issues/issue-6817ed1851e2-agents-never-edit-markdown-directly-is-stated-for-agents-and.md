---
created: '2026-07-30'
description: The single most likely user action outside the CLI has no stated contract.
id: issue-6817ed1851e2
owner: maintainer
related:
- arch-1cfb1b212237
- arch-3e305bc76ff0
- issue-9cb85759076d
- issue-b47a1203baa2
- issue-5f979576ef7d
status: resolved
tags:
- integrity
- material
title: '"Agents never edit markdown directly" is stated for agents and never for humans'
type: issue
updated: '2026-08-05'
---

**Class:** unstated · **Severity:** material
**Flow:** arch-3e305bc76ff0 · **Step:** hand-editing a markdown file
**Question:** None · **Frequency:** continuous

## Finding

The rule "agents never edit markdown directly" is stated for agents but the boundary for humans is never stated, while the whole design invites hand-editing (git-backed files, `reindex` explicitly exists "after a hand-edit").

## What happens today

Hand-editing works and is expected. A hand-edit that breaks frontmatter is silently dropped from the corpus (issue-5f979576ef7d). A hand-edit that duplicates an id is caught only by `check`. Which fields are safe to edit by hand (body: yes; id: never; related: only with care) is nowhere written.

## Impact

The single most likely user action outside the CLI has no stated contract.

## Proposed default

Document a short 'what you may edit by hand' contract and require `docir reindex` after; make `check` the verification step.

## Resolution

FIXED 2026-07-29, as proposed, after two prerequisites the proposal assumed were already in place. The contract is now a per-field table in the packaged agent guide ("What a human may edit by hand") and in the README, ending in the required workflow: `docir reindex && docir check`. What it says: body / `docs-schema.yaml` / `docs/tags.yaml` are hand-editable; `tags`, `status`, `related` and `type` should go through the CLI because each is a Tier 0 rule a hand-edit bypasses; `id` never, because it is the primary key; `verified` never, because it asserts a human re-read the document and nothing can check that — writing it by hand is simply a false statement. It also states its own limits: a plausible-but-wrong `verified` or `created`/`updated` is indistinguishable from a real one. THE PROPOSAL SAID "make `check` the verification step" AND `check` COULD NOT BE ONE. Measured first: an unregistered tag and an undeclared status both passed silently, so two of the four fields the contract steers away from had no detection at all. issue-5f979576ef7d (reindex reports skipped files) and the new `unknown-tag`/`unknown-status` findings had to land before the contract could promise anything. Writing it first would have documented a guarantee the tool did not provide. FOUND WHILE WRITING IT: both files the contract declares hand-editable crashed with a raw `yaml.ParserError` traceback on a syntax slip. The parser's exception is not a `DocirError`, so it escaped the mapping that catches every *semantic* schema error — including the one added for issue-b47a1203baa2 days earlier. Now `SchemaError` / `TagRegistryError`, exit 3, on the two files a human is told to edit. Documenting them as editable while a bad indent produced a stack trace would have been the worst kind of contract.

## Superseded progress

2026-07-29 — the *prerequisite* is done; the contract itself is still unwritten. Measuring what `check` actually caught after a hand-edit showed the proposed default could not be honoured: `malformed`, `duplicate-id`, `dangling` and `unknown-type` were detected, but an unregistered tag and an undeclared status parsed cleanly and passed silently — the document stayed queryable by a tag the registry had never heard of, and a status outside its type's state machine stuck. Both are Tier 0 rules the CLI enforces on every write, so either one proves the file was edited outside it. `check` now reports them as `unknown-tag` / `unknown-status`, both **warnings**: the document is still readable and every edge still resolves, so by the ERROR_KINDS rule they are not damage — and promoting them would red-build every repo already carrying a hand-edited tag, which is exactly how `--strict` became unusable (issue-9cb85759076d). `--strict-all` serves anyone who does want hand-edits to block a merge. With issue-5f979576ef7d (reindex reports skipped files) this makes "reindex then check" a workflow that can actually be trusted, which is what the contract needs to be able to promise. Still unverifiable by `check`, and so must be stated as limits in the contract: a forged `verified:` date (unknowable in principle) and a hand-edited `created`/`updated`.

## Actors affected

- repository maintainer

## Evidence

- `README.md:100-102`
- `src/docir/modules/documents/application/services/maintenance_service.py:1-7`

---

Migrated from the discovery gap register (GAP-016); the register itself now lives in this store.
