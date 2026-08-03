"""The rendered HTML — what actually reaches a browser.

Assertions are on content and structure, not on exact markup: the CSS will
change, the guarantees will not. The two that matter most are that the site is
offline-complete (no external request can fail or leak) and that interpolated
text is escaped (a document is untrusted input to the renderer even though it
came from the store).
"""

from __future__ import annotations

import re

from docir.modules.publishing.api import PublishRequest, build_site, build_site_builder
from docir.modules.publishing.infra.rendering import render_site

_DOCS = [
    {
        "id": "adr-0001",
        "title": "Old way",
        "description": "Previous.",
        "type": "decision",
        "status": "superseded",
        "created": "2026-01-01",
        "updated": "2026-01-02",
        "body": "## Context\n\nThe old approach with `code` and a [link](https://x.test).\n",
    },
    {
        "id": "adr-0002",
        "title": "New way",
        "description": "Replacement.",
        "type": "decision",
        "status": "accepted",
        "created": "2026-02-01",
        "updated": "2026-02-01",
        "body": "Body.",
        "related": [{"target": "adr-0001", "kind": "supersedes"}],
        "stale": True,
    },
]


def _pages() -> dict[str, str]:
    return render_site(build_site(_DOCS), title="Docs", version="1.2.3")


class TestStructure:
    def test_one_page_per_document_plus_an_index(self) -> None:
        pages = _pages()
        assert set(pages) == {"index.html", "adr-0001.html", "adr-0002.html"}

    def test_the_index_links_every_document(self) -> None:
        index = _pages()["index.html"]
        assert 'href="adr-0001.html"' in index
        assert 'href="adr-0002.html"' in index

    def test_the_body_is_rendered_as_markdown(self) -> None:
        page = _pages()["adr-0001.html"]
        assert 'id="context">Context' in page
        assert "<code>code</code>" in page
        assert "&#35;&#35; Context" not in page

    def test_both_edge_directions_are_shown(self) -> None:
        """No other ADR site renders the inbound half."""
        old = _pages()["adr-0001.html"]
        assert "Linked from" in old
        assert 'href="adr-0002.html"' in old
        new = _pages()["adr-0002.html"]
        assert "Links to" in new
        assert 'href="adr-0001.html"' in new

    def test_a_superseded_document_says_so_before_its_body(self) -> None:
        """The one thing a reader of an old decision must not miss."""
        old = _pages()["adr-0001.html"]
        banner = old.index("Not the last word")
        assert banner < old.index('<div class="body">')
        assert "New way" in old[banner : banner + 400]

    def test_staleness_is_visible_on_the_index(self) -> None:
        index = _pages()["index.html"]
        assert "past their review cadence" in index
        assert 'class="chip stale"' in index


class TestSelfContained:
    def test_the_renderer_adds_no_external_subresource(self) -> None:
        """A published site must work from file:// and behind a locked-down host.

        Also a privacy property: a page that fetches a font tells someone else
        who is reading your architecture decisions.

        Subresources only — a stylesheet, a script, an image. An `<a href>` to
        the web is the *document author's* link and must survive: this checks
        what the renderer brings, not what a body says.
        """
        for name, page in _pages().items():
            assert not re.search(r'<link[^>]+href="(?!data:)', page), f"{name} pulls a stylesheet"
            assert not re.search(r"<script[^>]+src=", page), f"{name} pulls a script"
            assert not re.search(r"<img[^>]+src=\"https?://", page), f"{name} pulls an image"

    def test_an_authored_link_survives(self) -> None:
        """The other half of the same rule: content links are not the renderer's."""
        assert 'href="https://x.test"' in _pages()["adr-0001.html"]

    def test_styles_are_inlined(self) -> None:
        assert "<style>" in _pages()["index.html"]


class TestEscaping:
    def test_titles_are_escaped_not_rendered(self) -> None:
        """A title is text. A document titled `<script>` is a title, not a script."""
        pages = render_site(
            build_site(
                [
                    dict(
                        _DOCS[0],
                        title="<script>alert(1)</script>",
                        description="a & b",
                    )
                ]
            ),
            title="Docs",
            version="1",
        )
        page = pages["adr-0001.html"]
        assert "<script>alert(1)</script>" not in page.replace("<script>const rows", ""), (
            "the title was emitted as markup"
        )
        assert "&lt;script&gt;" in page
        assert "a &amp; b" in page


