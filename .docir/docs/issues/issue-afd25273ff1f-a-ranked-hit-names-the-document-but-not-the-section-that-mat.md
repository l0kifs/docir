---
code:
- src/docir/modules/indexing/domain/scoring.py
created: '2026-08-06'
description: Chunk vectors decide the ranking and the winning ordinal is discarded
  before the result is built, so an agent must fetch the whole body or discover headings
  in a second round trip.
id: issue-afd25273ff1f
owner: maintainer
related:
- ref-a6db21f52427
- adr-927aa43d9635
- arch-f220a644d654
status: open
tags:
- material
- retrieval
- embeddings
title: A ranked hit names the document but not the section that matched, so the paired
  section read is a guess
type: issue
updated: '2026-08-06'
---

**Class:** missing · **Severity:** material
**Source:** ref-a6db21f52427 (competitive survey, gap 2 residual)
**Flow:** arch-f220a644d654 · **Step:** reading back a ranked hit
**Frequency:** every ranked hit on a document with sections

## Finding

The section that matched is known at ranking time and discarded one line later.
`semantic_ranking` receives document *and* chunk vectors in one list and keeps each document's best
score, dropping which vector won (`scoring.py:63-69`); `DocumentSummary` has no field to carry it
(`dto.py:105-125`). The heading is already stored — `chunk_embeddings.heading`
(`models.py:100-107`) — so nothing needs to be recomputed or migrated.

## What happens today

`docir context "how does the daemon keep the model warm"` puts the architecture document at rank 1
because one of its sections matched. The agent is told the id and a similarity, and then has two
moves: `get <id>` for the whole body — the cost adr-927aa43d9635 exists to remove — or
`get --section` with a heading it does not have. An unknown heading errors *listing* the real ones,
so the second path is a deliberate extra round trip, not a failure.

## Impact

Chunked embedding closed the ranking half of gap 2 (coverage 44% → 100%, MRR 0.94 → 0.97) and left
the citation half open: qmd and sqlite-memory return the passage and its location in one step. docir
has the information and does not carry it, so the paired read it shipped is a guess.

## Proposed default

Carry the winning chunk's ordinal and heading through `FusedScore` into `DocumentSummary` as an
optional `section`. Absent when the document-level vector won, and when the hit arrived from FTS or
the graph — the same "absent means unknown, not zero" rule `similarity` already follows, so a
missing `section` must never be rendered as "no section matched".

Two constraints hold it in shape:

- The skeleton contract stays. Return the *heading*, a few tokens; never the chunk text. A hit that
  carries its passage is a list path with a body in it, which is the thing the contract forbids.
- `indexing` may not import `documents`, so the ordinal travels as data across the existing seam,
  the way `Document.embedding_chunks()` already hands `(ordinal, heading, text)` out.

## Actors affected

- ACT-001 AI coding agent

## Evidence

- `src/docir/modules/indexing/domain/scoring.py:47-69`
- `src/docir/modules/documents/application/services/document_service.py:434-436`
- `src/docir/modules/documents/application/dto.py:105-125`
- `src/docir/platform/persistence/models.py:92-107`

---

Opened from the 2026-08-06 re-verification of ref-a6db21f52427; the survey's Table A gained a
"passage citation in a result" row for exactly this.
