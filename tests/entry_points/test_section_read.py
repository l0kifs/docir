"""`get --section` / `docir_get(section=)` — the paired read for chunked ranking.

Chunking lets `context` rank a document on one of its sections. Without a way to
read that section, the agent's only follow-up is `get`, which returns a body
that on this project's own corpus runs to tens of thousands of characters — so
retrieval would get sharper while reading got no cheaper.

The contract that matters is agreement: `get --section X` returns exactly the
span `update --replace-section X` would overwrite. Two notions of "a section"
would mean an agent could read one thing and overwrite another.

They agree on the span and differ on one line inside it: the read returns the
heading, the write supplies it. Handing the read's output straight back therefore
wrote the heading twice, and nothing could remove the second
(issue-9d4db5cd5f29) — so the round trip is refused here, and `--remove-section`
is the exit for a body that already has one.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from typer.testing import CliRunner

from docir.config.settings import Settings
from docir.entry_points.cli.app import app
from docir.entry_points.composition import Container, InProcessExecutor
from docir.entry_points.mcp.server import build_mcp_server
from docir.modules.documents.api import describe_schema, load_schema

runner = CliRunner()

_BODY = """\
## Context

The provider authenticates us with mutual TLS and rotates on its own schedule.

## Decision

The client certificate is rotated at ten months, never later, inside the
provider's thirty-day overlap window.

### Rollback

There is none: rotation cannot be undone faster than the provider propagates it.

## Consequences