class TestWriting:
    def test_it_writes_the_files_and_reports_them(self, tmp_path) -> None:
        result = build_site_builder().build(
            PublishRequest(out=tmp_path / "site", documents=_DOCS, title="Docs", version="1")
        )
        assert result.documents == 2
        assert result.stale == 1
        assert (tmp_path / "site" / "index.html").exists()
        assert (tmp_path / "site" / "search-index.json").exists()

    def test_a_rebuild_removes_pages_for_deleted_documents(self, tmp_path) -> None:
        """The site is derived: a deleted document must not survive as a page.

        Without the sweep, a corpus that shrinks publishes a page nobody can
        reach from the index and nobody knows is stale — the web equivalent of
        an index row whose file is gone.
        """
        out = tmp_path / "site"
        builder = build_site_builder()
        builder.build(PublishRequest(out=out, documents=_DOCS, version="1"))
        assert (out / "adr-0002.html").exists()

        builder.build(PublishRequest(out=out, documents=_DOCS[:1], version="1"))
        assert not (out / "adr-0002.html").exists()
        assert (out / "adr-0001.html").exists()

    def test_it_refuses_a_directory_it_did_not_build(self, tmp_path) -> None:
        """`--out` is a path a person types, and it regenerates what it finds."""
        import pytest

        from docir.platform.errors import DocirError

        out = tmp_path / "src"
        out.mkdir()
        (out / "important.py").write_text("# not a site", encoding="utf-8")

        with pytest.raises(DocirError, match="not empty"):
            build_site_builder().build(PublishRequest(out=out, documents=_DOCS, version="1"))
        assert (out / "important.py").exists()

    def test_force_overwrites_it(self, tmp_path) -> None:
        out = tmp_path / "src"
        out.mkdir()
        (out / "important.py").write_text("# not a site", encoding="utf-8")
        result = build_site_builder().build(
            PublishRequest(out=out, documents=_DOCS, version="1", force=True)
        )
        assert result.documents == 2

    def test_an_empty_directory_is_fine(self, tmp_path) -> None:
        out = tmp_path / "site"
        out.mkdir()
        assert (
            build_site_builder()
            .build(PublishRequest(out=out, documents=_DOCS, version="1"))
            .documents
            == 2
        )


