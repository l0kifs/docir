---
created: '2026-07-30'
description: The most likely adopter is exactly a project already keeping markdown
  ADRs.
id: issue-6a0ad9a70f84
owner: maintainer
related:
- issue-20933967697b
status: resolved
tags:
- integrity
- material
title: How is a repository that already has ADRs supposed to adopt docir
type: issue
updated: '2026-08-05'
---

**Gap:** issue-20933967697b
**Blocking:** no · **Rank:** 12 · **Answered:** 2026-07-27
**Authority:** repo maintainer (built, reviewed against a messy corpus, then rejected)

## Question

How is a repository that already has ADRs supposed to adopt docir? There is no import path, and because ids are always system-allocated, existing ADR numbers cannot be kept.

## What the system does today

No import/export/migrate command exists. Every historical cross-reference breaks.

## Proposed answer

`docir import <glob>` that preserves an id when the filename already matches `<prefix>-<suffix>`, and seeds the counter above it.

## Why it matters

The most likely adopter is exactly a project already keeping markdown ADRs.

## Answer

ANSWERED 2026-07-27, in the negative. `docir import` was built and then removed the same day: with random ids the command's only unique capability disappears, and what remained reported success over input it had mangled. The answer to "how does a repo with existing ADRs adopt docir?" is a documented review-then-add workflow, not a command. See issue-20933967697b, which stays open.

---

Migrated from the discovery question queue (Q-012); the queue itself now lives in this store.
