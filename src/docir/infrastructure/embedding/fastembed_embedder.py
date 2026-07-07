"""The real ``fastembed`` (ONNX, quantized, CPU-only) embedder adapter.

Opt-in via the ``embeddings`` extra. The heavy model is loaded lazily on first
use and kept warm — which is exactly why the architecture runs embedding inside
the long-lived daemon rather than paying the cold-start cost per command.

Excluded from coverage: exercising it requires a multi-megabyte model download,
so the test suite runs against the deterministic embedder instead.
"""

from __future__ import annotations

from docir.domain.ports.embedder import Embedder
from docir.domain.value_objects.embedding import Embedding

_DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


class FastEmbedEmbedder(Embedder):  # pragma: no cover
    """Wraps ``fastembed.TextEmbedding`` behind the :class:`Embedder` port."""

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        self._model_name = model_name
        self._model: object | None = None
        self._dimension = 384  # bge-small-en-v1.5 output size

    def _ensure_model(self) -> object:
        if self._model is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as exc:
                raise RuntimeError(
                    "fastembed is not installed; install the 'embeddings' extra"
                ) from exc
            self._model = TextEmbedding(model_name=self._model_name)
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_id(self) -> str:
        return f"fastembed:{self._model_name}"

    def embed(self, text: str) -> Embedding:
        model = self._ensure_model()
        vectors = list(model.embed([text]))  # type: ignore[attr-defined]
        values = tuple(float(component) for component in vectors[0])
        self._dimension = len(values)
        return Embedding(values)
