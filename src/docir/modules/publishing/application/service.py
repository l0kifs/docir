"""Building a site: resolve the corpus, render it, write it out."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from docir.modules.publishing.domain.site import build_site
from docir.modules.publishing.infra.branding import resolve_branding
from docir.modules.publishing.infra.rendering import render_search_index, render_site
from docir.platform.errors import DocirError

#: Written beside the pages so a re-run into the same directory can tell its own
#: output from someone else's files. See :meth:`SiteBuilder.build`.
MARKER_FILE = ".docir-site"


@dataclass(frozen=True, slots=True)
class PublishRequest:
    """Input for ``docir build``."""

    out: Path
    documents: Sequence[Mapping[str, object]]
    title: str = "Documentation"
    version: str = ""
    #: The publisher's own mark for the top-left corner. ``None`` publishes
    #: docir's. A site carrying someone else's logo is not their
    #: documentation, so this is a build input rather than a constant.
    logo: Path | None = None
    #: Overwrite a directory that is not a docir site. Off by default: `--out`
    #: is a path a person types, and a typo pointing at `src/` should not be
    #: answered by writing HTML into it.
    force: bool = False


@dataclass(frozen=True, slots=True)
class PublishResult:
    """What was written."""

    out: Path
    pages: int
    documents: int
    stale: int
    files: tuple[str, ...] = ()


class SiteBuilder:
    """Renders a corpus into a self-contained static site."""

    def build(self, request: PublishRequest) -> PublishResult:
        """Write the site, and refuse to scribble on a directory that is not one.

        The output directory is regenerated wholesale — a document deleted from
        the store must not survive as an orphaned page — which is exactly why
        the guard exists: "delete everything here first" needs to be sure it
        owns "here". A previous build leaves :data:`MARKER_FILE`; anything else
        non-empty needs ``force``.
        """
        out = Path(request.out)
        self._check_target(out, force=request.force)
        # Before the guard clears the directory: an unreadable logo should
        # fail the build, not empty the output and then fail it.
        branding = resolve_branding(request.logo)

        site = build_site(request.documents)
        pages = render_site(site, title=request.title, version=request.version, branding=branding)
        pages["search-index.json"] = render_search_index(site)

        out.mkdir(parents=True, exist_ok=True)
        # Both generated extensions are swept, for the same reason: a page and
        # its markdown source are equally derived, and one left behind after
        # its document is deleted is an orphan nobody knows is stale.
        for pattern in ("*.html", "*.md"):
            for existing in sorted(out.glob(pattern)):
                existing.unlink()
        for name, content in pages.items():
            (out / name).write_text(content, encoding="utf-8")
        (out / MARKER_FILE).write_text("", encoding="utf-8")

        return PublishResult(
            out=out,
            pages=len(pages),
            documents=len(site.documents),
            stale=site.stale_count,
            files=tuple(sorted(pages)),
        )

    @staticmethod
    def _check_target(out: Path, *, force: bool) -> None:
        if force or not out.exists():
            return
        if not out.is_dir():
            raise DocirError(f"{out} exists and is not a directory")
        if (out / MARKER_FILE).exists() or not any(out.iterdir()):
            return
        raise DocirError(
            f"{out} is not empty and was not built by docir; "
            "pass --force to overwrite it, or choose another --out"
        )
