"""A slow step may say it is running, but only to a human at a terminal.

Five commands could block for a long time with nothing on screen — `reindex`,
`daemon start`, `doctor --probe`, `self upgrade`, and any command at all under
`--no-daemon`, which loads the embedding model and on a cold cache downloads
~67 MB first. Silence there is indistinguishable from a hang, and the first-run
download is the one every new user meets.

The notice has three readers and only one of them wants it. stdout carries the
JSON an agent parses; an MCP client speaks its protocol over the child's stdout
and reads stderr as its log; the human is the only one who cannot tell a long
operation from a dead one. So the rule is stderr, terminal only — and stdout is
never touched either way, which is the half that would corrupt a payload.
"""

from __future__ import annotations

import pytest
from rich.console import Console

from docir.entry_points.cli import rendering


@pytest.fixture
def consoles(monkeypatch) -> tuple[Console, Console]:
    """Replace both consoles with recording ones, and return them."""
    out, err = Console(record=True, force_terminal=True), Console(record=True, force_terminal=True)
    monkeypatch.setattr(rendering, "console", out)
    monkeypatch.setattr(rendering, "error_console", err)
    return out, err


class TestAtATerminal:
    def test_progress_says_what_is_running(self, consoles) -> None:
        _, err = consoles
        with rendering.progress("rebuilding the index"):
            pass
        assert "rebuilding the index" in err.export_text()

    def test_notice_says_what_is_running(self, consoles) -> None:
        _, err = consoles
        rendering.render_notice("upgrading the docir package")
        assert "upgrading the docir package" in err.export_text()

    @pytest.mark.parametrize("emit", ["progress", "notice"])
    def test_stdout_is_never_touched(self, consoles, emit: str) -> None:
        out, _ = consoles
        if emit == "progress":
            with rendering.progress("rebuilding the index"):
                pass
        else:
            rendering.render_notice("rebuilding the index")
        assert out.export_text() == ""


class TestNotATerminal:
    """A pipe means an agent or an MCP client is reading. Say nothing."""

    @pytest.fixture
    def piped(self, monkeypatch) -> Console:
        err = Console(record=True, force_terminal=False, force_interactive=False)
        monkeypatch.setattr(rendering, "error_console", err)
        return err

    def test_progress_stays_silent_and_still_runs_the_block(self, piped: Console) -> None:
        ran = False
        with rendering.progress("rebuilding the index"):
            ran = True
        assert ran
        assert piped.export_text() == ""

    def test_notice_stays_silent(self, piped: Console) -> None:
        rendering.render_notice("upgrading the docir package")
        assert piped.export_text() == ""
