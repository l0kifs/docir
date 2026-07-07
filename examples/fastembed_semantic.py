"""fastembed_semantic.py — the real ONNX embedder vs. the deterministic default.

Demonstrates docir's pluggable ``Embedder`` port: one interface, two backends.
The deterministic default ranks by shared vocabulary; ``fastembed`` ranks by
*meaning*, so it links lexically-different but semantically-close documents —
the architecture's example, a query about "refresh token handling" matching a
document about "session renewal strategy".

Requires the optional extra and a one-time model download:

    uv sync --extra embeddings
    uv run python examples/fastembed_semantic.py

Setting ``DOCIR_EMBEDDER=fastembed`` makes the whole CLI use this backend too.
"""

from __future__ import annotations

import importlib.util

from docir.domain.ports.embedder import Embedder
from docir.infrastructure.embedding.deterministic_embedder import DeterministicEmbedder

QUERY = "how do we handle refresh token rotation on renewal"

# One candidate overlaps the query lexically; one is semantically close but
# shares almost no words; one is unrelated.
CANDIDATES = {
    "lexical-match": "Refresh token rotation and renewal handling for API tokens.",
    "semantic-match": "Session renewal strategy: reissue credentials when a login expires.",
    "unrelated": "Database schema migrations and table partitioning at scale.",
}


def rank(embedder: Embedder) -> list[tuple[str, float]]:
    """Rank the candidates by cosine similarity to the query, best first."""
    query_vector = embedder.embed(QUERY)
    scored = [
        (name, query_vector.cosine_similarity(embedder.embed(text)))
        for name, text in CANDIDATES.items()
    ]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored


def show(title: str, ranking: list[tuple[str, float]]) -> None:
    print(f"\n{title}")
    for name, score in ranking:
        print(f"  {score:+.3f}  {name}")


def main() -> None:
    if importlib.util.find_spec("fastembed") is None:
        print("fastembed is not installed — it is the optional 'embeddings' extra.\n")
        print("    uv sync --extra embeddings\n")
        print("then re-run:  uv run python examples/fastembed_semantic.py")
        return

    from docir.infrastructure.embedding.fastembed_embedder import FastEmbedEmbedder

    print(f"query: {QUERY!r}\ncandidates:")
    for name, text in CANDIDATES.items():
        print(f"  {name}: {text}")

    show("deterministic (hashing) — ranks by shared words", rank(DeterministicEmbedder()))

    print("\nloading the ONNX model (first run downloads the model)...")
    fastembed = FastEmbedEmbedder()
    show(f"fastembed ({fastembed.model_id}) — ranks by meaning", rank(fastembed))

    print("\nNotice how fastembed ranks 'semantic-match' high even though it shares")
    print("almost no words with the query — the deterministic embedder can't, because")
    print("it only sees vocabulary overlap. That semantic recall is exactly what")
    print("`docir context` gains when you enable the fastembed backend.")


if __name__ == "__main__":
    main()
