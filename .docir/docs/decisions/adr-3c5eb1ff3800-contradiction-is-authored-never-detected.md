---
code:
- src/docir/modules/documents/domain/services/similarity_lint.py
code_baseline:
  src/docir/modules/documents/domain/services/similarity_lint.py: 497f909c8dc4
created: '2026-09-24'
description: 'Why lint --deep gets no contradiction-candidate finding: the embedder
  scores subject and not stance, and every threshold reaching this corpus''s three
  recorded contradictions admits sixteen thousand pairs.'
id: adr-3c5eb1ff3800
owner: maintainer
related:
- kind: refines
  to: arch-ad342aae8293
- adr-e86c5040d626
- adr-b2cfed9d5888
- adr-bbfac38a82b6
- issue-08437ba704ff
status: accepted
tags:
- integrity
- embeddings
title: Contradiction is authored, never detected
type: decision
updated: '2026-09-24'
---

## Context

An agent reading a corpus it did not write asks two questions: does something
here already say this, and does something here disagree with it. The first has
an answer — the `duplicate` finding in `docir lint --deep`, two unlinked
documents over 0.90 cosine. The second had none, and the symmetry is inviting:
a second finding over the same vectors, flagging unlinked pairs in the band
*below* `duplicate` as possible disagreements.

That check was designed, measured against this corpus, and refused.

## Decision

docir computes no contradiction candidates, at any tier. `contradicts` stays an
authored edge: a reader who finds a disagreement records it, and the kind's
symmetric and successor properties make docir surface it from both sides on
every later read. Detection is the reader's; amplification is docir's.

The corpus-wide view is delivered by pull, the way staleness is
([[adr-bd7c4f3c5764]]) — a query over the authored edges, not a finding that
arrives unasked.

## What the vectors can and cannot see

Measured on this corpus at 255 document vectors and 32,385 pairs, under
`bge-small-en-v1.5`:

- A claim and its own negation scores 0.771–0.983. "Tests live in a central
  tests/ tree, not inside each module", against its exact inverse, scores
  0.983. That is the band in which agreement also lives, so cosine reports
  subject and never stance.
- The three `contradicts` edges this corpus actually carries score 0.726, 0.730
  and 0.744 — ranks 6,922, 10,034 and 10,904 of 32,385.
- A threshold low enough to reach them admits 16,063 unlinked pairs. At 0.85
  the candidate set is 80 pairs and contains none of the three.

No threshold is both readable and correct, because the signal is not in the
vectors.

## Why the structural variants fail the same way

Dropping similarity for co-governance does not rescue it. Unlinked pairs
sharing at least one governed `code:` file: 801. Restricted to accepted
decisions: 127, whose largest are pairs of ADRs that correctly govern one
module together — a finding on correct usage, which is what [[adr-e86c5040d626]]
refused for the derived mention graph.

The zero-heuristic version fails too. "An authored `contradicts` whose two sides
are both live" fires on 3 of 3 here, and all three are deliberate recorded
deviations that are meant to stay live for as long as the deviation does.

## Consequences

Disagreement is caught where a reader is already reading. The packaged skill
tells an agent to run `docir context` over a description before `docir add`,
and to record what it finds as an edge rather than as a memory.

The register is a query, and needs nothing built:

```
docir query --expr "length(related[?kind=='contradicts']) > `0`"
docir query --expr "length(related_by[?kind=='contradicts']) > `0`"
```

This reopens on evidence, not on symmetry ([[adr-bbfac38a82b6]]): a model that
scores stance rather than subject — which docir does not ship and does not
intend to ([[adr-ab9c454b760c]]) — or a corpus whose maintainer reports
disagreements found only by reading, at a volume a query cannot cover.
