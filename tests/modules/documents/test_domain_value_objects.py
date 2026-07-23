"""Unit tests for the domain value objects."""

from __future__ import annotations

import pytest

from docir.modules.documents.domain.services.slugify import slugify
from docir.modules.documents.domain.value_objects.identifiers import DocId
from docir.platform.embedding.vector import Embedding
from docir.platform.errors import ValidationError


class TestDocId:
    def test_build_zero_pads(self) -> None:
        assert DocId.build("adr", 7).value == "adr-0007"

    def test_prefix_and_number(self) -> None:
        doc_id = DocId("issue-0012")
        assert doc_id.prefix == "issue"
        assert doc_id.number == 12
        assert str(doc_id) == "issue-0012"

    @pytest.mark.parametrize("bad", ["adr7", "adr-", "-0007", "ADR-0007", "adr-12"])
    def test_malformed_ids_rejected(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            DocId(bad)

    def test_random_id_is_valid_and_unique(self) -> None:
        ids = {DocId.build_random("adr").value for _ in range(200)}
        assert len(ids) == 200
        assert all(i.startswith("adr-") for i in ids)

    def test_random_id_parses(self) -> None:
        doc_id = DocId("adr-3f9a2b1c7d4e")
        assert doc_id.prefix == "adr"
        assert doc_id.suffix == "3f9a2b1c7d4e"

    def test_number_raises_for_random_id(self) -> None:
        with pytest.raises(ValidationError):
            _ = DocId("adr-3f9a2b1c7d4e").number


class TestEmbedding:
    def test_bytes_round_trip(self) -> None:
        embedding = Embedding((0.5, -0.25, 1.0))
        restored = Embedding.from_bytes(embedding.to_bytes())
        assert restored.dimension == 3
        for original, value in zip(embedding.values, restored.values, strict=True):
            assert original == pytest.approx(value)

    def test_cosine_identical_is_one(self) -> None:
        embedding = Embedding((1.0, 2.0, 3.0))
        assert embedding.cosine_similarity(embedding) == pytest.approx(1.0)

    def test_cosine_orthogonal_is_zero(self) -> None:
        a = Embedding((1.0, 0.0))
        b = Embedding((0.0, 1.0))
        assert a.cosine_similarity(b) == pytest.approx(0.0)

    def test_cosine_zero_vector_is_zero(self) -> None:
        a = Embedding((0.0, 0.0))
        b = Embedding((1.0, 1.0))
        assert a.cosine_similarity(b) == 0.0

    def test_dimension_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="dimension mismatch"):
            Embedding((1.0,)).cosine_similarity(Embedding((1.0, 2.0)))


class TestSlugify:
    @pytest.mark.parametrize(
        ("title", "expected"),
        [
            ("Auth Strategy", "auth-strategy"),
            ("  Refresh   token!! ", "refresh-token"),
            ("###", "untitled"),
            ("", "untitled"),
        ],
    )
    def test_slugify(self, title: str, expected: str) -> None:
        assert slugify(title) == expected

    def test_slugify_truncates(self) -> None:
        assert len(slugify("a " * 100, max_length=10)) <= 10
