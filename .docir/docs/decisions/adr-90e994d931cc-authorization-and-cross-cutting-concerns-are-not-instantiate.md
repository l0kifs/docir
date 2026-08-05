---
created: '2026-07-22'
description: Why no authorization or cross-cutting machinery exists in a single-user
  local CLI.
id: adr-90e994d931cc
owner: maintainer
related:
- kind: contradicts
  to: arch-322e5f992ad2
status: accepted
tags:
- architecture
title: Authorization and cross-cutting concerns are not instantiated
type: decision
updated: '2026-08-05'
---

## Context
ARCHITECTURE_RULES §6 requires every cross-cutting concern (auth, tenancy,
audit, feature flags, ...) to have one declaration point, one enforcement point,
and one CI gate, and §6.1 spells this out for authorization. `docir` is a
single-user local CLI: there are no actors, permissions, tenants, roles, or
multi-user access. There is nothing to declare or enforce.

## Decision
Do not build `platform/authz`, a permission registry, or per-operation policy
declarations. Record that §6 and §6.1 are intentionally not instantiated because
the system has no cross-cutting concern of that kind. The other enforcement
checks that DO apply are kept: boundary/interface/layer/cycle (tach),
contract-sync, dead-code (vulture), lint, types, and tests.

## Consequences
- Easier: no machinery that enforces nothing; the `api` surface stays focused on
  document/tag/index operations.
- Harder: nothing today.
- If `docir` ever grows real actors (e.g. a shared server), a cross-cutting
  authorization concern must be introduced per §6, superseding this ADR.
