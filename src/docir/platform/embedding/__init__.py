"""Embedding capability: the :class:`Embedder` port and the vector value object.

Meaning-free text-to-vector primitive. Concrete embedders (deterministic,
fastembed) are imported directly from their submodules by the composition root.
"""

from docir.platform.embedding.port import Embedder
from docir.platform.embedding.vector import Embedding

__all__ = ["Embedder", "Embedding"]
