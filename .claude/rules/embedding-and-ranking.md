---
paths:
  - "src/docir/platform/embedding/**"
  - "src/docir/modules/indexing/**"
  - "src/docir/modules/documents/domain/services/chunking.py"
  - "src/docir/modules/documents/domain/services/retrieval_scoring.py"
  - "benchmarks/**"
---

# Embedding, chunking and ranking

Every claim here was measured. Run `uv run python benchmarks/run.py` before and after touching ranking — and read which benchmark applies, because three of them exist and `run.py` is the wrong instrument for chunking and for a model change.

- **Embeddings are the one deferred, eventually-consistent piece.** A content change sets an
  `embeddings.dirty` flag (persisted, survives a daemon restart) and returns; everything else (file,
  metadata, FTS, relations) is synchronous and current when the command returns. Two scheduler
  implementations back this: `InlineEmbeddingScheduler` (in-process/tests, drains synchronously so
  behaviour is deterministic) and `ThreadedEmbeddingScheduler` (daemon, debounced background thread).
  Anything that needs the vector *now* must flush, by one of the three routes README lists; the
  reindex among them reports its count as `embeddings_recomputed`. There is no flag for
  "recompute the vectors too", and
  adr-6a4718fa7a7d records why the one that existed was retired rather than repaired: it skipped
  the rebuild instead of adding to it, so it recomputed exactly those vectors and wrote neither
  the schema baseline nor the build stamp. Do not move embedding onto the synchronous write path.

- **Every section is embedded, because the model never read the whole body (adr-927aa43d9635).**
  `bge-small-en-v1.5` reads ~512 tokens (~1,900 chars of prose) and silently ignores the rest —
  appending text past it returns a bit-identical vector. 84 of docir's own 103 documents exceed
  that, so 56% of the corpus was absent from the semantic index while FTS5 hid it by covering the
  whole body. `drain_dirty` now writes a document vector **and** one vector per `##` section
  (`chunk_embeddings`, keyed `(doc_id, ordinal)`, migration `0003`), and
  `HybridScorer.semantic_ranking` accepts repeated ids and keeps each document's **best** — RRF
  fuses rankings *of documents*, so the collapse happens before fusion, not after. The collapse
  keeps the winning **candidate**, not just its score: `VectorCandidate` -> `SemanticHit` ->
  `FusedScore.section` -> `DocumentSummary.matched_section` is what tells an agent which heading
  to pass to `get --section` (issue-afd25273ff1f). Absent means *not addressable as a section* —
  the document vector won, the hit was lexical or graph-reached, or the chunk is a preamble or an
  over-long section's continuation — never "nothing matched"; and the field is **not** called
  `section`, because `DocumentView.section` already means "the body was narrowed to this".
  Load-bearing
  details: `MAX_CHUNK_CHARS` (1200) is *derived* from the measured window, not chosen — a chunk that
  overflows it reintroduces the bug one level down, and each chunk carries the title prefix that eats
  into the budget; the splitter tracks fenced code blocks, because a `##` comment inside one is not a
  heading and cutting there yields two invalid chunks; there is **no second dirty flag**, chunks are
  rewritten wholesale under the existing `embeddings` queue in the same transaction; and `lint --deep`
  deliberately still compares *document* vectors only, since chunk vectors would answer "do these
  share a section" rather than "are these the same document". `indexing` may not import `documents`,
  so the entity is the seam: `Document.embedding_chunks()` hands the scheduler positional
  `(ordinal, heading, text)` triples. Coverage on docir's own store went 44% -> 100% (695 chunks);
  recall@5 held at 0.97 while MRR rose 0.94 -> 0.97. Keep the recall gate — max-pooling structurally
  favours documents with more sections.

- **`score` is rank-derived; `similarity` is the one number with absolute meaning.** RRF
  fuses *ranks*, so `score` says where a document placed and never how good the match was — a
  nonsense query against a one-document store scored the same ~0.0328 a perfect match does,
  which made "nothing relevant exists" inexpressible. `FusedScore.similarity` carries the raw
  cosine through (`fuse` used to compute it, sort by it, and drop it), and `--min-score`
  filters on that. Do not point `--min-score` at `score`. Two exemptions are load-bearing:
  graph neighbours are never filtered (they are there because a selected document links them,
  not because they scored), and a hit with **no** `similarity` is kept — absent means *no
  current vector*, not zero, and dropping it would filter on embedding-queue staleness rather
  than relevance. That is also why `_trim` **rounds** `similarity` instead of dropping a 0.0:
  an absent value must keep meaning "not scored".

