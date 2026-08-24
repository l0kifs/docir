"""The embedding models docir has verified, and the one it uses by default.

This is a **recommendation, not a gate**. A store may name any model
``fastembed`` supports; the names here are the ones docir has measured and can
vouch for, and anything else is accepted with a warning rather than refused.
The corpus is the user's, the blast radius of a poor choice is bounded — vectors
record which model made them, so changing the key back recomputes rather than
compares — and somebody writing in a language docir has never benchmarked is
better placed to pick a model than this tuple is.

What the warning exists to say: :meth:`Embedder.embed
<docir.platform.embedding.port.Embedder.embed>` is symmetric — the query goes
through the same call the documents did. That is correct for the models listed
here, and measured for the default, whose ``query_embed`` returns a
bit-identical vector. It is *not* correct for a model trained on asymmetric
prefixes (E5's ``query: `` / ``passage: ``, which neither docir nor fastembed
applies) or one that selects a task adapter through ``query_embed``
(``jina-embeddings-v3``). Those work, and score below their published numbers.

Adding an entry is a measurement, not an edit: run ``benchmarks/run.py`` against
it first. The multilingual entries cost ranking rather than recall on the
English corpus (recall@5 0.97 -> 0.95, MRR 0.97 -> 0.91, with the paraphrased
split unchanged at 0.95), which is why the default does not move.
"""

from __future__ import annotations

#: The model every store uses unless its schema names another. English-only,
#: 384 dimensions, ~67 MB.
DEFAULT_EMBED_MODEL = "BAAI/bge-small-en-v1.5"

#: Models docir has measured. Naming one of these skips the warning *and* the
#: ``fastembed`` import that checking any other name requires — which is why the
#: common path stays free of both.
VERIFIED_EMBED_MODELS: tuple[str, ...] = (
    # English, 384 dim, ~67 MB — the default.
    DEFAULT_EMBED_MODEL,
    # Multilingual, 384 dim, ~220 MB — the drop-in: same width as the default.
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    # Multilingual, 768 dim, ~1.0 GB — the same family, larger.
    "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
)
