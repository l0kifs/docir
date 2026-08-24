"""The :class:`Embedder` port — turns text into a semantic vector.

Implementations: a deterministic, dependency-free hashing embedder (the
default, used everywhere including tests) and a real ``fastembed`` ONNX
adapter. Both satisfy this interface so the semantic layer is model-agnostic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from docir.platform.embedding.vector import Embedding


class Embedder(ABC):
    """Computes a dense semantic vector for a piece of text.

    Deliberately narrow: ``model_id`` and ``embed``, and nothing about the
    *shape* of what comes back. A ``dimension`` member lived here and was read
    by nobody — storage is width-agnostic (``Embedding.to_bytes`` handles any
    length and the columns are BLOBs), and the one place a width could
    disagree, comparing two vectors, is checked by ``Embedding`` itself where
    both are in hand (issue-6618d3a9e868).
    """

    @property
    @abstractmethod
    def model_id(self) -> str:
        """A stable identifier for the model/version, for staleness checks."""

    @abstractmethod
    def embed(self, text: str) -> Embedding:
        """Return the embedding vector for ``text``."""
