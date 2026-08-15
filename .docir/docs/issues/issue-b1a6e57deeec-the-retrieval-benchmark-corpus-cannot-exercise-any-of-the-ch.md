---
code:
- benchmarks/corpus.yaml
- benchmarks/tasks.yaml
- benchmarks/run.py
- benchmarks/chunking.py
- benchmarks/chunking_corpus.yaml
- benchmarks/chunking_tasks.yaml
created: '2026-08-15'
description: 26 documents, 30 sections, none over the chunk ceiling and none quoting
  a fenced heading — so the splitter never runs and a chunking regression scores identically.
id: issue-b1a6e57deeec
related:
- adr-927aa43d9635
status: resolved
tags:
- retrieval
- testing
- material
title: The retrieval benchmark corpus cannot exercise any of the chunking rules
type: issue
updated: '2026-08-15'
---

## What is missing
`benchmarks/corpus.yaml` is 26 documents and 30 sections. Measured against the
current rules: **0 sections over `MAX_CHUNK_CHARS`, 0 documents quoting a fenced
`##`, 0 short-then-long pairs, and 0 headless continuation chunks** across all
52 chunks it produces.

So `_split_long` never fires, `_merge_short` never declines, and the fence rule
never decides anything. Every section is exactly one chunk.

## Why it matters
The benchmark exists to be the evidence behind retrieval constants — that is the
argument in its own module docstring. But the rules adr-927aa43d9635 introduced
are the ones it cannot see. Two chunking defects were fixed on 2026-08-15
(issue-af046a467575, issue-66d43f63e441), and re-running the benchmark before
and after produced identical numbers, correctly and uselessly: a corpus with
nothing to split cannot distinguish a working splitter from a broken one.

The same holds in the other direction. A future change that reintroduces either
defect scores recall@5 0.97 and passes review.

Coverage reported by the run says the same thing more quietly: adding section
vectors moves embedded coverage 87% -> 94% here, against 44% -> 100% on docir's
own store. This corpus is short by construction.

## What it needs
Documents shaped like the failures: a section past the ceiling whose *tail*
holds the answer to a task, one quoting a markdown template inside a fence with
a real heading after it, and a short section immediately before a long one. Then
tasks whose answer lives in the part that only exists if chunking works.

The cost is real and has to be decided, not assumed: the corpus was re-based on
2026-07-27 and every figure quoted in `CLAUDE.md` compares against that run.
Adding documents re-bases it again and those comparisons stop being valid. The
alternative is a second, separate corpus that exercises the splitter and is
never mixed into the headline numbers.

## Resolution

Closed by a second harness rather than by extending `corpus.yaml`, so every
figure quoted against the 2026-07-27 re-base stays valid.

`benchmarks/chunking.py` runs `chunking_corpus.yaml` — three documents built out
of the shapes that fail: an answer past the document vector's window, a section
following a quoted markdown template, and a short section immediately before a
long one. `build_store` in `run.py` gained a corpus-file parameter so both
harnesses build a store the same way.

The corpus **declares** the headings each body really has. Deriving them would
have made the check circular: a fence-blind scanner reports the headings quoted
inside the fence and then agrees with its own list, which is exactly what the
first version of this did and why it could not see the defect.

Reported in two blocks. Structure — headings addressable, unaddressable chunks,
phantom headings — is deterministic and is the gate. Retrieval is reported and
not asserted: which section wins is the embedder's judgement, and tuning the
prose until it matches an expected heading would measure the tuning rather than
the splitter.

Verified by injecting both defects. The fence-blind scanner invents a
`Credentials` heading out of the quoted template (phantom 0 -> 1); the
unconditional merge leaves `Failover sequence` naming no chunk (addressable
15/15 -> 14/15, unaddressable 0 -> 1). Neither moved `run.py` at all.
