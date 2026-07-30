---
created: '2026-07-30'
description: '`docir init` is step 2 of the quickstart; forgetting it produces no
  error.'
id: issue-b86a75d656ea
owner: maintainer
related:
- issue-34b4f0ca1e13
status: resolved
tags:
- cli
- material
title: Q-016 — Should `docir add` in an uninitialised repository succeed silently
  against the global…
type: issue
updated: '2026-07-30'
---

# Q-016 — Should `docir add` in an uninitialised repository succeed silently against the global…

**Gap:** GAP-023 · **Also resolves:** — · **Audience:** repo maintainer
**Blocking:** no · **Rank:** 16 · **Asked:** 2026-07-29 · **Answered:** 2026-07-29
**Authority:** repo maintainer (asked for a recommendation, then adopted it)

## Question

Should `docir add` in an uninitialised repository succeed silently against the global `~/.docir`? Today it does, and the document lands outside the repo with no signal.

## What the system does today

settings.py:96-104 falls back silently; schema_loader.py:26-31 writes a default schema on first touch. The reported path looks repo-relative.

## Proposed answer

Report the resolved store in write output, or warn once on the global fallback.

## Why it matters

`docir init` is step 2 of the quickstart; forgetting it produces no error.

## Answer

The assumption was right on both counts: the fallback stays, the missing signal was the defect. Both halves of the proposed answer are implemented — every write reports the resolved `store`, and a stderr warning fires only when the fallback happens inside a git repository. Erroring was rejected (it would break the personal-notes case, and unlike git docir has a legitimate global store); warning on every fallback was rejected as firing on correct usage. `DOCIR_HOME` is the no-new-flag opt-out. See GAP-023 resolution.

---

Migrated from the discovery question queue (Q-016); the queue itself now lives in this store.
