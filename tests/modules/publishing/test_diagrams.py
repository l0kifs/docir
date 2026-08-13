"""Mermaid fences: drawn when a runtime is supplied, readable when it is not.

The two properties worth pinning are the ones that are easy to lose by
accident. A site must stay offline-complete — the runtime is written beside
the pages and referenced relatively, never fetched — and a build without
``--mermaid`` must publish the diagram's *source* rather than an empty box,
because a page whose script did not load should be no worse than the code
block it replaced.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pytest

from docir.modules.publishing.api import PublishRequest, build_site, build_site_builder
from docir.modules.publishing.infra import diagrams
from docir.modules.publishing.infra.rendering import render_site
from docir.platform.errors import ValidationError

_FLOW = "graph TD\n  A[Write] --> B[Index]\n"

_DOCS = [
    {
        "id": "arch-0001",
        "title": "The pipeline",
        "description": "How a write reaches the index.",
        "type": "architecture",
        "status": "active",
        "body": f"## Shape\n\n```mermaid\n{_FLOW}```\n",
    },
    {
        "id": "adr-0001",
        "title": "No diagram here",
        "description": "Prose only.",
        "type": "decision",
        "status": "accepted",
        "body": "## Context\n\n```python\nx = 1\n```\n",
    },
]

#: Enough of a bundle to be a plausible file; the tests never execute it.
_RUNTIME = "window.mermaid={initialize(){},run(){return Promise.resolve()}};\n"


def _pages(runtime: str | None = None) -> dict[str, str]:
    return render_site(build_site(_DOCS), title="Docs", version="1.2.3", runtime=runtime)


class TestFenceRendering:
    def test_a_mermaid_fence_becomes_a_figure_not_a_code_block(self) -> None:
        page = _pages()["arch-0001.html"]
        assert '<figure class="diagram">' in page
        assert f'<div class="{diagrams.DIAGRAM_CLASS}">' in page
        # The python fence on the other page still gets the code-block frame:
        # only mermaid is diverted.
        assert '<div class="codeblk">' in _pages()["adr-0001.html"]

    def test_the_source_survives_as_the_element_text(self) -> None:
        """The unrendered state is the fallback *and* the input the bootstrap
        captures, so losing it breaks both at once. Asserted *inside* the
        diagram element: the source appearing somewhere on the page is what a
        plain code block already does."""
        page = _pages()["arch-0001.html"]
        drawn = page.split(f'<div class="{diagrams.DIAGRAM_CLASS}">')[1].split("</div>")[0]
        assert drawn == "graph TD\n  A[Write] --&gt; B[Index]\n"

    def test_the_copy_button_carries_the_source_itself(self) -> None:
        """Once drawn, the element holds an <svg>; a button that read what it
        found would hand back serialized markup instead of mermaid."""
        page = _pages()["arch-0001.html"]
        assert 'data-copy="graph TD' in page

    def test_a_source_that_looks_like_markup_cannot_escape_the_page(self) -> None:
        docs = [{**_DOCS[0], "body": '```mermaid\ngraph TD\n  A["</script><b>x"] --> B\n```\n'}]
        page = render_site(build_site(docs), title="Docs", version="1")["arch-0001.html"]
        assert "</script><b>" not in page
        assert "&lt;/script&gt;" in page


class TestRuntimeWiring:
    def test_without_a_runtime_nothing_references_one(self) -> None:
        pages = _pages()
        assert diagrams.RUNTIME_FILE not in pages
        assert all(diagrams.RUNTIME_FILE not in page for page in pages.values())

    def test_the_runtime_is_published_and_loaded_relatively(self) -> None:
        pages = _pages(_RUNTIME)
        assert pages[diagrams.RUNTIME_FILE] == _RUNTIME
        assert f'<script src="{diagrams.RUNTIME_FILE}"></script>' in pages["arch-0001.html"]
        # Offline-complete: the only script sources on the page are relative.
        assert "http://" not in pages["arch-0001.html"]
        assert "https://" not in pages["arch-0001.html"]

    def test_only_the_pages_with_a_diagram_load_it(self) -> None:
        """The bundle is megabytes. A page with no diagram must not pay for it,
        and neither must the index or the graph."""
        pages = _pages(_RUNTIME)
        loaded = {
            name
            for name, page in pages.items()
            if name.endswith(".html") and diagrams.RUNTIME_FILE in page
        }
        assert loaded == {"arch-0001.html"}

    def test_a_corpus_with_no_diagrams_publishes_no_runtime(self) -> None:
        """Supplying --mermaid to a store that draws nothing should not write a
        megabyte of JavaScript nobody loads."""
        pages = render_site(build_site([_DOCS[1]]), title="Docs", version="1", runtime=_RUNTIME)
        assert diagrams.RUNTIME_FILE not in pages


class TestRuntimeValidation:
    def test_a_non_javascript_path_is_refused_by_name(self) -> None:
        with pytest.raises(ValidationError, match="browser build"):
            diagrams.resolve_runtime(Path("mermaid.tar.gz"))

    def test_a_missing_file_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(ValidationError, match="not found"):
            diagrams.resolve_runtime(tmp_path / "mermaid.min.js")

    def test_an_empty_file_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "mermaid.min.js"
        path.write_text("")
        with pytest.raises(ValidationError, match="empty"):
            diagrams.resolve_runtime(path)

    def test_an_oversized_file_is_refused_with_the_limit(self, tmp_path: Path) -> None:
        path = tmp_path / "mermaid.min.js"
        path.write_bytes(b"x" * (diagrams.MAX_RUNTIME_BYTES + 1))
        with pytest.raises(ValidationError, match="the limit is"):
            diagrams.resolve_runtime(path)

    def test_absent_is_not_an_error(self) -> None:
        assert diagrams.resolve_runtime(None) is None


class TestBuildIntegration:
    def test_the_runtime_lands_in_the_output_directory(self, tmp_path: Path) -> None:
        runtime = tmp_path / "mermaid.min.js"
        runtime.write_text(_RUNTIME)
        out = tmp_path / "site"
        result = build_site_builder().build(
            PublishRequest(out=out, documents=_DOCS, mermaid=runtime)
        )
        assert diagrams.RUNTIME_FILE in result.files
        assert (out / diagrams.RUNTIME_FILE).read_text() == _RUNTIME

    def test_a_rebuild_without_the_flag_sweeps_the_stale_runtime(self, tmp_path: Path) -> None:
        """The site is regenerated wholesale. A runtime left behind after the
        build stopped being given one is an orphan exactly like a deleted
        document's page."""
        runtime = tmp_path / "mermaid.min.js"
        runtime.write_text(_RUNTIME)
        out = tmp_path / "site"
        builder = build_site_builder()
        builder.build(PublishRequest(out=out, documents=_DOCS, mermaid=runtime))
        assert (out / diagrams.RUNTIME_FILE).exists()
        builder.build(PublishRequest(out=out, documents=_DOCS))
        assert not (out / diagrams.RUNTIME_FILE).exists()

    def test_a_bad_runtime_fails_before_the_directory_is_emptied(self, tmp_path: Path) -> None:
        """Same guarantee the logo has: a mistyped path must not cost the
        previous build."""
        out = tmp_path / "site"
        builder = build_site_builder()
        builder.build(PublishRequest(out=out, documents=_DOCS))
        with pytest.raises(ValidationError):
            builder.build(PublishRequest(out=out, documents=_DOCS, mermaid=tmp_path / "missing.js"))
        assert (out / "arch-0001.html").exists()


