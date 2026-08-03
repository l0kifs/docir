"""`get --section` / `docir_get(section=)` — the paired read for chunked ranking.

Chunking lets `context` rank a document on one of its sections. Without a way to
read that section, the agent's only follow-up is `get`, which returns a body
that on this project's own corpus runs to tens of thousands of characters — so
retrieval would get sharper while reading got no cheaper.

The contract that matters is agreement: `get --section X` returns exactly the
span `update --replace-section X` would overwrite. Two notions of "a section"
would mean an agent could read one thing and overwrite another.
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
