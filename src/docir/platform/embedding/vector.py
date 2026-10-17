"""The :class:`Embedding` value object and cosine-similarity math.

An embedding is a dense vector computed over a document's ``title`` +
``description`` + body. Similarity search at this scale (hundreds to low
thousands of documents) is a brute-force cosine comparison — no ANN index is
needed — so the math lives here in pure Python with no numeric dependency.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass

# Little-endian float32, matching the on-disk BLOB encoding.
_PACK_FMT = "<f"


@dataclass(frozen=True, slots=True)
class Embedding:
    """An immutable dense vector."""

    values: tuple[float, ...]

    @property
    def dimension(self) -> int:
        return len(self.values)

    def to_bytes(self) -> bytes:
        """Serialize to a compact float32 BLOB for SQLite storage."""
        return b"".join(struct.pack(_PACK_FMT, v) for v in self.values)

    @classmethod
    def from_bytes(cls, blob: bytes) -> Embedding:
        """Deserialize a float32 BLOB back into an :class:`Embedding`."""
        count = len(blob) // 4
        values = struct.unpack(f"<{count}f", blob)
        return cls(tuple(values))

    def cosine_similarity(self, other: Embedding) -> float:
        """Cosine similarity in ``[-1.0, 1.0]``; ``0.0`` for a zero vector."""
        if self.dimension != other.dimension:
            raise ValueError(f"dimension mismatch: {self.dimension} != {other.dimension}")
        # `math.sumprod` runs the loop in C. Generator sums over 384 floats cost
        # ~60ms per `context` call on a 1,947-vector store; this is ~7ms, and
        # it is the semantic scan, the one read cost that grows with the corpus.
        dot = math.sumprod(self.values, other.values)
        norm_a = math.sqrt(math.sumprod(self.values, self.values))
        norm_b = math.sqrt(math.sumprod(other.values, other.values))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)