class TestProseIsNotADiagram:
    """Found by building docir's own site: two of its documents *write about*
    this feature, so the runtime's filename and the marker class both appear in
    ordinary prose. A substring check on either one publishes megabytes of
    JavaScript for a corpus that draws nothing."""

    _WRITES_ABOUT_IT: ClassVar[dict[str, str]] = {
        "id": "adr-0002",
        "title": "The mermaid runtime is a build input",
        "description": "Why docir does not vendor the bundle.",
        "type": "decision",
        "status": "accepted",
        "body": (
            "## Decision\n\n"
            "Point `--mermaid` at mermaid.min.js. The element carries the\n"
            "`docir-mermaid` class and the page loads mermaid.min.js beside it.\n"
        ),
    }

    def test_a_document_about_diagrams_publishes_no_runtime(self) -> None:
        pages = render_site(
            build_site([self._WRITES_ABOUT_IT]), title="Docs", version="1", runtime=_RUNTIME
        )
        assert diagrams.RUNTIME_FILE not in pages

    def test_and_its_page_does_not_load_one(self) -> None:
        pages = render_site(
            build_site([_DOCS[0], self._WRITES_ABOUT_IT]),
            title="Docs",
            version="1",
            runtime=_RUNTIME,
        )
        # The real diagram still gets it; the document describing it does not.
        assert diagrams.loads_runtime(pages["arch-0001.html"])
        assert not diagrams.loads_runtime(pages["adr-0002.html"])
