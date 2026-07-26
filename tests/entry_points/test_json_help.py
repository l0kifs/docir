"""``--help`` must obey the same JSON/table contract as every other command.

``--help`` is an *eager* Click parameter: it renders and exits during parsing,
before the app callback sets ``CliState``. That made it the one command whose
output ignored the "piped stdout means compact JSON" promise, so an agent
capturing ``docir --help`` got a Rich panel whose box-drawing characters were
roughly a tenth of the payload.
"""

from __future__ import annotations

import json

import pytest

from docir.entry_points.cli.app import _install_json_help, app
from docir.entry_points.cli.runner import help_wants_json


def _help(argv: list[str], *, isatty: bool, monkeypatch) -> str:
    """Render help for ``argv`` with a controlled TTY and argv, as main() does."""
    from typer.main import get_command

    monkeypatch.setattr("sys.argv", ["docir", *argv])
    monkeypatch.setattr("sys.stdout.isatty", lambda: isatty, raising=False)

    command = get_command(app)
    _install_json_help(command)
    target = command
    ctx_path = ["docir"]
    for token in argv:
        if token.startswith("-"):
            continue
        sub = getattr(target, "commands", {}).get(token)
        if sub is None:
            break
        target, _ = sub, ctx_path.append(token)

    from typer import _click as click

    with click.Context(target, info_name=ctx_path[-1]) as ctx:
        return target.get_help(ctx)


class TestHelpWantsJson:
    @pytest.mark.parametrize(
        ("argv", "isatty", "expected"),
        [
            ([], False, True),  # piped -> the agent path
            ([], True, False),  # a human at a terminal
            (["--json"], True, True),  # --json forces JSON anywhere
            (["--pretty"], False, False),  # --pretty forces the panel anywhere
            (["--pretty", "--json"], False, False),  # --pretty wins, as in use_json
        ],
    )
    def test_precedence_matches_use_json(
        self, argv: list[str], isatty: bool, expected: bool, monkeypatch
    ) -> None:
        monkeypatch.setattr("sys.stdout.isatty", lambda: isatty, raising=False)
        assert help_wants_json(argv) is expected


class TestJsonHelp:
    def test_root_help_is_json_when_piped(self, monkeypatch) -> None:
        payload = json.loads(_help([], isatty=False, monkeypatch=monkeypatch))
        assert payload["command"] == "docir"
        assert payload["usage"].startswith("docir [OPTIONS]")
        names = {entry["name"] for entry in payload["commands"]}
        assert {"add", "get", "schema", "tag"} <= names
        flags = {flag for opt in payload["options"] for flag in opt["flags"]}
        assert "--home" in flags
        # `--help` describes itself nowhere; it is noise for a caller already
        # reading the help payload.
        assert "--help" not in flags

    def test_subgroup_and_leaf_help_are_json(self, monkeypatch) -> None:
        group = json.loads(_help(["schema"], isatty=False, monkeypatch=monkeypatch))
        assert {entry["name"] for entry in group["commands"]} == {"show", "validate"}

        leaf = json.loads(_help(["add"], isatty=False, monkeypatch=monkeypatch))
        assert leaf["commands"] == []
        required = {flag for opt in leaf["options"] if opt["required"] for flag in opt["flags"]}
        assert {"--type", "--title", "--description"} <= required

    def test_human_help_keeps_the_rich_panel(self, monkeypatch, capsys) -> None:
        # Typer's rich help *prints* to the console and returns "" rather than
        # returning the text, so the panel is asserted on captured stdout.
        returned = _help([], isatty=True, monkeypatch=monkeypatch)
        rendered = capsys.readouterr().out
        assert not returned.lstrip().startswith("{")
        assert "Usage:" in rendered
        assert set(rendered) & set("│╭╰"), "expected the Rich box for a human"

    def test_json_help_carries_no_box_drawing(self, monkeypatch) -> None:
        text = _help([], isatty=False, monkeypatch=monkeypatch)
        assert not set(text) & set("│┃╭╰┏┗━─╮╯┓┛")
