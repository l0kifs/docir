---
created: '2026-07-30'
description: README:42 claims "Retrieval by meaning ✅ (lexical + semantic)" against
  RAG's ✅ and plain files' ❌.
id: issue-f01a7a585fc1
owner: maintainer
related:
- adr-ab9c454b760c
- arch-f220a644d654
status: resolved
tags:
- embeddings
- material
title: GAP-043 — The default embedder does not capture meaning. `DeterministicEmbedder`
  is signed…
type: issue
updated: '2026-07-30'
---

# GAP-043 — The default embedder does not capture meaning. `DeterministicEmbedder` is signed…

**Class:** misleading · **Severity:** material · **Confidence:** observed
**Flow:** FLOW-002 · **Step:** semantic ranking in a default install
**Question:** None · **Frequency:** every default install

## Finding

The default embedder does not capture meaning. `DeterministicEmbedder` is signed feature hashing over tokens, so it scores similarity by shared vocabulary — the same signal FTS5 already provides. In a default install both halves of the "hybrid" ranking are lexical.

## What happens today

MEASURED 2026-07-26 by benchmarks/run.py. With the default embedder `context` beats plain `search` by +0.03 recall and -0.03 MRR — noise at 12 tasks. With `fastembed` it beats it by +0.11 recall and +0.13 MRR. On tasks phrased without the corpus vocabulary, recall is 0.83 (default) vs 0.92 (fastembed) vs 0.75 (search). Direct probe: the sentences "duplicate charges when the customer double-clicks pay" and "idempotency keys for payment capture" score cosine 0.000 under the default embedder.

## Impact

README:42 claims "Retrieval by meaning ✅ (lexical + semantic)" against RAG's ✅ and plain files' ❌. That is earned only with `DOCIR_EMBEDDER=fastembed` plus the `embeddings` extra, which is off by default — so the comparison table describes a configuration most users will not be running. The docstring in deterministic.py is honest ("captures real lexical overlap"); the README is not.

## Proposed default

Say so in the README's table and in `docir --help`: mark semantic retrieval as requiring the extra, or make `docir init` offer to enable it. The code is fine; the claim is not.

## Resolution

FIXED 2026-07-26 as a documentation-honesty change; no code changed, because the code was never wrong — the claim was. The README comparison table now reads "lexical by default, semantic with an extra" with a footnote giving the install command and the measured difference (0.96 vs 0.88 recall@5; 0.92 vs 0.83 on paraphrased tasks; search 0.75), linked to benchmarks/ so a reader can reproduce it. "Hybrid lexical + semantic" in the command table and the agent guide became "full-text and vector rankings fused", which is true in both configurations. The packaged agent guide now tells an agent to phrase `context` queries in the project's own vocabulary unless fastembed is enabled, and to retry with the codebase's terms when a query under-retrieves — turning the limitation into usable advice. CLAUDE.md records the invariant for maintainers, with the instruction to re-run the benchmark before and after touching ranking. SUPERSEDED same day: the maintainer decided the model should be the default, so the caveat is gone rather than documented. `fastembed` is now a hard dependency; `DOCIR_EMBEDDER=deterministic` selects the model-free fallback (the test suite does this, which is what keeps it hermetic). The README states the real cost measured on this machine: ~64 MB model downloaded once, ~240 MB of dependencies, CPU-only, local. The "works offline" row is now honest about the one-time download. Prerequisite discovered while implementing, see GAP-044: the switch would have broken every existing store.

## Actors affected

- AI coding agent
- repository maintainer

## Evidence

- `src/docir/platform/embedding/deterministic.py:1-8`
- `benchmarks/README.md`
- `README.md:42`

---

Migrated from the discovery gap register (GAP-043); the register itself now lives in this store.
