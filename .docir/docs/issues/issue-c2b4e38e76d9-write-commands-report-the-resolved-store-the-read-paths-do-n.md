---
created: '2026-07-30'
description: Introduced by the GAP-023 fix, which reasoned about writes only.
id: issue-c2b4e38e76d9
owner: maintainer
related:
- adr-20eec6e2e2ca
- arch-f220a644d654
- ref-1509d5dbb4c3
- issue-34b4f0ca1e13
status: resolved
tags:
- cli
- cosmetic
title: Write commands report the resolved `store`; the read paths do not
type: issue
updated: '2026-08-05'
---

**Class:** unstated · **Severity:** cosmetic
**Flow:** arch-f220a644d654 · **Step:** reading which store answered a query
**Question:** None · **Frequency:** every read

## Finding

Write commands report the resolved `store`; the read paths (`query`/`search`/`context`) do not.

## What happens today

OBSERVED. `add`/`update`/`get` carry `store` (they share `_emit_document`); `query` returns rows with no store field (`_emit_document_list`). An agent reading results cannot tell which store answered without issuing a separate command.

## Impact

Introduced by the issue-34b4f0ca1e13 fix, which reasoned about writes only. Reads are the safer half — nothing lands in the wrong place — but "which store am I reading?" is the same question, and the answer is now available on some commands and not others.

## Proposed default

Emit `store` on the list paths too, or state that it is a write-path field. Note the token cost: `store` is one absolute path per *response* on writes, but the list emitter would need it once per response rather than per row.

## Resolution

FIXED 2026-07-29 — but not by adding the field, which was the wrong shape for the cost. `store` is one absolute path, identical for every row, and a list response has nowhere to put it once; per row it would dwarf the 4.7% that one small field added to a `context` payload. The question a reader actually has is "am I reading the corpus I think I am?", and the global-fallback warning already answers it for nothing on stdout — it just was not wired to the read paths. It is now (`query`/`search`/`context`/`get`), and its wording changed from "writing to" to "using", since it is no longer write-only. Recorded because the finding asked for the field and the fix is deliberately not that: on a token-budgeted read path, a stderr signal beats a payload field that repeats.

## Actors affected

- AI coding agent

## Evidence

- `src/docir/entry_points/cli/app.py`
- `ref-1509d5dbb4c3 (discovery probe log)`

---

Migrated from the discovery gap register (GAP-050); the register itself now lives in this store.
