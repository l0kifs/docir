---
created: '2026-07-30'
description: The eight actors that drive docir, their goals and their authority (there
  is no permission model).
id: ref-301bcc84b75c
owner: maintainer
related:
- arch-1cfb1b212237
- adr-90e994d931cc
- arch-0a3c2d6d54a6
- arch-3e305bc76ff0
- arch-90c90751344f
- arch-ccfcceeb35eb
- arch-f220a644d654
- issue-389dc5dac58a
- issue-476b4e188fab
- issue-9cb85759076d
- issue-b4f441c7210f
status: active
tags:
- docs
- agents
title: Actor catalog — who and what drives docir
type: reference
updated: '2026-08-17'
---

Reconstructed from the code and tests. `observed` means read off code or executed;
`inferred` means reasoned from the design.

## ACT-001 — AI coding agent

**Type:** system · **Frequency:** every coding session; the primary caller
**Flows:** arch-3e305bc76ff0, arch-f220a644d654, arch-ccfcceeb35eb

**Goal.** Before writing code, obtain the design decisions/issues/architecture notes relevant to the current task, cheaply enough to afford doing it every session.

**Authority.** Full write authority — may add, update, archive, delete any document and mutate the tag registry. No permission model exists (adr-90e994d931cc), so it can do anything a human can.

**Evidence:** README.md:8, src/docir/entry_points/cli/rendering.py:1-9, src/docir/modules/agents/infra/templates/skill.md, src/docir/modules/documents/application/dto.py:86-91

**Confidence:** observed

**Notes:** The token-trimming, the skeleton read contract and the JSON `--help` all exist only for this actor. It is the design centre of the product.

## ACT-002 — repository maintainer / developer

**Type:** human · **Frequency:** at decision points; bursty, low volume
**Flows:** arch-3e305bc76ff0, arch-f220a644d654, arch-0a3c2d6d54a6, arch-90c90751344f, arch-ccfcceeb35eb, FLOW-006

**Goal.** Capture a decision once, in the repo, and have it resurface when it becomes relevant — without maintaining a wiki.

**Authority.** Unrestricted. Also the only actor who can edit markdown files directly.

**Evidence:** README.md:50-68, src/docir/entry_points/cli/rendering.py:21

**Confidence:** observed

## ACT-003 — CI job

**Type:** scheduler · **Frequency:** per pull request
**Flows:** arch-0a3c2d6d54a6

**Goal.** Block a merge that would corrupt the document graph (duplicate ids, dangling refs).

**Authority.** Read-only; signals via exit code only.

**Evidence:** src/docir/entry_points/cli/app.py:419-440, CLAUDE.md

**Confidence:** observed

**Notes:** This actor is asserted by the docs but has NO fixture, example workflow, or template anywhere in the repo — `.github/workflows/` runs the project's own tests, not `docir check`. Its requirements are therefore inferred, and they are not met (issue-9cb85759076d).

## ACT-004 — embedding scheduler

**Type:** scheduler · **Frequency:** debounced 2s after any content write (daemon); inline otherwise
**Flows:** arch-3e305bc76ff0, arch-f220a644d654

**Goal.** Bring semantic vectors up to date after content changes, off the write path.

**Authority.** May recompute or drop any embedding row. Cannot alter documents.

**Evidence:** src/docir/modules/indexing/infra/scheduler.py:27-44, src/docir/modules/indexing/infra/scheduler.py:105-115

**Confidence:** observed

## ACT-005 — docir daemon

**Type:** system · **Frequency:** continuous while in use; exits after 900s idle
**Flows:** arch-3e305bc76ff0, arch-f220a644d654, arch-90c90751344f

**Goal.** Keep the embedding model warm and serialize writes into the store.

**Authority.** Executes every command on behalf of a client; self-terminates when idle.

**Evidence:** src/docir/platform/transport/server.py:20-49, src/docir/config/settings.py:29

**Confidence:** observed

**Notes:** Load-bearing far beyond its stated role: it is the *only* thing that makes concurrent id allocation safe (PROBE-10 vs PROBE-11). The docs attribute that safety to the SequenceRow counter instead. See issue-389dc5dac58a.

## ACT-006 — git / branch merge

**Type:** external_partner · **Frequency:** per merge
**Flows:** arch-0a3c2d6d54a6

**Goal.** Integrate two developers' documents into one history.

**Authority.** Can create any file state, including two files with the same id.

**Evidence:** src/docir/modules/documents/application/services/maintenance_service.py:84-124, tests/modules/documents/test_merge_safety.py

**Confidence:** observed

**Notes:** A genuine non-human actor: the duplicate-id file scan exists solely because git can produce a state no docir command would.

## ACT-007 — document owner / steward

**Type:** human · **Frequency:** per review cadence (365d for decision/architecture, 180d for qa/ops)
**Flows:** arch-0a3c2d6d54a6

**Goal.** Re-verify that a document is still true when its review cadence elapses.

**Authority.** None modelled — `owner` is a free-form string with no behaviour attached.

**Evidence:** src/docir/modules/documents/domain/entities/document.py:37, src/docir/modules/documents/domain/services/graph_checks.py:100-102

**Confidence:** observed

**Notes:** The staleness feature names this actor but never reaches them: `owner` is only ever interpolated into a `check` message. No notification, no queue, no "my documents" filter. The actor exists in the data model and nowhere in the flows. See issue-b4f441c7210f.

## ACT-008 — support / operator recovering a broken store

**Type:** human · **Frequency:** unknown — no data
**Flows:** arch-0a3c2d6d54a6

**Goal.** Diagnose and repair a store that has duplicate ids, dangling refs, or a lost doc.

**Authority.** Unmodelled.

**Confidence:** assumed

**Notes:** This actor was NOT served at the time of the 2026-07-26 pass: `docir check`
reported duplicate-id and dangling findings and no command could act on them. **It is served
now.** `docir check --fix` re-issues duplicate ids (the oldest file keeps the id, so existing
edges stay valid) and drops dangling edges, reporting every change; `docir check --strict` is
the pre-merge gate that catches both. `malformed` and `unknown-type` are still returned
unrepaired in `RepairResult.remaining` — deliberately, because each needs somebody to read
something and decide what the file or the schema should say. The written procedures are `run-22e0a6ce6ae1` (AI
code-check checklist) and `run-f4a756206fe0` (upgrading docir in a project).
See issue-476b4e188fab for the argument.

**Still unmodelled:** this actor has no authority concept and no usage data. docir has no
actors or permissions at all (adr-90e994d931cc), so "operator" remains a role a person plays,
not something the system knows about.
