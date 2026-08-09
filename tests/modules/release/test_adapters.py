"""The three adapters, at the seam where they touch the outside world.

Nothing here reaches the network: the PyPI client is exercised against a fake
``urlopen``, which is also the only way to assert the failure modes that matter
(every one of them has to become ``None``).
"""

from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path

import pytest

from docir.modules.release.infra import adapters
from docir.modules.release.infra.adapters import (
    JsonFileReleaseCache,
    PyPIReleaseIndex,
    SubprocessRunner,
)


class TestTheCache:
    def test_it_round_trips(self, tmp_path: Path) -> None:
        cache = JsonFileReleaseCache(tmp_path / "nested" / "release-check.json")
        cache.write("0.12.0", "2026-07-07")
        assert cache.read() == ("0.12.0", "2026-07-07")

    def test_a_missing_file_is_unknown(self, tmp_path: Path) -> None:
        assert JsonFileReleaseCache(tmp_path / "absent.json").read() is None

    @pytest.mark.parametrize("content", ["not json", "[]", '{"latest": 12}', "{}"])
    def test_unusable_content_is_unknown_rather_than_an_error(
        self, tmp_path: Path, content: str
    ) -> None:
        # Derived, disposable state: the worst it may do is say nothing.
        path = tmp_path / "release-check.json"
        path.write_text(content, encoding="utf-8")
        assert JsonFileReleaseCache(path).read() is None


class TestTheReleaseIndex:
    @staticmethod
    def _answer(monkeypatch: pytest.MonkeyPatch, payload: object) -> None:
        class _Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *_args) -> None:
                self.close()

        monkeypatch.setattr(
            adapters.urllib.request,
            "urlopen",
            lambda *_args, **_kwargs: _Response(json.dumps(payload).encode()),
        )

    def test_it_reads_the_version(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._answer(monkeypatch, {"info": {"version": "0.12.0"}})
        assert PyPIReleaseIndex().latest_version("docir") == "0.12.0"

    @pytest.mark.parametrize("payload", [{}, {"info": {}}, {"info": "0.12.0"}, []])
    def test_an_unexpected_shape_is_unknown(
        self, monkeypatch: pytest.MonkeyPatch, payload: object
    ) -> None:
        self._answer(monkeypatch, payload)
        assert PyPIReleaseIndex().latest_version("docir") is None

    def test_an_unreachable_index_is_unknown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _fail(*_args, **_kwargs):
            raise urllib.error.URLError("offline")

        monkeypatch.setattr(adapters.urllib.request, "urlopen", _fail)
        assert PyPIReleaseIndex().latest_version("docir") is None


class TestTheProcessRunner:
    def test_it_reports_the_exit_status_and_output(self) -> None:
        status, output = SubprocessRunner().run(
            ["python", "-c", "import sys; print('hi'); sys.exit(3)"]
        )
        assert status == 3
        assert "hi" in output

    def test_a_missing_installer_is_an_exit_status_not_a_traceback(self) -> None:
        # `uv tool upgrade` on a machine without uv: the CLI has to print this,
        # not crash on it.
        status, output = SubprocessRunner().run(["docir-no-such-installer", "upgrade"])
        assert status == 127
        assert "not found on PATH" in output
