# indexing

## Purpose
Owns how relevant a document is to a query — the relevance and ranking engine.
It fuses lexical and semantic signals for context retrieval and manages when
document embeddings are (re)computed.

## Public operations
- `HybridScorer.semantic_ranking(query, vectors) -> [(id, score)]` — cosine ranking
- `HybridScorer.fuse(lexical, semantic) -> [FusedScore]` — reciprocal-rank fusion
- `FusedScore` — one fused ranking (`doc_id`, `score`, `lexical`, `semantic`). Exported as a
  type so consumers can hold a ranked list before resolving it to documents.
- `build_scheduler(uow_factory, embedder, *, background) -> EmbeddingScheduler`
  — construct the deferred embedding-recompute scheduler for one process
- `EmbeddingScheduler.schedule(id) / flush()` — queue and drain recomputes

## Events published
- none (no event bus; see ADR-0002)

## Events consumed
- none

## Owns
- data: per-document embedding vectors and the dirty-recompute queue.
  Physically stored in the shared index owned by `platform` (grandfathered;
  see ADR-0002).

## Depends on
- modules: none
- platform: persistence, embedding

## Policy
- permissions: none (single-user local CLI; see ADR-0003)
