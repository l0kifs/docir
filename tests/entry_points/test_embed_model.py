"""``verify_embed_model`` — the store's embedding model is checked, not gated.

The catalogue names what docir has *measured*, not what it permits: a model
fastembed supports but docir has not benchmarked is accepted with a warning,
because the corpus is the user's and somebody writing in a language docir has
never measured is better placed to choose than the tuple is. Only a name
nothing supports is refused.

The branch tests stub ``fastembed`` so they are hermetic and can assert the
thing that matters most about the fast path: that a measured name never reaches
the import at all. One ``slow`` test then pins the stub's shape against the real
library, so the branch tests cannot pass by agreeing with a fiction.
"""

from __future__ import annotations

import sys
import types
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from docir.entry_points.composition import verify_embed_model
from docir.platform.embedding.catalogue import DEFAULT_EMBED_MODEL, VERIFIED_EMBED_MODELS
from docir.platform.errors import SchemaError

#: A name fastembed knows and docir has not measured.
UNMEASURED = "jinaai/jina-embeddings-v2-small-en"


@contextmanager
def no_warning() -> Iterator[None]:
    """Fail the test if anything warns inside the block."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        yield


@pytest.fixture
def listed(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Stub ``fastembed``, recording every ``list_supported_models`` call."""
    calls: list[int] = []

    class _TextEmbedding:
        @staticmethod
        def list_supported_models() -> list[dict[str, Any]]:
            calls.append(1)
            return [{"model": name} for name in (*VERIFIED_EMBED_MODELS, UNMEASURED)]

    module = types.ModuleType("fastembed")
    module.TextEmbedding = _TextEmbedding  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fastembed", module)
    return calls


class TestVerifyEmbedModel:
    def test_absent_is_silent_and_asks_nothing(self, listed: list[int]) -> None:
        with no_warning():
            verify_embed_model(None)
        assert listed == []

    @pytest.mark.parametrize("name", VERIFIED_EMBED_MODELS)
    def test_a_measured_name_never_reaches_the_import(self, name: str, listed: list[int]) -> None:
        # The assertion that matters is `listed == []`: importing fastembed is
        # most of a cold start, and it runs on every command. A refactor that
        # checks membership first and short-circuits second would still pass a
        # "does not warn" test, and fail this one.
        with no_warning():
            verify_embed_model(name)
        assert listed == []

    def test_a_supported_but_unmeasured_name_warns_and_is_accepted(self, listed: list[int]) -> None:
        with pytest.warns(RuntimeWarning) as caught:
            verify_embed_model(UNMEASURED)
        assert listed == [1]
        message = str(caught[0].message)
        # It has to say *why* an accepted model may still disappoint, or the
        # warning is noise the reader learns to skip.
        assert UNMEASURED in message
        assert "asymmetric" in message

    def test_a_name_nothing_supports_is_refused_naming_both_sets(self, listed: list[int]) -> None:
        with pytest.raises(SchemaError) as exc:
            verify_embed_model("my-org/my-finetune")
        message = str(exc.value)
        assert "my-org/my-finetune" in message
        # Both halves: what has been measured, and that others are allowed —
        # otherwise the error reads as "these three or nothing", which is the
        # behaviour this function was rewritten to stop having.
        assert DEFAULT_EMBED_MODEL in message
        assert "accepted with a warning" in message

    def test_refusal_beats_the_warning_for_an_unknown_name(self, listed: list[int]) -> None:
        # Injected bug: warn-then-raise would emit a caveat about a model that
        # does not exist, and the caveat is the line a reader keeps.
        with no_warning(), pytest.raises(SchemaError):
            verify_embed_model("my-org/my-finetune")


@pytest.mark.slow
def test_the_stub_matches_the_real_library() -> None:
    """Pin the shape the branch tests stub, against fastembed itself.

    Metadata only — ``list_supported_models`` downloads nothing. Without this
    the tests above would keep passing after fastembed renamed the key or
    dropped the default model, which is precisely when they should fail.
    """
    from fastembed import TextEmbedding

    supported = {str(entry["model"]) for entry in TextEmbedding.list_supported_models()}
    assert DEFAULT_EMBED_MODEL in supported
    assert UNMEASURED in supported
    for name in VERIFIED_EMBED_MODELS:
        assert name in supported, f"{name} is in the catalogue and fastembed no longer has it"