- **`fastembed` is the default embedder and a hard dependency; the hashing one is the
  fallback (adr-ab9c454b760c).** It was optional, which meant the shipped default scored *shared vocabulary*
  rather than meaning — `DeterministicEmbedder` is signed feature hashing, the same signal
  FTS5 already provides, and two paraphrases with no words in common score 0.0. Measured
  (`benchmarks/`, 2026-07-27 re-based corpus — compare only against figures from that run):
  isolate the embedding signal with `--expand 0` and the hashing embedder scores recall@5
  **0.80, below the 0.83 plain `search` manages on its own**, while the model scores 0.87.
  Full `context` is 0.96/MRR 0.95 with the model against 0.93/MRR 0.80 without.
  Quote the `--expand 0` pair when arguing about embedders: full `context` numbers include
  graph expansion, which lifts both and hides the difference. `DOCIR_EMBEDDER=deterministic`
  selects the fallback — **the test fixtures set this**, so the suite stays hermetic and most
  of it never touches a model. `platform/embedding/fastembed.py` is **no longer excluded from
  `ty` or omitted from coverage**: it is what every default install runs, so a break there
  reaches every user, and lifting the `ty` exclusion immediately surfaced a real diagnostic
  (the adapter held its model as bare `object`; it now depends on a `_TextEmbedding` Protocol).
  Tests that load the real model are marked `slow` (~4 s cold, ~2 ms warm); CI caches
  `~/.cache/fastembed`. Run `uv run python benchmarks/run.py` before and after touching ranking.
  **For a change to the *chunking* rules `run.py` is the wrong instrument**: its corpus has no
  section over the ceiling and none quoting a fenced heading, so a broken splitter scores what a
  working one does (issue-b1a6e57deeec). `benchmarks/chunking.py` is the one that moves. Its
  corpus **declares** each body's real headings by hand — a scanner checked against itself agrees
  with itself, which is why the first version of that guard saw nothing — and it reports structure
  (headings addressable, phantom headings) as the gate with retrieval as context, because which
  section wins a query is the embedder's judgement and tuning prose until it matches would measure
  the tuning.

- **A store may name its embedding model, and `run.py` is the wrong instrument for that
  too (issue-a24f404dd106).** A top-level `embed_model:` key in `docs-schema.yaml` — beside
  `id_style`, which is the precedent for a store-wide policy that is not a type concept —
  selects any model `fastembed` supports. It lives in the committed file rather than an env
  var, for the reason README gives about two clones disagreeing. **The catalogue
  (`platform/embedding/catalogue.py`) is a recommendation, not a gate**: a name docir has
  measured passes silently *and without importing fastembed at all* — that import is most
  of a cold start and the schema loads on every command, so the short-circuit is load-bearing
  and `test_embed_model.py` asserts the model list was never consulted, not merely that
  nothing warned. Any other supported name is accepted with one warning, because a hardcoded
  tuple is worse placed to choose than somebody writing in a language docir never
  benchmarked; only a name fastembed does not know is refused. `verify_embed_model` is
  called by **both** `_build_embedder` and `validate_schema` — `schema validate` is the
  command run right after editing the key, and two checkers would disagree — and it lives in
  the composition root rather than in `Schema`, since answering costs that import and the
  domain must stay pure. The key is **absent from `schema_shape.describe`**, so a deliberate
  switch is not reported as `schema-drift`: drift exists to report what `git diff` cannot
  show you. `docir self status` reports the model in force, because nothing else did.
  **For a change of model `run.py` measures the wrong corpus** — it is in English, where the
  multilingual models lose ranking and buy nothing, which is why the default did not move.
  `benchmarks/multilingual.py` is the one that moves: `corpus.yaml` translated with
  identical keys, edges and judgments, so language is the only variable. Russian paraphrased
  recall goes **0.50 -> 0.80** and MRR 0.63 -> 0.90; the default's *same-words* 1.00 beside
  its paraphrased 0.50 is FTS5 carrying the lexical half unaided, which is what "no better
  than full-text search" means as a number.

- **Vectors record which model produced them, and mismatches are recomputed, not compared
  (adr-ab9c454b760c).**
  `set_vector` writes `embeddings.model_id`; `active_vectors(model_id)` returns only matching
  rows and `dirty_ids(model_id)` treats a foreign or NULL `model_id` as dirty. Without this,
  changing embedder made `docir context` raise `dimension mismatch: 256 != 384` in every
  existing store — different models have different widths, and `Embedding.cosine_similarity`
  refuses rather than silently truncating. The recompute is deferred exactly as README
  describes, so the first read after a switch has no semantic signal.

- **docir generates nothing, and that is a decision rather than an omission
  (adr-27c63ad02695).** No generative model, not as a dependency and not as an extra. The
  reason is not install weight: docir's caller *is* a frontier model that has read the code,
  so a 0.5-1.5B quantized rewriter underneath it would be guessing at context the caller had
  and did not send. Two mechanisms that would have needed one are already closed by
  measurement — cross-encoder reranking (adr-d657a09b8c4a) and pseudo-relevance feedback
  (adr-46b69a581c65, which cost 0.13 recall@5 on this corpus because the first pass is already
  right 88% of the time). What replaces HyDE is **accepting** it: several caller-supplied
  query strings fused in one `context` call, which needs no model and uses a better one. That
  is unbuilt and ships like any ranking change — measured with `docir bench` first.
