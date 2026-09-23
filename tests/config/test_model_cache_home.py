"""Where a downloaded embedding model lives (adr-78090be868ec).

Guards issue-c5c089bcc1b2. fastembed's default is under the temp directory, which
is where the system puts state it may delete — so the 64 MB download was re-paid
on every sweep, and where there is no temp directory at all it raised before
docir ran.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from docir.config.settings import (
    EMBED_THREADS_ENV,
    MODEL_CACHE_ENV,
    Settings,
    embed_threads,
    model_cache_home,
)
from docir.platform.embedding.fastembed import FastEmbedEmbedder


def test_it_is_user_level_and_not_the_store(monkeypatch, tmp_path: Path) -> None:
    """The half that is easy to 'simplify' into a bug.

    A project store is one per repository and a committed artifact, so a model
    inside it would be downloaded per repository and would need gitignoring to
    stay out of every teammate's working tree. The model is identical for every
    store on the machine.
    """
    monkeypatch.delenv(MODEL_CACHE_ENV, raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path / "user"))
    project = Settings.resolve(home=tmp_path / "repo" / ".docir", use_daemon=False)

    cache = model_cache_home()

    assert cache == tmp_path / "user" / ".docir" / "models"
    assert project.home not in cache.parents
    assert cache != project.home / "models"


def test_it_is_not_under_the_temp_directory(monkeypatch) -> None:
    """The defect itself, and the one test here that must not use ``tmp_path``.

    `tmp_path` *is* under the temp directory — that is what it is for — so a
    fake home built from it puts the answer inside the very directory this
    asserts it stays out of. On Linux that fails outright, whatever
    `model_cache_home` returns; on macOS it passed for a reason unrelated to
    the property asserted, because `gettempdir()` reports ``/var/folders/…``
    where `tmp_path` reports the symlink-resolved ``/private/var/folders/…``
    and `in .parents` compares components rather than filesystem identity.
    Green where it was written and impossible where it ran
    (issue-64e4ff192ebb).

    So the home is built from the filesystem root instead, and both sides are
    resolved. The first assertion is the fixture's own precondition: without it
    a later "simplification" back to `tmp_path` restores the blind spot on the
    one platform that would not notice.
    """
    import tempfile

    temp = Path(tempfile.gettempdir()).resolve()
    outside = Path(temp.anchor) / "docir-home-outside-any-temp-dir"
    assert temp not in outside.parents, "the fake home must itself sit outside the temp dir"

    monkeypatch.delenv(MODEL_CACHE_ENV, raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: outside))

    assert temp not in model_cache_home().resolve().parents


def test_an_explicit_choice_wins(monkeypatch, tmp_path: Path) -> None:
    # A CI image that pins this is naming a directory it also caches, and two
    # sides naming different directories is the defect this repo's own workflow
    # comment already records.
    monkeypatch.setenv(MODEL_CACHE_ENV, str(tmp_path / "pinned"))
    assert model_cache_home() == tmp_path / "pinned"


def test_an_empty_override_is_not_a_choice(monkeypatch, tmp_path: Path) -> None:
    # An unset variable exported as "" is the ordinary shell accident, and
    # `Path("")` is the current directory — a model downloaded into the repo.
    monkeypatch.setenv(MODEL_CACHE_ENV, "   ")
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path / "user"))

    assert model_cache_home() == tmp_path / "user" / ".docir" / "models"


def test_it_answers_where_there_is_no_temporary_directory(monkeypatch, tmp_path: Path) -> None:
    """The sandbox case, which is why it must not consult `tempfile` at all."""
    import tempfile

    def refuse() -> str:
        raise FileNotFoundError("No usable temporary directory found in []")

    monkeypatch.setattr(tempfile, "gettempdir", refuse)
    monkeypatch.delenv(MODEL_CACHE_ENV, raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path / "user"))

    assert model_cache_home() == tmp_path / "user" / ".docir" / "models"


class TestTheAdapterPassesItAsAnArgument:
    """Not by exporting the variable, which cannot work.

    `define_cache_dir` computes `tempfile.gettempdir()/fastembed_cache` *before*
    it reads `FASTEMBED_CACHE_PATH`, so in a sandbox the default raises and the
    override is never consulted. The constructor argument is the only route.
    """

    def _record(self, monkeypatch) -> dict:
        import fastembed

        seen: dict = {}

        class _Fake:
            def __init__(self, **kwargs) -> None:
                seen.update(kwargs)

            def embed(self, documents):
                return [[0.0, 1.0] for _ in documents]

        monkeypatch.setattr(fastembed, "TextEmbedding", _Fake)
        return seen

    def test_the_path_reaches_fastembed(self, monkeypatch, tmp_path: Path) -> None:
        seen = self._record(monkeypatch)

        FastEmbedEmbedder("a/model", cache_dir=tmp_path / "models").embed("x")

        assert seen["cache_dir"] == str(tmp_path / "models")
        assert seen["model_name"] == "a/model"

    def test_no_path_still_means_whatever_fastembed_decides(self, monkeypatch) -> None:
        seen = self._record(monkeypatch)

        FastEmbedEmbedder("a/model").embed("x")

        assert seen["cache_dir"] is None


def test_the_composition_root_wires_it(monkeypatch, tmp_path: Path) -> None:
    """The seam that makes the rest of this true for a real command."""
    from docir.entry_points.composition import build_embedder

    monkeypatch.delenv("DOCIR_EMBEDDER", raising=False)
    monkeypatch.delenv(MODEL_CACHE_ENV, raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path / "user"))

    embedder = build_embedder("BAAI/bge-small-en-v1.5")

    assert isinstance(embedder, FastEmbedEmbedder)
    assert embedder._cache_dir == tmp_path / "user" / ".docir" / "models"


class TestTheThreadCap:
    """How many cores the model may take (GitHub #23).

    Unset means fastembed's own behaviour, which is every core: fine on a build
    machine, and the reported complaint on a laptop, where warming the model, a
    reindex and each `context` query all saturate the CPU.

    An environment variable and never a schema key: a store is a committed
    artifact read by whoever clones it, so a core count inside it would impose
    one laptop's hardware on the whole team — the argument that keeps the model
    itself out of the store, one field over.
    """

    def test_unset_means_fastembeds_own_default(self, monkeypatch) -> None:
        monkeypatch.delenv(EMBED_THREADS_ENV, raising=False)
        assert embed_threads() is None

    def test_a_positive_count_is_the_cap(self, monkeypatch) -> None:
        monkeypatch.setenv(EMBED_THREADS_ENV, "4")
        assert embed_threads() == 4

    @pytest.mark.parametrize("value", ["0", "-2", "abc", "   ", "2.5"])
    def test_an_unusable_value_is_ignored_rather_than_raised(self, monkeypatch, value: str) -> None:
        """Read while every container is built, `docir doctor` included.

        A typo in a shell profile that made the command somebody runs *to
        diagnose the problem* refuse to start would be the worst failure this
        could have. `doctor` reports the effective value instead, which is
        where they look.
        """
        monkeypatch.setenv(EMBED_THREADS_ENV, value)
        assert embed_threads() is None


class TestTheCapReachesTheModel:
    """The half that makes the setting mean anything.

    `threads` is a constructor argument, and fastembed turns it into ONNX's
    `intra_op_num_threads` and `inter_op_num_threads` — so it caps the warm-up,
    the reindex and every query, which is the whole of what #23 reports.
    """

    def _record(self, monkeypatch) -> dict:
        import fastembed

        seen: dict = {}

        class _Fake:
            def __init__(self, **kwargs) -> None:
                seen.update(kwargs)

            def embed(self, documents):
                return [[0.0, 1.0] for _ in documents]

        monkeypatch.setattr(fastembed, "TextEmbedding", _Fake)
        return seen

    def test_the_cap_is_passed_as_a_constructor_argument(self, monkeypatch) -> None:
        seen = self._record(monkeypatch)

        FastEmbedEmbedder("a/model", threads=3).embed("x")

        assert seen["threads"] == 3

    def test_no_cap_still_means_whatever_fastembed_decides(self, monkeypatch) -> None:
        seen = self._record(monkeypatch)

        FastEmbedEmbedder("a/model").embed("x")

        assert seen["threads"] is None

    def test_the_composition_root_wires_the_variable(self, monkeypatch, tmp_path: Path) -> None:
        """The seam that makes the rest true for a real command."""
        from docir.entry_points.composition import build_embedder

        monkeypatch.delenv("DOCIR_EMBEDDER", raising=False)
        monkeypatch.delenv(MODEL_CACHE_ENV, raising=False)
        monkeypatch.setenv(EMBED_THREADS_ENV, "2")
        monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path / "user"))

        embedder = build_embedder("BAAI/bge-small-en-v1.5")

        assert isinstance(embedder, FastEmbedEmbedder)
        assert embedder._threads == 2
