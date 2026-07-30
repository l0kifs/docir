---
created: '2026-07-30'
description: The eight actors that drive docir, their goals and their authority (there
  is no permission model).
id: ref-301bcc84b75c
owner: maintainer
related:
- arch-1cfb1b212237
status: active
tags:
- docs
- agents
title: Actor catalog — who and what drives docir
type: reference
updated: '2026-07-30'
---

# Actor catalog — who and what drives docir

Reconstructed from the code and tests. `observed` means read off code or executed;
`inferred` means reasoned from the design.

## ACT-001 — AI coding agent

**Type:** system · **Frequency:** every coding session; the primary caller
**Flows:** FLOW-001, FLOW-002, FLOW-005

**Goal.** Before writing code, obtain the design decisions/issues/architecture notes relevant to the current task, cheaply enough to afford doing it every session.

**Authority.** Full write authority — may add, update, archive, delete any document and mutate the tag registry. No permission model exists (ADR-0003), so it can do anything a human can.

**Evidence:** README.md:8, src/docir/entry_points/cli/rendering.py:1-9, src/docir/modules/agents/infra/templates/skill.md, src/docir/modules/documents/application/dto.py:86-91

**Confidence:** observed

**Notes:** The token-trimming, the skeleton read contract and the JSON `--help` all exist only for this actor. It is the design centre of the product.

## ACT-002 — repository maintainer / developer

**Type:** human · **Frequency:** at decision points; bursty, low volume
**Flows:** FLOW-001, FLOW-002, FLOW-003, FLOW-004, FLOW-005, FLOW-006

**Goal.** Capture a decision once, in the repo, and have it resurface when it becomes relevant — without maintaining a wiki.

**Authority.** Unrestricted. Also the only actor who can edit markdown files directly.

**Evidence:** README.md:50-68, src/docir/entry_points/cli/rendering.py:21

**Confidence:** observed

## ACT-003 — CI job

**Type:** scheduler · **Frequency:** per pull request
**Flows:** FLOW-003

**Goal.** Block a merge that would corrupt the document graph (duplicate ids, dangling refs).

**Authority.** Read-only; signals via exit code only.

**Evidence:** src/docir/entry_points/cli/app.py:419-440, CLAUDE.md

**Confidence:** observed

**Notes:** This actor is asserted by the docs but has NO fixture, example workflow, or template anywhere in the repo — `.github/workflows/` runs the project's own tests, not `docir check`. Its requirements are therefore inferred, and they are not met (GAP-006).

## ACT-004 — embedding scheduler

**Type:** scheduler · **Frequency:** debounced 2s after any content write (daemon); inline otherwise
**Flows:** FLOW-001, FLOW-002

**Goal.** Bring semantic vectors up to date after content changes, off the write path.

**Authority.** May recompute or drop any embedding row. Cannot alter documents.

**Evidence:** src/docir/modules/indexing/infra/scheduler.py:27-44, src/docir/modules/indexing/infra/scheduler.py:105-115

**Confidence:** observed

## ACT-005 — docir daemon

**Type:** system · **Frequency:** continuous while in use; exits after 900s idle
**Flows:** FLOW-001, FLOW-002, FLOW-004

**Goal.** Keep the embedding model warm and serialize writes into the store.

**Authority.** Executes every command on behalf of a client; self-terminates when idle.

**Evidence:** src/docir/platform/transport/server.py:20-49, src/docir/config/settings.py:29

**Confidence:** observed

**Notes:** Load-bearing far beyond its stated role: it is the *only* thing that makes concurrent id allocation safe (PROBE-10 vs PROBE-11). The docs attribute that safety to the SequenceRow counter instead. See GAP-009.

## ACT-006 — git / branch merge

**Type:** external_partner · **Frequency:** per merge
**Flows:** FLOW-003

**Goal.** Integrate two developers' documents into one history.

**Authority.** Can create any file state, including two files with the same id.

**Evidence:** src/docir/modules/documents/application/services/maintenance_service.py:84-124, tests/modules/documents/test_merge_safety.py

**Confidence:** observed

**Notes:** A genuine non-human actor: the duplicate-id file scan exists solely because git can produce a state no docir command would.

## ACT-007 — document owner / steward

**Type:** human · **Frequency:** per review cadence (365d for decision/architecture, 180d for qa/ops)
**Flows:** FLOW-003

**Goal.** Re-verify that a document is still true when its review cadence elapses.

**Authority.** None modelled — `owner` is a free-form string with no behaviour attached.

**Evidence:** src/docir/modules/documents/domain/entities/document.py:37, src/docir/modules/documents/domain/services/graph_checks.py:100-102

**Confidence:** observed

**Notes:** The staleness feature names this actor but never reaches them: `owner` is only ever interpolated into a `check` message. No notification, no queue, no "my documents" filter. The actor exists in the data model and nowhere in the flows. See GAP-011.

## ACT-008 — support / operator recovering a broken store

**Type:** human · **Frequency:** unknown — no data
**Flows:** FLOW-003

**Goal.** Diagnose and repair a store that has duplicate ids, dangling refs, or a lost doc.

**Authority.** Unmodelled.

**Confidence:** assumed

**Notes:** NO actor of this kind is served. `docir check` reports duplicate-id and dangling findings but there is no `docir repair`, no `--fix`, no runbook, and no documented manual procedure. Every failure mode this analysis confirmed leaves the user here with no tool. See GAP-012.
