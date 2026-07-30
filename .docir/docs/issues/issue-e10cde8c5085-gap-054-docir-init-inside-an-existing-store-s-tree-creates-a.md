---
created: '2026-07-30'
description: A nested `.docir` captures every command run beneath it, and the parent
  store's `check` never sees those documents.
id: issue-e10cde8c5085
owner: maintainer
related:
- ref-cb2beaa41604
- arch-90c90751344f
- adr-20eec6e2e2ca
status: resolved
tags:
- cli
- material
title: GAP-054 — `docir init` inside an existing store's tree creates a shadowing
  store in silence
type: issue
updated: '2026-07-30'
---

# GAP-054 — `docir init` inside an existing store's tree creates a shadowing store in silence

**Class:** missing · **Severity:** material · **Confidence:** observed
**Flow:** FLOW-004 (adoption)
**Frequency:** unknown; one `docir init` in the wrong directory

## Finding

`docir init sub/` inside a repository that already has a `.docir/` at its root creates a
second store and says nothing about the first. Store discovery walks *up* for the nearest
`.docir`, so from that moment every command run anywhere under `sub/` resolves to the
nested store.

## What happens today

OBSERVED. Parent store initialised at the root with three documents; `docir init team/`
exits 0, stderr silent. `docir add` run from `team/` reports
`store: .../team/.docir` — also silent — and the document lands there. The parent store
holds 3 documents, the nested one holds 1, and `docir check` at the root cannot see the
nested document at all: it is not orphaned, not dangling, not anything. It is in a
different corpus.

## Impact

The failure is quiet in both directions. Nobody is told a second store was created, and
nobody is told which store a write landed in unless they read the `store` field. Documents
split across two corpora retrieve separately, so `docir context` from the root silently
stops returning half the project's decisions, and the CI gate over the root store passes
while the nested one is unchecked.

docir already recognises this class of problem and handles it elsewhere: a write that falls
back to the global `~/.docir` from inside a git repository warns on stderr, because "your
document landed in a store you may not have meant" is worth interrupting for
(`Settings.is_unintended_global_fallback`). A nested project store is the same sentence
with a different store.

Not a contradiction of ADR-0009. That decision says `new_store_home` deliberately does not
walk up for an existing `.docir`, because reusing a parent store is the wrong answer when
the caller asked for a new one — and that is right. "Do not reuse it" and "do not mention
it" are different decisions, and only the first was made.

## Proposed default

`init` warns on stderr when `discover_project_home()` finds a store above the directory it
is about to create one in: name the enclosing store, say that commands run beneath the new
one will use the new one, and proceed. A flag (`--nested`) could silence it if the
shadowing is deliberate. Do not refuse: monorepo subprojects with their own stores are a
legitimate layout, which is why this is a warning rather than an error.

## Actors affected

- AI coding agent
- repository maintainer
- CI job

## Evidence

- `src/docir/config/settings.py` (`discover_project_home`, `new_store_home`,
  `is_unintended_global_fallback`)
- `src/docir/entry_points/composition.py` (`initialize_store`)
- PROBE-R7 / PROBE-R7b in the 2026-07-30 probe log

## Resolution

FIXED 2026-07-30. `docir init` now warns on stderr when a project store already exists above the one it is creating, naming the enclosing store and saying that commands run beneath the new one will use the new one and that the outer store's `check` will not see documents added there. `InitResult.enclosing_home` carries it, so the JSON path reports it too. It warns rather than refuses: a monorepo subproject with its own store is a legitimate layout, which is exactly why ADR-0009 has `init` create rather than reuse — the fix is to the silence, not to the rule. The check lives in `config/settings.enclosing_project_home`, beside `resolve` and `new_store_home`, for the reason recorded on the latter: a rule about which store is in play that lives anywhere else escapes the review that reads those two. It starts the walk at the store's own directory so an explicitly-named store (`--home /srv/docs`) still notices a sibling `.docir`, and skips a candidate equal to the new home so re-running `init` does not report the store against itself. Verified by injecting the bug: with the lookup stubbed to None, five of the eight new guards fail.
