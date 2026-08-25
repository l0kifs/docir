---
code:
- src/docir/modules/documents/application/services/maintenance_service.py
- src/docir/modules/documents/domain/services/graph_checks.py
created: '2026-08-25'
description: 'Why an index holding nothing beside files on disk is an error rather
  than a warning: --strict was a merge gate that passed by reading nothing.'
id: adr-1cccd77cb023
owner: maintainer
related:
- issue-87410666c867
- adr-909734bced92
- adr-bd7c4f3c5764
status: accepted
tags:
- cli
- integrity
- testing
title: check refuses to report a verdict it could not reach
type: decision
updated: '2026-08-25'
---

## Context

`docir check --strict` is the merge gate this project recommends to every
adopter. Its graph half — `dangling`, `cycle`, `layering`, `orphan` — reads the
index. The index is derived and `.gitignore`d, so a fresh clone has none, and a
CI checkout is always a fresh clone.

So the gate ran over an empty graph and exited 0. The file-scanning half
(`duplicate-id`, `malformed`) kept firing, which is why nothing looked broken:
a half-alive gate is harder to notice than a dead one. Measured on this
repository, a corpus with one linked-to document removed produced **zero**
findings before a reindex and **sixteen** `dangling` errors after
(issue-87410666c867).

Fixing docir's own workflow fixes docir. Every adopter following the shipped
instructions still had a gate that passed by reading nothing.

## Decision

`check` reports **`empty-index`** — an `error` — when the index holds nothing
while `docs/` holds files.

## Why an error, against this codebase's own rule

`ERROR_KINDS` means "the corpus is broken", and by that reading this belongs
with the warnings: the documents are fine, only the derived state is missing.
The rule holds; the argument for promotion is a different one.

Every warning this project refuses to promote — `schema-drift`,
`stale-index-build`, `code-changed` — describes an index or a rule that has moved
*and still answers*. Promoting one red-builds a **correct** setup: a repo between
an upgrade and its next rebuild, a branch that edits code before its docs.

`empty-index` describes an index that answers nothing. The report beneath it is
not a weaker verdict, it is no verdict. And it red-builds a setup that was never
checking anything — the one case where a newly-failing build is true information.
The message names the single command that clears it.

A warning would have changed nothing, which is the test: an adopter whose CI runs
`check --strict` on a fresh clone would still get green over an empty graph.

## What keeps it narrow

- It compares against the **files**, so a freshly `docir init`-ed store — no
  documents, no index — is silent. Firing there would greet every new store with
  an error.
- A **partially** behind index is not this finding. One unparseable file counts on
  disk and not in the index for as long as it exists; an error there would
  red-build a repository for a condition `check` already reports as `malformed`.
  That case stays `docir doctor`'s `index-behind-files` warning.
- The comparison is `index_is_empty`, one function shared by `check` and
  `doctor`. Two copies would let one command call a store readable that the other
  refuses — the drift `validation.is_absent` exists to prevent, one size down.

## Consequences

An adopter upgrading docir may find CI newly red. That is the intended outcome
and the only honest one: the gate was not failing before because it was not
running. The fix is `docir reindex` ahead of `docir check --strict`, which is now
what the skill and README tell them to do, and what this repository's own
workflow does.
