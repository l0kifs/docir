"""The site's mark: docir's own by default, the publisher's on request.

A generated site that carries someone else's logo is not their documentation
— the corner of every page is the first thing that says whose corpus this is.
So the mark is a build input, and the default is docir's rather than a
placeholder gradient.

Both forms are **inlined into the page**, not linked. A published site has to
work from ``file://`` and from a host with no CDN reachable, and a page that
survives being copied on its own is the property the whole module is built
around; a ``<img src="logo.svg">`` beside the pages would quietly break both.

The two forms are deliberately different mechanisms:

* **docir's own mark is inline SVG**, drawn with ``currentColor`` for the
  bracket. The logo kit ships an ink mark and a paper one for light and dark
  backgrounds; inlined against the header's own colour those collapse into a
  single asset that is already correct in both themes. The caret keeps the
  brand's signal amber at a fixed value — per the kit, amber is *only ever*
  the caret, so a caret that followed the theme would make it decoration.
* **A publisher's logo is a ``data:`` URI in an ``<img>``**, whatever the file
  type. It is not inlined as markup even when it is an SVG: an SVG inlined
  into the document can carry script and its ids and CSS leak into the page,
  while the same file inside ``<img>`` renders and can do nothing else. The
  cost is that it cannot follow the theme, which is the publisher's own call
  to make in their art.
"""

from __future__ import annotations

import base64
import html
import re
from dataclasses import dataclass
from pathlib import Path

from docir.platform.errors import ValidationError

#: The Compile Caret from ``assets/logo/docir-mark.svg`` — a bracket (the IR
#: container) meeting a filled caret (the compile step). The geometry is
#: duplicated here rather than read at runtime because the module renders
#: without touching the filesystem and two path strings are not worth a
#: packaged data file; ``test_branding.py`` pins these paths against the
#: files in ``assets/logo/``, which stay the source of truth for the art.
#:
#: The corner mark and the favicon are both *derived from these two strings*
#: rather than transcribed separately, so the one drift risk the duplication
#: creates exists in one place instead of two.
_BRACKET = "M18 9H11V39H18"
_CARET = "M24 12L41 24L24 36Z"
#: The kit's three colours. Amber is only ever the caret — never decoration.
_AMBER = "#E0932C"
_INK = "#12161C"
_PAPER = "#ECEEF1"

DOCIR_MARK = (
    '<svg class="brandmark" viewBox="0 0 48 48" fill="none" aria-hidden="true">'
    f'<path d="{_BRACKET}" stroke="currentColor" stroke-width="5" '
    'stroke-linecap="butt" stroke-linejoin="miter"/>'
    f'<path d="{_CARET}" fill="{_AMBER}"/></svg>'
)

#: The favicon is the **tile**, not the bare mark, and that is the kit's own
#: call: a thin bracket on a transparent ground vanishes against dark browser
#: chrome, while the mark on its ink squircle reads on any tab strip. Being
#: opaque is also why this one does not follow the theme — the tile carries
#: its own background, so paper-on-ink is correct in both.
_DOCIR_TILE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">'
    f'<rect width="48" height="48" rx="11" fill="{_INK}"/>'
    '<g transform="translate(4.2 4.8) scale(0.8)" fill="none">'
    f'<path d="{_BRACKET}" stroke="{_PAPER}" stroke-width="5" '
    'stroke-linecap="butt" stroke-linejoin="miter"/>'
    f'<path d="{_CARET}" fill="{_AMBER}"/></g></svg>'
)

#: What a logo may be. Deliberately short: these are the formats every browser
#: renders inside an `<img>` without a plugin or a fallback, and an extension
#: docir does not recognise is far more likely to be a mistyped path than a
#: format worth supporting.
_MIME_TYPES = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

#: Cap on a custom logo's size. The logo is inlined into *every* page — the
#: price of a page that is one self-contained file — so a 2 MB photograph is
#: 2 MB times the corpus, and the result (a site of hundreds of megabytes that
#: takes minutes to write) reads as a docir bug rather than as a large input.
#: A header mark is a few kilobytes; 64 KiB is generous, and the error names
#: the fix instead of leaving the publisher to guess a number.
MAX_LOGO_BYTES = 64 * 1024


def _data_uri(mime: str, data: bytes) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def _icon_link(uri: str) -> str:
    """The favicon element. Browsers request ``/favicon.ico`` on every page and
    log a 404 without one; a `data:` URI answers it with no network request, so
    the page stays offline-complete."""
    return f'<link rel="icon" href="{uri}">'


_DOCIR_TILE_URI = _data_uri("image/svg+xml", _DOCIR_TILE.encode("utf-8"))


@dataclass(frozen=True, slots=True)
class Branding:
    """The site's two marks, resolved together.

    One object rather than two calls because they come from one input and one
    validation: a logo that is unreadable must fail once, before the build
    removes anything, not once per place the art is needed.
    """

    #: The corner of the top bar, ready to interpolate.
    mark: str
    #: The ``<link rel="icon">`` element for the page head.
    favicon: str


DOCIR_BRANDING = Branding(mark=DOCIR_MARK, favicon=_icon_link(_DOCIR_TILE_URI))


def resolve_branding(logo: Path | None) -> Branding:
    """docir's marks, or the publisher's — the corner and the tab together.

    One flag brands the whole site: a page whose corner says Acme and whose
    tab says docir is the kind of half-applied branding that reads as a bug.
    A logo shaped for a header is not always shaped for 16 pixels, which is
    the publisher's call to make in their own art rather than docir's to make
    for them by ignoring half the input.
    """
    if logo is None:
        return DOCIR_BRANDING
    uri = _logo_data_uri(Path(logo))
    return Branding(
        mark=f'<img class="brandmark" src="{uri}" alt="">',
        favicon=_icon_link(uri),
    )


def _logo_data_uri(path: Path) -> str:
    suffix = path.suffix.lower()
    mime = _MIME_TYPES.get(suffix)
    if mime is None:
        known = ", ".join(sorted(_MIME_TYPES))
        raise ValidationError(f"unsupported logo format '{suffix or path.name}'; expected {known}")
    if not path.is_file():
        raise ValidationError(f"logo not found: {path}")
    data = path.read_bytes()
    if not data:
        raise ValidationError(f"logo is empty: {path}")
    if len(data) > MAX_LOGO_BYTES:
        raise ValidationError(
            f"logo is {len(data) // 1024} KiB; the limit is {MAX_LOGO_BYTES // 1024} KiB "
            "because it is inlined into every page — export it at header size, "
            "or use an SVG"
        )
    return _data_uri(mime, data)


#: A site title's trailing qualifier — "docir — design docs", "Acme · ADRs".
#: Only a separator with space on both sides counts, so a hyphenated name
#: ("Doc-Index CLI") stays one word.
_BRAND_TAIL = re.compile("\\s+([\u2014\u2013\u00b7|-]\\s+\\S.*)$")


def brand_html(site_title: str) -> str:
    """The wordmark, with any trailing qualifier muted.

    A one-weight brand made "design docs" look like part of the product's
    name. The split is presentational only — the `<title>`, the palette and
    every page heading still carry the whole string. Shared with the graph
    page, whose header is the same bar: two implementations would drift the
    first time someone changed which separators count.
    """
    match = _BRAND_TAIL.search(site_title)
    if not match:
        return html.escape(site_title)
    head = html.escape(site_title[: match.start()])
    return f'{head}&nbsp;<span class="sub">{html.escape(match.group(1))}</span>'
