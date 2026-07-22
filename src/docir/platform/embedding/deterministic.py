"""A deterministic, dependency-free embedder.

Uses signed feature hashing: each token is hashed to a bucket and a sign, and
its contribution is accumulated with a term-frequency dampening. The result is
L2-normalized so cosine similarity behaves well. It captures real lexical
overlap (shared vocabulary → higher similarity) without any model download,
which keeps the default install light and every test hermetic and reproducible.
"""

from __future__ import annotations

import hashlib
import math
import re

from docir.platform.embedding.port import Embedder
from docir.platform.embedding.vector import Embedding

_TOKEN_RE = re.compile(r"[\w-]+", re.UNICODE)
_DEFAULT_DIMENSION = 256


class DeterministicEmbedder(Embedder):
    """Feature-hashing embedder producing stable, offline vectors."""

    def __init__(self, dimension: int = _DEFAULT_DIMENSION) -> None:
        if dimension <= 0:
            raise ValueError("dimension must be positive")
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_id(self) -> str:
        return f"deterministic-hash-{self._dimension}-v1"

    def embed(self, text: str) -> Embedding:
        buckets = [0.0] * self._dimension
        for token in _TOKEN_RE.findall(text.lower()):
            digest = hashlib.sha1(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "little") % self._dimension
            sign = 1.0 if digest[4] & 1 else -1.0
            buckets[index] += sign
        norm = math.sqrt(sum(value * value for value in buckets))
        if norm > 0.0:
            buckets = [value / norm for value in buckets]
        return Embedding(tuple(buckets))
