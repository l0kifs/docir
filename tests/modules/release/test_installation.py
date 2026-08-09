"""Detection: which installs docir may replace, and which it must leave alone.

The interesting half is the refusals. Running the wrong installer against the
wrong environment is worse than doing nothing, so every case that is not clearly
docir's own environment has to come back with no command and a reason.
"""

from __future__ import annotations

from pathlib import Path

from docir.modules.release.domain.installation import Evidence, detect
from docir.modules.release.infra.probe import gather_evidence


def _evidence(tmp_path: Path, **overrides) -> Evidence:
    base = {
        "prefix": tmp_path,
        "executable": tmp_path / "bin" / "python",
        "has_uv_receipt": False,
        "has_pipx_metadata": False,
        "direct_url": None,
        "editable": False,
        "ephemeral": False,
    }
    return Evidence(**{**base, **overrides})


class TestWhereDocirOwnsItsEnvironment:
    def test_a_uv_tool_install_is_upgraded_with_uv(self, tmp_path: Path) -> None:
        installation = detect(_evidence(tmp_path, has_uv_receipt=True))
        assert installation.method == "uv-tool"
        assert installation.upgrade_command == ("uv", "tool", "upgrade", "docir")

    def test_a_pipx_install_is_upgraded_with_pipx(self, tmp_path: Path) -> None:
        installation = detect(_evidence(tmp_path, has_pipx_metadata=True))
        assert installation.method == "pipx"
        assert installation.upgrade_command == ("pipx", "upgrade", "docir")

    def test_a_virtualenv_is_upgraded_with_this_interpreter(self, tmp_path: Path) -> None:
        # `sys.executable -m pip`, not `pip`: the pip on PATH may belong to a
        # different environment entirely.
        (tmp_path / "pyvenv.cfg").write_text("home = /usr", encoding="utf-8")
        installation = detect(_evidence(tmp_path))
        assert installation.method == "pip"
        assert installation.upgrade_command[:4] == (
            str(tmp_path / "bin" / "python"),
            "-m",
            "pip",
            "install",
        )


class TestWhereItMustNotTouchAnything:
    def test_an_editable_checkout_is_left_to_its_project(self, tmp_path: Path) -> None:
        installation = detect(_evidence(tmp_path, editable=True))
        assert installation.method == "project"
        assert installation.upgrade_command == ()
        assert "uv lock --upgrade-package docir" in installation.explanation

    def test_a_path_install_is_left_alone_even_when_not_editable(self, tmp_path: Path) -> None:
        # `uv pip install .` — installed from a directory, so a lockfile
        # somewhere still believes it decides this version.
        installation = detect(_evidence(tmp_path, direct_url="file:///srv/checkout"))
        assert installation.method == "project"
        assert not installation.can_self_upgrade

    def test_an_ephemeral_uvx_run_has_nothing_to_upgrade(self, tmp_path: Path) -> None:
        installation = detect(_evidence(tmp_path, ephemeral=True))
        assert installation.method == "uvx"
        assert installation.upgrade_command == ()
        assert "uvx docir@latest" in installation.explanation

    def test_an_unrecognised_layout_refuses_to_guess(self, tmp_path: Path) -> None:
        installation = detect(_evidence(tmp_path))
        assert installation.method == "unknown"
        assert installation.upgrade_command == ()

    def test_ephemeral_beats_the_index_url_it_was_installed_from(self, tmp_path: Path) -> None:
        # A uvx environment is a real index install; what makes it untouchable
        # is that it is thrown away, so that case has to be checked first.
        installation = detect(_evidence(tmp_path, ephemeral=True, direct_url=None))
        assert installation.method == "uvx"


def test_the_test_suite_itself_can_never_self_upgrade() -> None:
    """The safety property the whole feature rests on, asserted where it matters.

    Tests run from the workspace checkout, which is an editable install — so
    `detect` classifies it as `project` and no installer can run. If this ever
    fails, a `docir self upgrade` in a test would try to replace the environment
    the suite is running in.
    """
    evidence = gather_evidence()
    assert evidence.editable or evidence.direct_url is not None
    assert not detect(evidence).can_self_upgrade
