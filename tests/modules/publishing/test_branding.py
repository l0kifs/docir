"""The site's mark — docir's own by default, the publisher's on request.

The geometry test is the one that matters over time: the mark is inlined as a
Python constant so the renderer touches no files, and `assets/logo/` stays the
source of truth for the art. Nothing but this test connects the two.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path

import pytest

from docir.modules.publishing.api import PublishRequest, build_site, build_site_builder
from docir.modules.publishing.infra.branding import (
    DOCIR_MARK,
    MAX_LOGO_BYTES,
    resolve_branding,
)
from docir.modules.publishing.infra.rendering import render_site
from docir.platform.errors import ValidationError

_REPO = Path(__file__).resolve().parents[3]
_KIT = _REPO / "assets" / "logo"

#: A 1x1 transparent GIF — the smallest real image file, so the encoding tests
#: assert on encoding rather than on a fixture.
_TINY_GIF = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")

_DOCS = [
    {
        "id": "adr-0001",
        "title": "A decision",
        "description": "d",
        "type": "decision",
        "status": "accepted",
        "created": "2026-01-01",
        "updated": "2026-01-02",
        "body": "## Context\n\nText.\n",
    }
]


def _paths(svg: str) -> list[str]:
    return re.findall(r'\sd="([^"]+)"', svg)


def _decoded_favicon(pages: dict[str, str]) -> str:
    """The favicon's SVG source, back out of the page's data: URI."""
    match = re.search(
        r'<link rel="icon" href="data:image/svg\+xml;base64,([^"]+)">', pages["index.html"]
    )
    assert match, "the index carries no SVG favicon"
    return base64.b64decode(match.group(1)).decode("utf-8")


class TestTheDocirMark:
    def test_the_geometry_matches_the_logo_kit(self) -> None:
        """The constant is a copy of `assets/logo/docir-mark.svg`, which is the
        art's source of truth. Nothing else notices if the two diverge — the
        site would simply draw last year's logo forever."""
        kit = (_KIT / "docir-mark.svg").read_text(encoding="utf-8")
        assert _paths(DOCIR_MARK) == _paths(kit), "the mark drifted from the logo kit"
        assert 'viewBox="0 0 48 48"' in DOCIR_MARK

    def test_the_bracket_follows_the_theme_and_the_caret_does_not(self) -> None:
        """The kit ships an ink mark and a paper one; against the header's own
        colour those collapse into one. The caret keeps signal amber fixed —
        per the kit, amber is only ever the caret, never decoration."""
        assert 'stroke="currentColor"' in DOCIR_MARK
        assert 'fill="#E0932C"' in DOCIR_MARK
        assert "#12161C" not in DOCIR_MARK, "the light-only ink would be invisible on dark"

    def test_it_is_the_default_on_every_page(self) -> None:
        pages = render_site(build_site(_DOCS), title="Docs", version="1")
        for name in ("index.html", "graph.html", "adr-0001.html"):
            assert 'fill="#E0932C"' in pages[name], f"{name} has no mark"

    def test_the_bracket_is_ink_not_the_link_colour(self) -> None:
        """The mark sits inside an `<a>`. Left to inherit, `currentColor`
        drew the bracket accent-blue on the graph page, whose back-link is not
        the same colour as body text — the kit's ink and paper, never a hue."""
        pages = render_site(build_site(_DOCS), title="Docs", version="1")
        assert ".brandmark{height:22px" in pages["index.html"]
        for name in ("index.html", "graph.html"):
            marks = pages[name][pages[name].index(".brandmark") :]
            assert "color:var(--fg)" in marks[: marks.index("}")], f"{name} inherits its colour"


