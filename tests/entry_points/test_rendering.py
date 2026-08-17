"""Unit tests for CLI rendering: compact-JSON trimming and the human paths.

Since piped output now defaults to JSON, the Rich render_* functions are no
longer hit by the e2e substring tests — they are exercised directly here, along
with the trimming rules and the TTY-aware output decision.
"""

from __future__ import annotations

import json
import sys

import pytest

from docir.config.settings import Settings
from docir.entry_points.cli import rendering
from docir.entry_points.cli.runner import CliState, use_json


class TestEmitJsonTrimming:
    def test_output_is_compact_single_line(self, capsys: pytest.CaptureFixture[str]) -> None:
        rendering.emit_json([{"id": "adr-0001", "score": 0.5}])
        out = capsys.readouterr().out
        assert out.endswith("\n")
        assert "\n" not in out.strip()  # single line
        assert ", " not in out and ": " not in out  # compact separators
        assert json.loads(out) == [{"id": "adr-0001", "score": 0.5}]

    def test_trim_drops_empty_but_keeps_false_and_zero(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rendering.emit_json(
            {
                "id": "x",
                "owner": "",  # dropped
                "related": [],  # dropped
                "verified": None,  # dropped
                "archived": False,  # kept: a real boolean
                "score": 0.0,  # kept: a real zero, not "empty"
                "count": 0,  # kept
            }
        )
        assert json.loads(capsys.readouterr().out) == {
            "id": "x",
            "archived": False,
            "score": 0.0,
            "count": 0,
        }

    def test_trim_rounds_score(self, capsys: pytest.CaptureFixture[str]) -> None:
        rendering.emit_json({"score": 0.03278688524590164})
        assert json.loads(capsys.readouterr().out)["score"] == 0.0328

    def test_trim_rounds_similarity_too(self, capsys: pytest.CaptureFixture[str]) -> None:
        rendering.emit_json({"similarity": 0.40512345678})
        assert json.loads(capsys.readouterr().out)["similarity"] == 0.4051

    def test_a_zero_similarity_survives_trimming(self, capsys: pytest.CaptureFixture[str]) -> None:
        # An absent `similarity` means "not scored" (lexical-only hit, or a
        # graph neighbour). If trimming dropped a real 0.0, an agent reading the
        # payload could not tell "no vector" from "scored nothing" — the exact
        # distinction --min-score depends on.
        rendering.emit_json({"similarity": 0.0})
        assert json.loads(capsys.readouterr().out) == {"similarity": 0.0}

    def test_trim_recurses_into_nested_maps_and_lists(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rendering.emit_json({"a": {"b": "", "c": "keep"}, "d": [{"e": None, "f": 1}]})
        assert json.loads(capsys.readouterr().out) == {"a": {"c": "keep"}, "d": [{"f": 1}]}

    def test_no_trim_keeps_everything_and_full_precision(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        data = {"id": "x", "owner": "", "related": [], "score": 0.03278688524590164}
        rendering.emit_json(data, trim=False)
        assert json.loads(capsys.readouterr().out) == data

    def test_unicode_is_not_escaped(self, capsys: pytest.CaptureFixture[str]) -> None:
        rendering.emit_json({"t": "café ⚠"})
        assert "café ⚠" in capsys.readouterr().out


class TestUseJson:
    def _state(self, settings: Settings, **kwargs: object) -> CliState:
        return CliState(settings=settings, **kwargs)  # type: ignore[arg-type]

    def test_pretty_forces_tables(self, settings: Settings) -> None:
        assert use_json(self._state(settings, pretty=True, json_output=True)) is False

    def test_json_flag_forces_json(self, settings: Settings) -> None:
        assert use_json(self._state(settings, json_output=True)) is True

    def test_defaults_to_json_when_piped(
        self, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "stdout", type("F", (), {"isatty": lambda self: False})())
        assert use_json(self._state(settings)) is True

    def test_defaults_to_tables_at_a_tty(
        self, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "stdout", type("F", (), {"isatty": lambda self: True})())
        assert use_json(self._state(settings)) is False


class TestHumanRenderers:
    def test_render_document_full(self, capsys: pytest.CaptureFixture[str]) -> None:
        rendering.render_document(
            {
                "id": "adr-0001",
                "type": "decision",
                "status": "accepted",
                "title": "Auth",
                "description": "d",
                "tags": ["auth"],
                "related": [
                    {"target": "adr-0002", "kind": "supersedes"},
                    {"target": "adr-0003", "kind": "relates_to"},
                ],
                "owner": "team",
                "verified": "2026-01-01",
                "stale": True,
                "archived": True,
                "body": "BODY TEXT",
            }
        )
        out = capsys.readouterr().out
        for token in ("adr-0001", "BODY TEXT", "stale", "archived", "team", "adr-0002"):
            assert token in out

    def test_render_document_minimal(self, capsys: pytest.CaptureFixture[str]) -> None:
        rendering.render_document(
            {"id": "issue-0001", "type": "issue", "status": "open", "title": "T"}
        )
        assert "issue-0001" in capsys.readouterr().out

    def test_render_document_list_with_markers(self, capsys: pytest.CaptureFixture[str]) -> None:
        rendering.render_document_list(
            [
                {
                    "id": "adr-0001",
                    "type": "decision",
                    "status": "accepted",
                    "title": "T",
                    "description": "d",
                    "score": 0.5,
                    "via_graph": True,
                    "stale": True,
                }
            ]
        )
        assert "adr-0001" in capsys.readouterr().out

    def test_render_document_list_empty(self, capsys: pytest.CaptureFixture[str]) -> None:
        rendering.render_document_list([])
        assert "no matching" in capsys.readouterr().out

    def test_render_tags(self, capsys: pytest.CaptureFixture[str]) -> None:
        rendering.render_tags([{"key": "auth", "description": "d", "usage": 3}])
        out = capsys.readouterr().out
        assert "auth" in out
        assert "3" in out

    def test_render_tags_shows_a_dead_tag_as_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        # Zero is the finding, so it has to be on screen, not blank.
        rendering.render_tags([{"key": "dead", "description": "d", "usage": 0}])
        assert "0" in capsys.readouterr().out

    def test_render_tags_empty(self, capsys: pytest.CaptureFixture[str]) -> None:
        rendering.render_tags([])
        assert "no tags" in capsys.readouterr().out

    def test_render_findings(self, capsys: pytest.CaptureFixture[str]) -> None:
        rendering.render_findings(
            [{"kind": "orphan", "message": "m", "doc_ids": ["a", "b"]}], empty="none"
        )
        assert "orphan" in capsys.readouterr().out

    def test_render_findings_empty(self, capsys: pytest.CaptureFixture[str]) -> None:
        rendering.render_findings([], empty="all good")
        assert "all good" in capsys.readouterr().out

    def test_render_error_to_stderr(self, capsys: pytest.CaptureFixture[str]) -> None:
        rendering.render_error({"message": "boom"})
        assert "boom" in capsys.readouterr().err

    def test_render_message(self, capsys: pytest.CaptureFixture[str]) -> None:
        rendering.render_message("hello")
        assert "hello" in capsys.readouterr().out

    def test_render_init_written(self, capsys: pytest.CaptureFixture[str]) -> None:
        rendering.render_init(
            {
                "home": "/x/.docir",
                "profiles": ["software"],
                "schema_written": True,
                "gitignore_written": True,
            }
        )
        assert "/x/.docir" in capsys.readouterr().out

    def test_render_init_kept_existing(self, capsys: pytest.CaptureFixture[str]) -> None:
        rendering.render_init(
            {
                "home": "/x/.docir",
                "profiles": ["software"],
                "schema_written": False,
                "gitignore_written": False,
            }
        )
        assert "kept existing" in capsys.readouterr().out

    def test_render_setup_created_and_updated(self, capsys: pytest.CaptureFixture[str]) -> None:
        rendering.render_setup(
            [
                {
                    "target": "claude",
                    "path": "/p",
                    "action": "updated",
                    "previous_version": "0.0.9",
                    "new_version": "0.1.0",
                    "note": "bumped",
                },
                {
                    "target": "agents",
                    "path": "/q",
                    "action": "created",
                    "previous_version": None,
                    "new_version": "0.1.0",
                    "note": None,
                },
            ]
        )
        out = capsys.readouterr().out
        assert "/p" in out and "0.0.9" in out and "bumped" in out

    def test_render_setup_unchanged_prints_no_version_arrow(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # `v0.14.0 → v0.16.0` beside a file whose content did not move is what
        # read as "your skill changed" after an upgrade that shipped nothing.
        rendering.render_setup(
            [
                {
                    "target": "claude",
                    "path": "/p",
                    "action": "unchanged",
                    "previous_version": "0.14.0",
                    "new_version": "0.16.0",
                    "note": None,
                }
            ]
        )
        out = capsys.readouterr().out
        assert "unchanged" in out and "0.16.0" in out
        assert "→" not in out and "0.14.0" not in out

    def test_render_setup_empty(self, capsys: pytest.CaptureFixture[str]) -> None:
        rendering.render_setup([])
        assert "nothing" in capsys.readouterr().out