class TestReadability:
    """Fixes that came from opening the site in a browser, not from the markup.

    Each of these was a real defect found at a real viewport; without a test
    they are one refactor away from coming back, and none of them would fail
    anything else in the suite.
    """

    def test_a_body_repeating_the_title_does_not_print_it_twice(self) -> None:
        """docir's own convention restates the title as the body's first line.

        Published, that was the title twice — and the second one *larger*,
        because a body `h1` outranks the page heading.
        """
        pages = render_site(
            build_site([dict(_DOCS[0], body="# Old way\n\nThe body proper.\n")]),
            title="Docs",
            version="1",
        )
        # Exactly one h1 per page: the header's. The body's repeat is gone.
        # (Counting the text would also match <title>, which is correct there.)
        assert pages["adr-0001.html"].count("<h1") == 1

    def test_a_body_heading_that_is_not_the_title_survives(self) -> None:
        """Only the *repeat* is dropped; a real first heading is content."""
        pages = render_site(
            build_site([dict(_DOCS[0], body="# Something else\n\nBody.\n")]),
            title="Docs",
            version="1",
        )
        page = pages["adr-0001.html"]
        assert ">Something else" in page
        assert page.count("<h1") == 2, "the header's and the body's own"

    def test_headings_are_addressable(self) -> None:
        """The site's answer to `get --section`: a link to one section."""
        body = "\n".join(f"## Section {n}\n\nText for {n}.\n" for n in range(1, 5))
        pages = render_site(build_site([dict(_DOCS[0], body=body)]), title="Docs", version="1")
        page = pages["adr-0001.html"]
        assert 'id="section-1"' in page
        assert 'href="#section-1"' in page, "no anchor to link the section with"

    def test_repeated_headings_get_distinct_ids(self) -> None:
        """Two sections called Context is normal; two links to one is not."""
        body = "## Context\n\nA.\n\n## Decision\n\nB.\n\n## Context\n\nC.\n"
        pages = render_site(build_site([dict(_DOCS[0], body=body)]), title="Docs", version="1")
        page = pages["adr-0001.html"]
        assert 'id="context"' in page and 'id="context-1"' in page

    def test_a_long_document_gets_a_table_of_contents(self) -> None:
        body = "\n".join(f"## Section {n}\n\nText.\n" for n in range(1, 6))
        page = render_site(build_site([dict(_DOCS[0], body=body)]), title="Docs", version="1")[
            "adr-0001.html"
        ]
        assert "Contents" in page
        assert page.index("Contents") < page.index('<div class="body">')

    def test_a_short_document_gets_none(self) -> None:
        """Two links above a short body are furniture, not navigation."""
        page = render_site(
            build_site([dict(_DOCS[0], body="## One\n\nText.\n")]), title="Docs", version="1"
        )["adr-0001.html"]
        assert "Contents" not in page

    def test_relations_sit_above_the_body(self) -> None:
        """They were 4,068px down a 4,596px page — present and invisible."""
        page = _pages()["adr-0002.html"]
        assert page.index("Links to") < page.index('<div class="body">')

    def test_type_status_and_tags_are_visually_distinct(self) -> None:
        """One page read `architecture · active · architecture · persistence`.

        Three different kinds of fact rendered as three identical grey pills,
        with the same word meaning a type in one and a tag in the next.
        """
        page = render_site(
            build_site([dict(_DOCS[0], tags=["decision", "auth"])]),
            title="Docs",
            version="1",
        )["adr-0001.html"]
        assert 'class="chip type"' in page
        assert 'class="chip status"' in page
        assert 'class="chip tag"' in page
        # The type is `decision` and so is one of the tags; they must not read
        # the same, which is exactly the case that exposed this.
        assert ">#decision<" in page, "a tag is not marked as one"

    def test_the_index_does_not_repeat_its_own_count(self) -> None:
        """It read "105 documents · 105 of 105" until you typed something."""
        index = _pages()["index.html"]
        assert "2 documents" in index
        assert "2 of 2" not in index

    def test_the_index_reflows_instead_of_scrolling_sideways(self) -> None:
        """A four-column table needed 426px at a 390px viewport.

        Asserting on the mechanism rather than on pixels: a grid list with a
        single-column breakpoint cannot overflow the way the table did.
        """
        index = _pages()["index.html"]
        assert "<table" not in index
        assert "grid-template-columns:1fr}" in index, "no single-column breakpoint"

    def test_the_favicon_request_is_answered_without_a_network_call(self) -> None:
        """Browsers ask for /favicon.ico on every page and log a 404 without it."""
        assert 'rel="icon" href="data:,"' in _pages()["index.html"]

    def test_a_long_relation_list_starts_collapsed(self) -> None:
        """Moving relations up buried the document under its own graph.

        docir's architecture document has 21 inbound edges; expanded above the
        body they filled the entire first screen. The count stays visible
        without a click, which is the part that was missing when they were at
        the bottom.
        """
        many = [dict(_DOCS[0])] + [
            {
                "id": f"adr-1{n:03d}",
                "title": f"Linker {n}",
                "description": "d",
                "type": "decision",
                "status": "accepted",
                "created": "2026-03-01",
                "updated": "2026-03-01",
                "body": "b",
                "related": [{"target": "adr-0001", "kind": "relates_to"}],
            }
            for n in range(9)
        ]
        page = render_site(build_site(many), title="Docs", version="1")["adr-0001.html"]
        assert '<details class="panel">' in page, "a 9-item list should be collapsed"
        assert ">9</span></summary>" in page, "the count must be legible without expanding"

    def test_a_short_relation_list_stays_open(self) -> None:
        """Two links are context, not clutter — hiding them costs a click."""
        page = _pages()["adr-0002.html"]
        assert '<details class="panel" open>' in page
