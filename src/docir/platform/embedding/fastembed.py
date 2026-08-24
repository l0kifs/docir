"""The real ``fastembed`` (ONNX, quantized, CPU-only) embedder adapter.

This is the default embedder: ``DOCIR_EMBEDDER=deterministic`` selects the
model-free hashing fallback instead. The model is loaded lazily on first use and
kept warm — which is exactly why embedding runs inside the long-lived daemon
rather than paying the ~4s cold start per command.

Not omitted from the gates, despite needing a model download: it is what every
default install runs, so a type error or a broken call here reaches every user.
The tests that exercise it are marked ``slow``.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol, cast

from docir.platform.embedding.port import Embedder
from docir.platform.embedding.vector import Embedding

_DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


class _TextEmbedding(Protocol):
    """The slice of ``fastembed.TextEmbedding`` this adapter depends on.

    Declared here so the adapter type-checks against a contract rather than
    against ``object`` — the untyped ``object`` it used to hold is what made this
    file need a type-checker exclusion.
    """

    def embed(self, documents: Iterable[str]) -> Iterable[Sequence[float]]: ...


class FastEmbedEmbedder(Embedder):
    """Wraps ``fastembed.TextEmbedding`` behind the :class:`Embedder` port."""

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        self._model_name = model_name
        self._model: _TextEmbedding | None = None

    def _ensure_model(self) -> _TextEmbedding:
        if self._model is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as exc:  # pragma: no cover - dependency is required
                raise RuntimeError(
                    "fastembed is not installed; reinstall docir, or set "
                    "DOCIR_EMBEDDER=deterministic to use the model-free embedder"
                ) from exc
            self._model = cast(_TextEmbedding, TextEmbedding(model_name=self._model_name))
        return self._model

    @property
    def model_id(self) -> str:
        return f"fastembed:{self._model_name}"

    def embed(self, text: str) -> Embedding:
        vectors = list(self._ensure_model().embed([text]))
        values = tuple(float(component) for component in vectors[0])
        return Embedding(values)