Rotation is a runbook step performed by two people rather than an automated job.
"""


@pytest.fixture(autouse=True)
def _env(settings: Settings) -> Settings:
    return settings


@pytest.fixture
def doc_id(container: Container) -> str:
    return container.dispatcher.dispatch(
        "add",
        {
            "type": "architecture",
            "title": "Provider integration",
            "description": "The provider boundary.",
            "body": _BODY,
        },
    )["id"]


class TestCli:
    def test_a_section_replaces_the_body(self, doc_id: str) -> None:
        result = runner.invoke(app, ["--no-daemon", "get", doc_id, "--section", "Decision"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["section"] == "Decision"
        assert payload["body"].startswith("## Decision")
        assert "ten months" in payload["body"]
        assert "runbook step" not in payload["body"], "the next section leaked in"

    def test_a_section_stops_at_the_next_heading_of_equal_depth(self, doc_id: str) -> None:
        """A deeper heading belongs to the section; a sibling ends it."""
        result = runner.invoke(app, ["--no-daemon", "get", doc_id, "--section", "Decision"])
        body = json.loads(result.stdout)["body"]
        assert "### Rollback" in body, "a nested subsection is part of its parent"
        assert "## Consequences" not in body

    def test_without_the_flag_the_whole_body_comes_back(self, doc_id: str) -> None:
        result = runner.invoke(app, ["--no-daemon", "get", doc_id])
        payload = json.loads(result.stdout)
        assert "Consequences" in payload["body"]
        # Absent rather than null: trimming drops it, and an agent reads a
        # missing `section` as "you have the whole thing".
        assert "section" not in payload

    def test_an_unknown_section_lists_the_real_ones(self, doc_id: str) -> None:
        """An agent must not have to fetch the body to learn the headings.

        That round trip is the cost this whole path exists to avoid, so the
        error carries the answer.
        """
        result = runner.invoke(app, ["--no-daemon", "get", doc_id, "--section", "Nope"])
        assert result.exit_code != 0
        combined = result.output + str(result.stderr or "")
        assert "Context" in combined and "Decision" in combined

    def test_the_heading_match_is_case_insensitive(self, doc_id: str) -> None:
        result = runner.invoke(app, ["--no-daemon", "get", doc_id, "--section", "dEcIsIoN"])
        assert result.exit_code == 0
        assert "ten months" in json.loads(result.stdout)["body"]


class TestAppendSectionRejectsItsOwnMarkers:
    """The corruption was silent, so the CLI must be where it is refused.

    Filed after an agent wrote `--append-section "## Resolution"` — composing
    the argument from the heading it had just read in a body, where it carries
    its `##` (issue-d5f68b44b1d9).
    """

    def test_the_command_fails_and_names_the_argument_that_works(self, doc_id: str) -> None:
        result = runner.invoke(
            app,
            ["--no-daemon", "update", doc_id, "--append-section", "## Resolution", "--body", "x"],
        )
        assert result.exit_code != 0
        combined = result.output + str(result.stderr or "")
        assert "Resolution" in combined

    def test_the_body_is_untouched(self, doc_id: str) -> None:
        runner.invoke(
            app,
            ["--no-daemon", "update", doc_id, "--append-section", "## Resolution", "--body", "x"],
        )
        body = json.loads(runner.invoke(app, ["--no-daemon", "get", doc_id]).stdout)["body"]
        assert "## ## Resolution" not in body
        assert "Resolution" not in body

    def test_the_bare_heading_still_appends(self, doc_id: str) -> None:
        result = runner.invoke(
            app,
            ["--no-daemon", "update", doc_id, "--append-section", "Resolution", "--body", "x"],
        )
        assert result.exit_code == 0, result.output
        body = json.loads(runner.invoke(app, ["--no-daemon", "get", doc_id]).stdout)["body"]
        assert body.rstrip().endswith("## Resolution\n\nx")


class TestAgreesWithReplaceSection:
    def test_read_and_write_span_the_same_text(self, container: Container, doc_id: str) -> None:
        """The load-bearing property: one notion of where a section ends.

        Reading `Decision` and then replacing `Decision` must touch the same
        lines. If they disagreed, an agent could read one span and overwrite a
        different one — silently, with no error anywhere.
        """
        dispatcher = container.dispatcher
        before = dispatcher.dispatch("get", {"doc_id": doc_id, "section": "Decision"})["body"]
        dispatcher.dispatch(
            "update",
            {"doc_id": doc_id, "replace_section": ["Decision", "Replaced entirely."]},
        )
        whole = dispatcher.dispatch("get", {"doc_id": doc_id})["body"]

        for line in before.splitlines():
            if line.strip() and not line.startswith("##"):
                assert line.strip() not in whole, f"replace_section left behind: {line!r}"
        assert "Replaced entirely." in whole
        assert "runbook step" in whole, "replace_section reached past the section"


class TestMcp:
    @pytest.fixture
    def server(self, container: Container, settings: Settings):
        return build_mcp_server(
            InProcessExecutor(container.dispatcher),
            describe_schema=lambda: describe_schema(load_schema(settings.schema_path)),
            version="0.0.0-test",
        )

    def _call(self, server, args: dict[str, Any]) -> Any:
        async def _session():
            async with Client(server) as client:
                return (await client.call_tool("docir_get", args)).data

        return asyncio.run(_session())

    def test_the_tool_takes_a_section(self, server, doc_id: str) -> None:
        payload = self._call(server, {"doc_id": doc_id, "section": "Consequences"})
        assert payload["section"] == "Consequences"
        assert "runbook step" in payload["body"]
        assert "ten months" not in payload["body"]

    def test_an_unknown_section_is_a_tool_error_naming_the_others(
        self, server, doc_id: str
    ) -> None:
        with pytest.raises(ToolError, match="Consequences"):
            self._call(server, {"doc_id": doc_id, "section": "Nope"})


class TestTheRoundTripIsRefusedRatherThanDuplicated:
    """Read a section, edit it, write it back — the flow the read path exists for.

    `get --section` returns the heading line and `--replace-section` writes its
    own, so passing one to the other spelled the heading twice; from there
    `--replace-section` matched the first and kept it, `--append-section` added
    a third, and only `--replace-body --force` could undo it
    (issue-9d4db5cd5f29).
    """

    def test_the_cli_refuses_the_text_it_just_returned(self, doc_id: str) -> None:
        read_back = json.loads(
            runner.invoke(app, ["--no-daemon", "get", doc_id, "--section", "Decision"]).stdout
        )["body"]
        assert read_back.startswith("## Decision"), "the read no longer returns the heading"

        result = runner.invoke(
            app,
            ["--no-daemon", "update", doc_id, "--replace-section", "Decision", "--body", read_back],
        )
        assert result.exit_code != 0
        combined = result.output + str(result.stderr or "")
        assert "--replace-section" in combined and "Decision" in combined

    def test_the_refused_edit_leaves_the_body_alone(self, doc_id: str) -> None:
        runner.invoke(
            app,
            [
                "--no-daemon",
                "update",
                doc_id,
                "--replace-section",
                "Decision",
                "--body",
                "## Decision\n\nrewritten",
            ],
        )
        body = json.loads(runner.invoke(app, ["--no-daemon", "get", doc_id]).stdout)["body"]
        assert body.count("## Decision") == 1
        assert "rewritten" not in body
        assert "ten months" in body

    def test_the_text_without_the_heading_writes(self, doc_id: str) -> None:
        result = runner.invoke(
            app,
            ["--no-daemon", "update", doc_id, "--replace-section", "Decision", "--body", "Rotated"],
        )
        assert result.exit_code == 0, result.output
        body = json.loads(runner.invoke(app, ["--no-daemon", "get", doc_id]).stdout)["body"]
        assert body.count("## Decision") == 1
        assert "Rotated" in body

    def test_the_mcp_tool_refuses_it_too(self, container: Container, settings: Settings) -> None:
        # The MCP surface is where flags have gone missing before, so the guard
        # is asserted on both transports rather than on the one that was easy.
        server = build_mcp_server(
            InProcessExecutor(container.dispatcher),
            describe_schema=lambda: describe_schema(load_schema(settings.schema_path)),
            version="0.0.0-test",
        )
        doc = container.dispatcher.dispatch(
            "add",
            {
                "type": "architecture",
                "title": "Provider integration",
                "description": "The provider boundary.",
                "body": _BODY,
            },
        )

        async def _session() -> Any:
            async with Client(server) as client:
                return (
                    await client.call_tool(
                        "docir_update",
                        {
                            "doc_id": doc["id"],
                            "replace_section": "Decision",
                            "body": "## Decision\n\nrewritten",
                        },
                    )
                ).data

        with pytest.raises(ToolError, match="Decision"):
            asyncio.run(_session())


class TestRemoveSection:
    """The exit from a body that already spells one heading twice.

    A hand edit can put one there at any time, and `--replace-section` cannot
    take it out: it keeps the first heading line by contract (issue-9d4db5cd5f29).
    """

    def test_the_cli_removes_a_heading_and_its_text(self, doc_id: str) -> None:
        result = runner.invoke(
            app, ["--no-daemon", "update", doc_id, "--remove-section", "Decision"]
        )
        assert result.exit_code == 0, result.output
        body = json.loads(runner.invoke(app, ["--no-daemon", "get", doc_id]).stdout)["body"]
        assert "## Decision" not in body
        assert "ten months" not in body
        assert "### Rollback" not in body, "a nested subsection belongs to its parent"
        assert "## Context" in body and "## Consequences" in body

    def test_a_hand_written_duplicate_is_repairable(self, doc_id: str) -> None:
        duplicated = "## Notes\n\n## Notes\n\nthe real text\n\n## Other\n\ntail\n"
        runner.invoke(
            app,
            ["--no-daemon", "update", doc_id, "--replace-body", "--force", "--body", duplicated],
        )
        result = runner.invoke(app, ["--no-daemon", "update", doc_id, "--remove-section", "Notes"])
        assert result.exit_code == 0, result.output
        body = json.loads(runner.invoke(app, ["--no-daemon", "get", doc_id]).stdout)["body"]
        assert body.count("## Notes") == 1
        assert "the real text" in body, "the surviving section kept its content"
        assert "tail" in body

    def test_it_is_a_body_edit_mode_like_the_others(self, doc_id: str) -> None:
        result = runner.invoke(
            app,
            [
                "--no-daemon",
                "update",
                doc_id,
                "--remove-section",
                "Decision",
                "--append-section",
                "Notes",
                "--body",
                "x",
            ],
        )
        assert result.exit_code != 0
        combined = result.output + str(result.stderr or "")
        assert "one body edit mode" in combined

    def test_a_body_passed_alongside_it_is_refused_not_ignored(self, doc_id: str) -> None:
        """`--remove-section X --body "..."` reads as "delete this text from X".

        It deletes the whole section instead and consumes nothing, so accepting
        it silently costs the caller a section they meant to keep
        (issue-9d4db5cd5f29).
        """
        result = runner.invoke(
            app,
            ["--no-daemon", "update", doc_id, "--remove-section", "Decision", "--body", "keep me"],
        )
        assert result.exit_code != 0
        combined = result.output + str(result.stderr or "")
        assert "--replace-section" in combined, "the error must name the mode that does take text"
        body = json.loads(runner.invoke(app, ["--no-daemon", "get", doc_id]).stdout)["body"]
        assert "## Decision" in body, "the refused edit removed the section anyway"

    def test_naming_a_writing_mode_too_blames_the_right_argument(self, doc_id: str) -> None:
        # Two modes plus a body is a different mistake; answering it with the
        # stray-text error would blame the argument that is doing its job.
        result = runner.invoke(
            app,
            [
                "--no-daemon",
                "update",
                doc_id,
                "--remove-section",
                "Decision",
                "--replace-section",
                "Context",
                "--body",
                "x",
            ],
        )
        assert result.exit_code != 0
        combined = result.output + str(result.stderr or "")
        assert "one body edit mode" in combined

    def test_blank_text_is_not_a_body(self, doc_id: str) -> None:
        # A shell expansion that produced nothing must not fail the removal.
        result = runner.invoke(
            app, ["--no-daemon", "update", doc_id, "--remove-section", "Decision", "--body", "  "]
        )
        assert result.exit_code == 0, result.output

    def test_the_mcp_tool_refuses_it_too(self, container: Container, settings: Settings) -> None:
        server = build_mcp_server(
            InProcessExecutor(container.dispatcher),
            describe_schema=lambda: describe_schema(load_schema(settings.schema_path)),
            version="0.0.0-test",
        )
        doc = container.dispatcher.dispatch(
            "add",
            {
                "type": "architecture",
                "title": "Provider integration",
                "description": "The provider boundary.",
                "body": _BODY,
            },
        )

        async def _session() -> Any:
            async with Client(server) as client:
                return (
                    await client.call_tool(
                        "docir_update",
                        {"doc_id": doc["id"], "remove_section": "Decision", "body": "keep me"},
                    )
                ).data

        with pytest.raises(ToolError, match="--replace-section"):
            asyncio.run(_session())

    def test_an_unknown_heading_lists_the_real_ones(self, doc_id: str) -> None:
        result = runner.invoke(app, ["--no-daemon", "update", doc_id, "--remove-section", "Nope"])
        assert result.exit_code != 0
        combined = result.output + str(result.stderr or "")
        assert "Context" in combined and "Decision" in combined

    def test_the_mcp_tool_removes_too(self, container: Container, settings: Settings) -> None:
        server = build_mcp_server(
            InProcessExecutor(container.dispatcher),
            describe_schema=lambda: describe_schema(load_schema(settings.schema_path)),
            version="0.0.0-test",
        )
        doc = container.dispatcher.dispatch(
            "add",
            {
                "type": "architecture",
                "title": "Provider integration",
                "description": "The provider boundary.",
                "body": _BODY,
            },
        )

        async def _session() -> Any:
            async with Client(server) as client:
                await client.call_tool(
                    "docir_update", {"doc_id": doc["id"], "remove_section": "Consequences"}
                )
                return (await client.call_tool("docir_get", {"doc_id": doc["id"]})).data

        body = asyncio.run(_session())["body"]
        assert "## Consequences" not in body
        assert "runbook step" not in body
        assert "## Decision" in body
