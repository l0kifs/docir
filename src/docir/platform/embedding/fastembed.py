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
from pathlib import Path
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

    def __init__(
        self,
        model_name: str = _DEFAULT_MODEL,
        *,
        cache_dir: Path | None = None,
        threads: int | None = None,
    ) -> None:
        self._model_name = model_name
        self._cache_dir = cache_dir
        self._threads = threads
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
            # Passed, not left to fastembed's default. `define_cache_dir`
            # computes `tempfile.gettempdir()/fastembed_cache` *before* it reads
            # `FASTEMBED_CACHE_PATH`, so the variable cannot rescue a sandbox
            # with no temp directory and this argument is the only thing that
            # can — and a temp directory is the wrong home for a 67 MB download
            # anyway, being where the system puts what it may delete
            # (issue-c5c089bcc1b2). `None` still means "whatever fastembed
            # decides", which is what a caller building this directly gets.
            cache_dir = str(self._cache_dir) if self._cache_dir is not None else None
            # `threads` reaches ONNX as both `intra_op_num_threads` and
            # `inter_op_num_threads`, so it caps every path that runs the model:
            # the warm-up, a reindex, and each query `context` embeds. `None` is
            # fastembed's own behaviour, which is every core — fine on a build
            # machine, and the complaint on a laptop (GitHub #23).
            self._model = cast(
                _TextEmbedding,
                TextEmbedding(
                    model_name=self._model_name,
                    cache_dir=cache_dir,
                    threads=self._threads,
                ),
            )
        return self._model

    @property
    def model_id(self) -> str:
        return f"fastembed:{self._model_name}"

    def embed(self, text: str) -> Embedding:
        vectors = list(self._ensure_model().embed([text]))
        values = tuple(float(component) for component in vectors[0])
        return Embedding(values)