class TestTheFavicon:
    def test_it_is_the_tile_not_the_bare_mark(self) -> None:
        """The kit's own call: a thin bracket on a transparent ground vanishes
        against dark browser chrome, while the mark on its ink squircle reads
        on any tab strip. Being opaque is why it does not follow the theme."""
        tile = _decoded_favicon(render_site(build_site(_DOCS), title="Docs", version="1"))
        assert 'rx="11"' in tile and 'fill="#12161C"' in tile, "the mark is not on its tile"
        assert 'stroke="#ECEEF1"' in tile, "an ink bracket on an ink tile is invisible"

    def test_it_is_drawn_from_the_same_geometry_as_the_mark(self) -> None:
        """Corner and tab derive from one pair of path strings, so the two
        cannot drift into different logos."""
        tile = _decoded_favicon(render_site(build_site(_DOCS), title="Docs", version="1"))
        assert _paths(tile) == _paths(DOCIR_MARK)

    def test_it_costs_no_network_request(self) -> None:
        """Browsers ask for /favicon.ico on every page and log a 404 without
        one; a data: URI answers it and keeps the page offline-complete."""
        for page in render_site(build_site(_DOCS), title="Docs", version="1").values():
            if page.lstrip().startswith("<!doctype"):
                assert '<link rel="icon" href="data:' in page

    def test_a_custom_logo_brands_the_tab_too(self, tmp_path: Path) -> None:
        """A page whose corner says Acme and whose tab says docir is
        half-applied branding, which reads as a bug."""
        logo = tmp_path / "acme.gif"
        logo.write_bytes(_TINY_GIF)
        branding = resolve_branding(logo)
        expected = base64.b64encode(_TINY_GIF).decode("ascii")
        assert branding.favicon == f'<link rel="icon" href="data:image/gif;base64,{expected}">'
        index = render_site(build_site(_DOCS), title="Docs", version="1", branding=branding)[
            "index.html"
        ]
        assert "#12161C" not in index, "docir's tile survived a custom logo"


class TestACustomLogo:
    def test_it_is_embedded_as_a_data_uri_on_every_page(self, tmp_path: Path) -> None:
        """Inlined, not linked: a page has to survive being copied on its own,
        and `<img src="logo.png">` beside the pages would not."""
        logo = tmp_path / "acme.gif"
        logo.write_bytes(_TINY_GIF)
        pages = render_site(
            build_site(_DOCS), title="Docs", version="1", branding=resolve_branding(logo)
        )
        expected = base64.b64encode(_TINY_GIF).decode("ascii")
        for name in ("index.html", "graph.html", "adr-0001.html"):
            assert f"data:image/gif;base64,{expected}" in pages[name]
            assert 'fill="#E0932C"' not in pages[name], "docir's mark must not also appear"

    def test_an_svg_logo_is_an_image_not_inlined_markup(self, tmp_path: Path) -> None:
        """An SVG inlined into the document can carry script and leaks its ids
        and CSS into the page; the same file inside <img> renders and can do
        nothing else."""
        logo = tmp_path / "acme.svg"
        logo.write_text('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>')
        html = resolve_branding(logo).mark
        assert html.startswith('<img class="brandmark" src="data:image/svg+xml;base64,')
        assert "<script>" not in html

    def test_an_unknown_format_names_what_is_accepted(self, tmp_path: Path) -> None:
        logo = tmp_path / "acme.psd"
        logo.write_bytes(_TINY_GIF)
        with pytest.raises(ValidationError, match=r"\.png"):
            resolve_branding(logo)

    def test_a_missing_file_says_so(self, tmp_path: Path) -> None:
        with pytest.raises(ValidationError, match="not found"):
            resolve_branding(tmp_path / "absent.png")

    def test_an_oversized_logo_is_refused_with_the_fix(self, tmp_path: Path) -> None:
        """It is inlined into *every* page, so a 2 MB photograph is 2 MB times
        the corpus — a site of hundreds of megabytes that reads as a docir bug
        rather than as a large input."""
        logo = tmp_path / "huge.png"
        logo.write_bytes(b"\x89PNG" + b"\0" * MAX_LOGO_BYTES)
        with pytest.raises(ValidationError, match="header size"):
            resolve_branding(logo)

    def test_a_bad_logo_fails_before_anything_is_deleted(self, tmp_path: Path) -> None:
        """The output directory is regenerated wholesale. A logo resolved late
        would empty a previous build and *then* fail."""
        out = tmp_path / "site"
        builder = build_site_builder()
        builder.build(PublishRequest(out=out, documents=_DOCS, title="Docs"))
        assert (out / "index.html").exists()
        with pytest.raises(ValidationError):
            builder.build(
                PublishRequest(out=out, documents=_DOCS, title="Docs", logo=tmp_path / "absent.png")
            )
        assert (out / "index.html").exists(), "the previous build was destroyed"
