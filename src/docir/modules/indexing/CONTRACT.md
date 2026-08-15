# indexing

## Purpose
Owns how relevant a document is to a query — the relevance and ranking engine.
It fuses lexical and semantic signals for context retrieval and manages when
embeddings are (re)computed — a vector per document *and* one per `##` section,
since the model reads only the first ~512 tokens of a body (adr-927aa43d9635).

## Public operations
- `HybridScorer.semantic_ranking(query, candidates) -> [SemanticHit]` — cosine ranking,
  collapsing a document's candidates to its best one
- `HybridScorer.fuse(lexical, semantic) -> [FusedScore]` — reciprocal-rank fusion
- `VectorCandidate(doc_id, vector, section=None)` — one vector to rank. `section` is the
  heading it came from; `None` means the vector describes the whole document, or the chunk
  has no addressable heading (a preamble, or a continuation of an over-long section).
- `SemanticHit(doc_id, similarity, section=None)` — a document's best cosine and *where* in
  it that was found. The winning candidate is kept, not just its score: the section that
  earned a document its rank is what `get --section` should be asked for next
  (issue-afd25273ff1f).
- `FusedScore` — one fused ranking (`doc_id`, `score`, `lexical`, `semantic`, `similarity`,
  `section`). Exported as a type so consumers can hold a ranked list before resolving it to
  documents.
- `build_scheduler(uow_factory, embedder, *, background) -> EmbeddingScheduler`
  — construct the deferred embedding-recompute scheduler for one process
- `EmbeddingScheduler.schedule(id) / flush()` — queue and drain recomputes

## Events published
- none (no event bus; see adr-d3e3616400bf)

## Events consumed
- none

## Owns
- data: per-document embedding vectors, the per-section chunk vectors written
  beside them in the same transaction (there is deliberately no second dirty
  flag — chunks are rewritten wholesale under the existing queue), and the
  dirty-recompute queue. Physically stored in the shared index owned by
  `platform` (grandfathered; see adr-d3e3616400bf).

## Depends on
- modules: none
- platform: persistence, embedding

## Policy
- permissions: none (single-user local CLI; see adr-90e994d931cc)
