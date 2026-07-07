"""The :class:`Embedder` port — turns text into a semantic vector.

Implementations: a deterministic, dependency-free hashing embedder (the
default, used everywhere including tests) and a real ``fastembed`` ONNX
adapter. Both satisfy this interface so the semantic layer is model-agnostic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from docir.domain.value_objects.embedding import Embedding


class Embedder(ABC):
    """Computes a dense semantic vector for a piece of text."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """The fixed dimensionality of vectors this embedder produces."""

    @property
    @abstractmethod
    def model_id(self) -> str:
        """A stable identifier for the model/version, for staleness checks."""

    @abstractmethod
    def embed(self, text: str) -> Embedding:
        """Return the embedding vector for ``text``."""
