"""Where a downloaded embedding model lives (adr-78090be868ec).

Guards issue-c5c089bcc1b2. fastembed's default is under the temp directory, which
is where the system puts state it may delete — so the 64 MB download was re-paid
on every sweep, and where there is no temp directory at all it raised before
docir ran.
"""

from __future__ import annotations

from pathlib import Path

from docir.config.settings import MODEL_CACHE_ENV, Settings, model_cache_home
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


def test_it_is_not_under_the_temp_directory(monkeypatch, tmp_path: Path) -> None:
    import tempfile

    monkeypatch.delenv(MODEL_CACHE_ENV, raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path / "user"))

    assert Path(tempfile.gettempdir()) not in model_cache_home().parents


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
