# Embedding adapters — the semantic layer.
#
#   * deterministic_embedder — dependency-free hashing embedder; the default,
#                              offline, reproducible, used everywhere in tests.
#   * fastembed_embedder     — real ONNX (quantized, CPU-only) embedder; opt-in
#                              via the `embeddings` extra.
#   * scheduler              — InlineEmbeddingScheduler (synchronous, used
#                              in-process) and ThreadedEmbeddingScheduler
#                              (debounced background drain, used by the daemon).
