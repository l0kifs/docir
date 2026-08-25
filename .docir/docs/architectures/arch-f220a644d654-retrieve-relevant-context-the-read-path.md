---
code:
- src/docir/modules/documents/application/services/document_service.py
- src/docir/modules/indexing/**
created: '2026-07-30'
description: 'How a task turns into a ranked document set: hybrid fusion plus graph
  expansion.'
id: arch-f220a644d654
owner: maintainer
related:
- arch-1cfb1b212237
- issue-5bfbc6f2699d
- issue-8c37bf22ba3c
- issue-93152f7b9213
- issue-996b567e5131
- issue-e19a2fde1805
- issue-f6a5d0b86806
status: active
tags:
- retrieval
- embeddings
title: Retrieve relevant context (the read path)
type: architecture
updated: '2026-08-25'
---

## Backbone

express intent → rank (lexical + semantic) → filter visibility → expand one hop → return skeletons → fetch bodies by id

## Event timeline

| # | Event | Actor | Trigger | Evidence |
|---|-------|-------|---------|----------|
| 1 | ContextRequested | ACT-001 | `docir context "<task>"` | cli/app.py:299-311 |
| 2 | QueryEmbedded | system | always, before the transaction | document_service.py:252 |
| 3 | LexicalCandidatesFetched | system | FTS5 MATCH, capped at 25 | document_service.py:256 |
| 4 | SemanticRankingComputed | system | cosine over **all** active vectors | document_service.py:257 |
| 5 | RankingsFused | system | Reciprocal Rank Fusion, k=60 | scoring.py:44-73 |
| 6 | VisibilityFiltered | system | drops archived + inactive statuses | document_service.py:265-268 |
| 7 | GraphExpanded | system | one hop along outgoing edges | document_service.py:297-307 |
| 8 | SkeletonsReturned | system | no body — `DocumentSummary` | dto.py:84-135 |
| 9 | BodyFetched | ACT-001 | `docir get <id>` | document_service.py:210-214 |

`query` and `search` share steps 6 and 8 but skip 2–5 and 7.

## Hotspots

- **H1 — `--limit` does not bound the result.** Step 6 enforces the limit; step 7 then appends
  neighbours with no cap. CONFIRMED: `context --limit 3` over 3 decisions with out-degree 2
  returned **9** documents. For the product whose headline claim is "token-cheap for agents"
  (README:46) with a default `--limit 5`, the result size is unbounded by the caller.
  → `issue-996b567e5131`.

### H2 — visibility rules disagree between step 6 and step 7.

Step 7 checks `archived` but
not inactive status. CONFIRMED: a `resolved` issue is returned by `docir context` without
`--include-resolved`, while `search`/`query` correctly hide it. → `issue-8c37bf22ba3c`.

### H3 — no relevance floor.

Every active document receives a semantic rank, so the fused
list is never empty. CONFIRMED: `context "how do I bake sourdough bread"` against a store
containing only a Postgres decision returned that decision with `score 0.0328`. An agent
cannot distinguish "here is what matters" from "nothing matches". → `issue-93152f7b9213`.

### H4 — the score is not comparable across queries.

RRF output depends only on rank
position, so the top hit's score is ~identical for a perfect and a nonsense query. It is
emitted as a bare number named `score` (README:90) with no stated interpretation.
Same root cause as H3, separate consequence for anyone thresholding on it. → `issue-93152f7b9213`.

### H5 — search can silently under-return.

It fetches `limit * 2` candidates then filters
inactive ones. With more than half inactive in the head of the ranking, fewer than `limit`
results come back with no indication that filtering, not scarcity, caused it.
→ `issue-e19a2fde1805`.

### H6 — semantic ranking loads every active vector into memory on every call

(`active_vectors()`, repositories.py:309-320). Fine at thousands; no stated ceiling, no
pagination, no test at scale. Recorded as a limit-of-validity question, not a defect. → `issue-f6a5d0b86806`.

### H7 — graph expansion follows outgoing edges only.

A decision that supersedes an ADR is
reachable from it, but from the superseded ADR the newer one is not. Whether that is
intended is unstated — for `supersedes` specifically, the *incoming* direction is the one a
reader needs ("has this been replaced?"). → `issue-5bfbc6f2699d`.

### H8 — get ignores every visibility rule

and returns archived/inactive docs in full
(document_service.py:210-214, docstring says "regardless of status"). Deliberate and
documented; recorded so the asymmetry is not mistaken for a bug.

## Off-system steps

None — this flow is fully in-system.

## Rules

BR-018, BR-025, BR-026, BR-027, BR-028, BR-029, BR-030, BR-031, BR-032, BR-033, BR-034

## Gaps

issue-8c37bf22ba3c, issue-996b567e5131, issue-93152f7b9213, issue-e19a2fde1805, issue-5bfbc6f2699d, issue-f6a5d0b86806

## Several queries, and how they merge

Since 0.18.0 the caller may hand the ranking more than one query. `docir context "<task>"
--also "<phrasing>"` retrieves each string and merges them, and the merge is two operations
rather than one: **pooling decides each document's numbers** (RRF over every backend list, with
ranks, `similarity` and the matched section taken from its best pass) and **taking turns decides
the order**, so the caller's task holds every Nth slot whatever the others rank.

That split is measured. Pooling alone gives a correct extra phrasing everything it is worth —
recall@5 0.88 to 1.00 on docir's own corpus — and lets a confidently wrong one take the result
down to 0.25. Weighting the task fixes the second by destroying the first. Taking turns keeps
both: 1.00 and 0.75 (adr-4c21693aac55, adr-b23dae55666f).

docir writes none of those phrasings. The caller is already a model that has read the code, so a
rewriter shipped underneath it would guess at context the caller had and did not send
(adr-27c63ad02695). An agent passing a hypothetical *answer* is doing HyDE with the better model.

`--explain` returns the terms behind each rank, and `docir bench` scores the whole path against
a fixture of judged tasks — the two things that make a change to any of the above arguable from
numbers rather than from taste.
