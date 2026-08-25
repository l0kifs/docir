"""`docir get a b c` / `docir_get(doc_ids=)` — the deep read, batched.

A docir read is dominated by starting the process rather than by retrieval
(issue-9509f9fa3631): five `get` calls are five interpreters, and over MCP they
are five model turns. So an agent that has just ranked five documents pays five
times for the first one. This path lets it ask once.

Two properties carry the design and both are asserted here. The **shape follows
the key**: `doc_id` still answers with the document, `doc_ids` answers with an
envelope even for one id, so nothing has to branch on how many results came
back. And a reference that does not resolve is **data, not an error** — the
deleted id must not cost the caller the four documents that did resolve — while
a *malformed* one still raises, because that is the caller's own typo.
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
from docir.entry_points.dispatch import Dispatcher
from docir.entry_points.mcp.server import build_mcp_server
from docir.modules.documents.api import describe_schema, load_schema
from docir.platform.errors import DocirError, ValidationError

runner = CliRunner()

_ALPHA_BODY = """\
## Context

Alpha runs behind the shared gateway.

## Decision

Alpha keeps its own rate limiter.
"""

_BETA_BODY = """\
## Context

Beta reads Alpha's queue.

## Decision

Beta retries with jitter.
"""


@pytest.fixture(autouse=True)
def _env(settings: Settings) -> Settings:
    return settings


def _add(dispatcher: Dispatcher, title: str, body: str) -> str:
    added = dispatcher.dispatch(
        "add",
        {
            "type": "architecture",
            "title": title,
            "description": f"{title} boundary.",
            "body": body,
        },
    )
    assert isinstance(added, dict)
    return str(added["id"])


@pytest.fixture
def alpha(container: Container) -> str:
    return _add(container.dispatcher, "Alpha service", _ALPHA_BODY)


@pytest.fixture
def beta(container: Container) -> str:
    return _add(container.dispatcher, "Beta service", _BETA_BODY)


class TestTheShapeFollowsTheKey:
    def test_doc_id_still_answers_with_the_document(self, container: Container, alpha: str) -> None:
        """The existing contract, unchanged — `docir build`, saved prompts and
        every agent that already learned `get` depend on it."""
        payload = container.dispatcher.dispatch("get", {"doc_id": alpha})
        assert isinstance(payload, dict)
        assert payload["id"] == alpha
        assert "documents" not in payload

    def test_doc_ids_answers_with_an_envelope_even_for_one(
        self, container: Container, alpha: str
    ) -> None:
        """Asking in the plural gets the plural shape.

        Deciding by the *count* would make a caller that batches unpredictably
        branch on how many results came back, which is the ambiguity this rule
        exists to remove.
        """
        payload = container.dispatcher.dispatch("get", {"doc_ids": [alpha]})
        assert isinstance(payload, dict)
        assert [doc["id"] for doc in payload["documents"]] == [alpha]
        assert payload["missing"] == ()

    def test_both_keys_at_once_is_refused(self, container: Container, alpha: str) -> None:
        with pytest.raises(ValidationError, match="not both"):
            container.dispatcher.dispatch("get", {"doc_id": alpha, "doc_ids": [alpha]})

    def test_section_with_doc_ids_names_the_form_that_works(
        self, container: Container, alpha: str
    ) -> None:
        """Silently ignoring the flag would return whole bodies and report success."""
        with pytest.raises(ValidationError, match="#<heading>"):
            container.dispatcher.dispatch("get", {"doc_ids": [alpha], "section": "Decision"})


class TestItReadsWhatTheSingleGetWouldHave:
    def test_the_batched_view_is_the_single_view(
        self, container: Container, alpha: str, beta: str
    ) -> None:
        """The load-bearing property: one projection of the aggregate.

        A batch that assembled its own view would drop a field only when you
        asked for two documents — invisible to every single-document test.
        """
        dispatcher = container.dispatcher
        singles = [dispatcher.dispatch("get", {"doc_id": doc}) for doc in (alpha, beta)]
        batch = dispatcher.dispatch("get", {"doc_ids": [alpha, beta]})
        assert isinstance(batch, dict)
        assert list(batch["documents"]) == singles

    def test_an_address_may_name_a_section(self, container: Container, alpha: str) -> None:
        payload = container.dispatcher.dispatch("get", {"doc_ids": [f"{alpha}#Decision"]})
        assert isinstance(payload, dict)
        (document,) = payload["documents"]
        assert document["section"] == "Decision"
        assert "rate limiter" in document["body"]
        assert "shared gateway" not in document["body"], "the other section leaked in"

    def test_one_document_under_two_headings_is_two_answers(
        self, container: Container, alpha: str
    ) -> None:
        payload = container.dispatcher.dispatch(
            "get", {"doc_ids": [f"{alpha}#Context", f"{alpha}#Decision"]}
        )
        assert isinstance(payload, dict)
        assert [doc["section"] for doc in payload["documents"]] == ["Context", "Decision"]

    def test_the_same_address_twice_is_one_answer(self, container: Container, alpha: str) -> None:
        """Bodies are the expensive half of a deep read; paying twice for the
        identical span is never what was meant."""
        payload = container.dispatcher.dispatch("get", {"doc_ids": [alpha, alpha]})
        assert isinstance(payload, dict)
        assert len(payload["documents"]) == 1

    def test_the_order_asked_for_is_the_order_returned(
        self, container: Container, alpha: str, beta: str
    ) -> None:
        payload = container.dispatcher.dispatch("get", {"doc_ids": [beta, alpha]})
        assert isinstance(payload, dict)
        assert [doc["id"] for doc in payload["documents"]] == [beta, alpha]


class TestAMissIsDataAndATypoIsNot:
    def test_a_deleted_id_does_not_cost_the_others(
        self, container: Container, alpha: str, beta: str
    ) -> None:
        payload = container.dispatcher.dispatch("get", {"doc_ids": [alpha, "adr-nope", beta]})
        assert isinstance(payload, dict)
        assert [doc["id"] for doc in payload["documents"]] == [alpha, beta]
        assert [entry["ref"] for entry in payload["missing"]] == ["adr-nope"]

    def test_the_miss_carries_the_error_it_would_have_raised_alone(
        self, container: Container
    ) -> None:
        payload = container.dispatcher.dispatch("get", {"doc_ids": ["adr-nope"]})
        assert isinstance(payload, dict)
        (entry,) = payload["missing"]
        assert "no document with id" in entry["error"]

    def test_an_unknown_heading_misses_and_still_lists_the_real_ones(
        self, container: Container, alpha: str
    ) -> None:
        """The section error's whole value is the heading list; losing it in a
        batch would send the agent back for the body it was avoiding."""
        payload = container.dispatcher.dispatch("get", {"doc_ids": [f"{alpha}#Nope"]})
        assert isinstance(payload, dict)
        (entry,) = payload["missing"]
        assert entry["ref"] == f"{alpha}#Nope"
        assert "Context" in entry["error"] and "Decision" in entry["error"]

    def test_a_malformed_address_raises(self, container: Container, alpha: str) -> None:
        """A typo is the caller's, not the corpus's — reporting it beside the
        results would let a mistyped id read as a deleted document."""
        with pytest.raises(DocirError):
            container.dispatcher.dispatch("get", {"doc_ids": [alpha, "#Decision"]})

    def test_an_empty_list_raises(self, container: Container) -> None:
        with pytest.raises(ValidationError, match="at least one"):
            container.dispatcher.dispatch("get", {"doc_ids": []})


class TestCli:
    def test_several_ids_return_the_envelope(self, alpha: str, beta: str) -> None:
        result = runner.invoke(app, ["--no-daemon", "get", alpha, beta])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert [doc["id"] for doc in payload["documents"]] == [alpha, beta]
        assert all(doc["body"] for doc in payload["documents"])

    def test_one_id_returns_the_document(self, alpha: str) -> None:
        result = runner.invoke(app, ["--no-daemon", "get", alpha])
        assert json.loads(result.stdout)["id"] == alpha

    def test_the_hash_form_reads_a_section(self, alpha: str, beta: str) -> None:
        result = runner.invoke(app, ["--no-daemon", "get", f"{alpha}#Decision", beta])
        payload = json.loads(result.stdout)
        assert payload["documents"][0]["section"] == "Decision"
        assert "section" not in payload["documents"][1]

    def test_the_hash_form_works_for_one_id_too(self, alpha: str) -> None:
        """One grammar, parsed in one place — a single id must not need --section."""
        result = runner.invoke(app, ["--no-daemon", "get", f"{alpha}#Decision"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["section"] == "Decision"

    def test_both_spellings_at_once_is_refused(self, alpha: str) -> None:
        result = runner.invoke(
            app, ["--no-daemon", "get", f"{alpha}#Decision", "--section", "Context"]
        )
        assert result.exit_code != 0
        assert "drop --section" in result.output + str(result.stderr or "")

    def test_section_with_several_ids_names_the_form_that_works(
        self, alpha: str, beta: str
    ) -> None:
        result = runner.invoke(app, ["--no-daemon", "get", alpha, beta, "--section", "Decision"])
        assert result.exit_code != 0
        assert "#<heading>" in result.output + str(result.stderr or "")

    def test_a_miss_does_not_fail_the_command(self, alpha: str) -> None:
        """The request was answered; `missing` is the answer's other half.

        Exiting non-zero here would make a partial read indistinguishable from
        a store that could not be opened.
        """
        result = runner.invoke(app, ["--no-daemon", "get", alpha, "adr-nope"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert [doc["id"] for doc in payload["documents"]] == [alpha]
        assert [entry["ref"] for entry in payload["missing"]] == ["adr-nope"]

    def test_no_ids_at_all_is_an_error(self) -> None:
        result = runner.invoke(app, ["--no-daemon", "get"])
        assert result.exit_code != 0

    def test_the_human_view_reports_the_misses_on_stderr(self, alpha: str) -> None:
        """Stdout carries what was read; a miss noticed only by counting panels
        is a miss nobody notices."""
        result = runner.invoke(app, ["--pretty", "--no-daemon", "get", alpha, "adr-nope"])
        assert result.exit_code == 0, result.output
        assert "adr-nope" in str(result.stderr or "")


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

    def test_doc_ids_reaches_the_dispatcher(self, server, alpha: str, beta: str) -> None:
        """The flag existed on the CLI and reached no tool twice before
        (adr-f14682e3f4d6); the transports are checked separately for that reason."""
        payload = self._call(server, {"doc_ids": [alpha, beta]})
        assert [doc["id"] for doc in payload["documents"]] == [alpha, beta]

    def test_the_hash_form_survives_the_wire(self, server, alpha: str) -> None:
        payload = self._call(server, {"doc_ids": [f"{alpha}#Decision"]})
        assert payload["documents"][0]["section"] == "Decision"

    def test_a_miss_is_reported_rather_than_raised(self, server, alpha: str) -> None:
        payload = self._call(server, {"doc_ids": [alpha, "adr-nope"]})
        assert len(payload["documents"]) == 1
        assert payload["missing"][0]["ref"] == "adr-nope"

    def test_doc_id_alone_still_answers_with_the_document(self, server, alpha: str) -> None:
        assert self._call(server, {"doc_id": alpha})["id"] == alpha

    def test_a_malformed_address_is_a_tool_error(self, server) -> None:
        with pytest.raises(ToolError):
            self._call(server, {"doc_ids": ["#Decision"]})

    def test_an_empty_batch_is_trimmed_to_the_half_that_has_content(
        self, server, alpha: str
    ) -> None:
        """`trim` drops empty collections, so `missing` is absent when nothing
        missed — the same convention every other docir payload follows."""
        payload = self._call(server, {"doc_ids": [alpha]})
        assert "missing" not in payload
