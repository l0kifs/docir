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
status: resolved
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

## Resolution

FIXED 2026-08-06, as proposed, with one deliberate departure: the field is `matched_section`, not
`section`. `DocumentView.section` already means "the body was narrowed to this one" — a different
claim on a sibling DTO — and one word meaning two things is how `stale` came to name three
concepts (issue-d8295c5c76d1).

The collapse in `HybridScorer.semantic_ranking` now keeps the winning *candidate* rather than
just its score: `VectorCandidate(doc_id, vector, section)` in, `SemanticHit(doc_id, similarity,
section)` out, through `FusedScore.section` onto `DocumentSummary.matched_section`. The heading
was already stored (`chunk_embeddings.heading`), so nothing was recomputed or migrated; the
chunk repository's `active_vectors` widened to `(doc_id, heading, vector)` and the seam stayed
where it was — `indexing` still imports nothing from `documents`.

Absent keeps meaning *not addressable as a section*: the document's own vector won, the hit was
lexical or graph-reached, or the winning chunk has no heading (a preamble, or the continuation of
an over-long section, which `--section` could not accept anyway). Never "nothing matched" — the
rule `similarity` already follows.

`_visible_ranked` now carries the whole `FusedScore` alongside its document instead of a tuple of
the two numbers the summary happened to need. Threading each new field through as another tuple
slot is precisely how this one was dropped for as long as chunking existed.

Verified the way the issue frames the problem — not that a string is present, but that it
dereferences: the round-trip test feeds `matched_section` straight back into
`get --section` and asserts the body that comes out. Two more pin the absent cases (a preamble
match, a graph-reached neighbour), and each was confirmed by injecting the bug it claims to
catch. On docir's own corpus, "how does the daemon keep the embedding model warm" now returns
`arch-1cfb1b212237` with `matched_section: Daemon process`.

Cost: ~20 tokens per `context` result set on the benchmark corpus (484 vs 464), against a body
fetch saved whenever a hit is a long document. Ranking is untouched — recall@5 0.97, MRR 0.97.

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
